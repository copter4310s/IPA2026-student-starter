"""Ansible apply-only adapter."""
import ipaddress
import json
import os
import subprocess
import tempfile
from pathlib import Path

import yaml


PLAYBOOK = Path(__file__).resolve().parents[2] / "ansible" / "apply_interface.yml"


def _run_playbook(variables):
    router = variables["router"]
    username = os.getenv("ROUTER_USER", "")
    password = os.getenv("ROUTER_PASS", "")
    inventory = {"all": {"children": {"target": {"hosts": {"router": {
        "ansible_host": router,
        "ansible_user": username,
        "ansible_password": password,
        "ansible_connection": "ansible.netcommon.network_cli",
        "ansible_network_os": "cisco.ios.ios",
    }}}}}}
    with tempfile.TemporaryDirectory() as tmp:
        inventory_path = Path(tmp) / "inventory.yml"
        inventory_path.write_text(yaml.safe_dump(inventory), encoding="utf-8")
        command = ["ansible-playbook", str(PLAYBOOK), "-i", str(inventory_path),
                   "--extra-vars", json.dumps(variables)]
        return subprocess.run(command, capture_output=True, text=True, timeout=90)


def _error(exc):
    name = type(exc).__name__.lower()
    if isinstance(exc, PermissionError) or "authentication" in name:
        code = "authentication_failed"
    elif isinstance(exc, (ConnectionError, TimeoutError, subprocess.TimeoutExpired)) or "timeout" in name or "connection" in name:
        code = "connection_failed"
    else:
        code = "backend_failed"
    return {"status": "error", "result": code}


def apply_interface(router, desired_interface, run_playbook=None):
    try:
        address = ipaddress.IPv4Interface(desired_interface["ipv4"])
        variables = {
            "router": router,
            "interface_name": desired_interface["name"],
            "description": desired_interface["description"],
            "ipv4_address": str(address.ip),
            "netmask": str(address.network.netmask),
            "shutdown": desired_interface["admin_state"] == "down",
        }
        result = (run_playbook or _run_playbook)(variables)
        if isinstance(result, subprocess.CompletedProcess) and result.returncode != 0:
            output = f"{result.stdout}\n{result.stderr}".lower()
            if "authentication" in output or "permission denied" in output or "invalid username" in output:
                return {"status": "error", "result": "authentication_failed"}
            if "unreachable" in output or "timed out" in output or "connection refused" in output:
                return {"status": "error", "result": "connection_failed"}
            return {"status": "error", "result": "backend_failed"}
        return {"status": "ok", "result": "applied"}
    except Exception as exc:
        return _error(exc)
