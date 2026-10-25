"""RESTCONF adapter for Cisco IOS XE Loopback interfaces."""
import ipaddress
import os

import requests

from app.backends.planning import plan_interface as _plan


def _auth():
    return os.getenv("ROUTER_USER", ""), os.getenv("ROUTER_PASS", "")


def _url(router, path):
    return f"https://{router}/restconf/data/{path}"


def _get(url):
    return requests.get(url, auth=_auth(), headers={"Accept": "application/yang-data+json"}, timeout=10, verify=False)


def _put(url, *, json):
    return requests.put(url, json=json, auth=_auth(), headers={"Content-Type": "application/yang-data+json", "Accept": "application/yang-data+json"}, timeout=10, verify=False)


def _error(exc):
    if isinstance(exc, PermissionError):
        return {"status": "error", "result": "authentication_failed"}
    if isinstance(exc, (ConnectionError, requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        return {"status": "error", "result": "connection_failed"}
    return {"status": "error", "result": "backend_failed"}


def _response_error(status):
    if status in (401, 403):
        return {"status": "error", "result": "authentication_failed"}
    if status in (408, 425, 429, 500, 502, 503, 504):
        return {"status": "error", "result": "connection_failed" if status in (408, 502, 503, 504) else "backend_failed"}
    return {"status": "error", "result": "backend_failed"}


def get_interface_state(router, interface_name, http_get=None):
    url = _url(router, f"ietf-interfaces:interfaces/interface={interface_name}")
    try:
        response = (http_get or _get)(url)
        if response.status_code == 404:
            return {"status": "ok", "result": "not_found", "interface": None}
        if response.status_code in (401, 403) or not 200 <= response.status_code < 300:
            return _response_error(response.status_code)
        raw = response.json()
        if not isinstance(raw, dict):
            return {"status": "error", "result": "backend_failed"}
        item = raw.get("ietf-interfaces:interface", raw)
        if not isinstance(item, dict):
            return {"status": "error", "result": "backend_failed"}
        addresses = item.get("ietf-ip:ipv4", {}).get("address", [])
        ipv4 = None
        if addresses:
            first = addresses[0]
            ipv4 = str(ipaddress.IPv4Interface(f"{first['ip']}/{first['netmask']}").with_prefixlen)
        enabled = item.get("enabled", True)
        if isinstance(enabled, str):
            enabled = enabled.strip().lower() == "true"
        return {"status": "ok", "result": "found", "interface": {
            "name": item.get("name", interface_name), "ipv4": ipv4,
            "description": item.get("description"),
            "admin_state": "up" if enabled else "down",
        }}
    except Exception as exc:
        return _error(exc)


def plan_interface(router, desired_interface, http_get=None):
    return _plan(router, desired_interface, lambda host, name: get_interface_state(host, name, http_get))


def apply_interface(router, desired_interface, http_put=None):
    try:
        ip = ipaddress.IPv4Interface(desired_interface["ipv4"])
        number = int(desired_interface["name"][len("Loopback"):])
        payload = {"Cisco-IOS-XE-native:Loopback": {
            "name": number, "description": desired_interface["description"],
            "ip": {"address": {"primary": {"address": str(ip.ip), "mask": str(ip.network.netmask)}}},
        }}
        if desired_interface["admin_state"] == "down":
            payload["Cisco-IOS-XE-native:Loopback"]["shutdown"] = [None]
        url = _url(router, f"Cisco-IOS-XE-native:native/interface/Loopback={number}")
        response = (http_put or _put)(url, json=payload)
        if response.status_code in (200, 201, 204):
            return {"status": "ok", "result": "applied"}
        return _response_error(response.status_code)
    except Exception as exc:
        return _error(exc)
