"""Part 4 student implementation."""

import json

import logging

import os

from concurrent.futures import ThreadPoolExecutor

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pathlib import Path

from tempfile import TemporaryDirectory

from app.integration import process_request

from app.webex_client import WEBEX_API_BASE, WebexClient

class WebexEventHandler:
    def __init__(self, client, bot_person_id, processor=None):
        self.client = client
        self.bot_person_id = bot_person_id
        self.processor = processor or process_request

    def handle_event(self, event):
        if not isinstance(event, dict):
            return None
        data = event.get("data")
        if (event.get("resource") != "messages" or event.get("event") != "created"
                or not isinstance(data, dict) or not isinstance(data.get("id"), str) or not data["id"]):
            return None
        if data.get("personId") == self.bot_person_id:
            return None

        message = self.client.get_message(data["id"])
        if not isinstance(message, dict) or message.get("personId") == self.bot_person_id:
            return None
        room_id = message.get("roomId")
        if not room_id:
            return None
        mentions = message.get("mentionedPeople", [])
        files = message.get("files", [])
        if not isinstance(files, list):
            files = []

        if len(files) > 1:
            result = {"status": "error", "result": "multiple_attachments"}
        elif not files:
            result = self.processor(mentions, None, self.bot_person_id)
        else:
            temp_path = None
            try:
                content = self.client.download_file(files[0])
                with TemporaryDirectory(prefix="ipa2026-") as temp_dir:
                    temp_path = Path(temp_dir) / "request.yaml"
                    temp_path.write_bytes(content)
                    result = self.processor(mentions, temp_path, self.bot_person_id)
            except Exception:
                logging.exception("Failed to process Webex attachment")
                result = {"status": "error", "result": "backend_failed"}

        text = json.dumps(result, separators=(",", ":"), ensure_ascii=False)
        self.client.send_message(room_id, text)
        return result

def make_http_handler(submit_event):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path != "/health":
                self._send(404, {"status": "error", "result": "not_found"})
                return
            self._send(200, {"status": "ok", "result": "healthy"})

        def do_POST(self):
            if self.path != "/webhook":
                self._send(404, {"status": "error", "result": "not_found"})
                return
            try:
                length_header = self.headers.get("Content-Length")
                length = int(length_header) if length_header is not None else 0
                if not 1 <= length <= 1_000_000:
                    raise ValueError("invalid body length")
                body = self.rfile.read(length)
                if len(body) != length:
                    raise ValueError("truncated body")
                event = json.loads(body)
                if not isinstance(event, dict):
                    raise ValueError("event must be an object")
            except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
                self._send(400, {"status": "error", "result": "invalid_event"})
                return
            try:
                submit_event(event)
            except Exception:
                logging.exception("Unable to submit Webex event")
                self._send(500, {"status": "error", "result": "backend_failed"})
                return
            self._send(200, {"status": "ok", "result": "accepted"})

        def log_message(self, fmt, *args):
            logging.info("%s - %s", self.address_string(), fmt % args)

    return Handler

def main():
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    client = WebexClient()
    response = client.session.get(f"{WEBEX_API_BASE}/people/me", headers=client.headers, timeout=10)
    response.raise_for_status()
    bot_person_id = response.json().get("id")
    if not bot_person_id:
        raise RuntimeError("Webex did not return the bot person ID")

    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="webex-event")
    event_handler = WebexEventHandler(client, bot_person_id)
    host = os.getenv("WEBHOOK_HOST", "0.0.0.0")
    port = int(os.getenv("WEBHOOK_PORT", "8000"))
    server = ThreadingHTTPServer((host, port), make_http_handler(
        lambda event: pool.submit(event_handler.handle_event, event)
    ))
    logging.info("Webhook listening on %s:%s", host, port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        pool.shutdown(wait=True)

if __name__ == "__main__":
    main()
