"""Validation and YAML loading for Part 1 requests."""

from collections.abc import Mapping
from pathlib import Path

import yaml


ALLOWED_ROUTERS = {
    "10.0.29.101",
    "10.0.29.102",
    "10.0.29.103",
    "10.0.29.104",
    "10.0.29.105",
}

ALLOWED_ACTIONS = {
    "restconf": {"status", "plan", "apply"},
    "netconf": {"status", "plan", "apply"},
    "ansible": {"apply"},
    "netmiko-textfsm": {"status", "delete"},
}


def validate_action(method, action):
    """Return whether *method* supports *action*."""
    return (
        isinstance(method, str)
        and isinstance(action, str)
        and method in ALLOWED_ACTIONS
        and action in ALLOWED_ACTIONS[method]
    )


def _error(result):
    return {"status": "error", "result": result}


def validate_request(data: dict):
    """
    Validate one IPA2026 desired-state request.

    Return a response dictionary according to
    specs/response-spec-v1.md.
    """
    # TODO: implement
    if data.get("method") not in ["restconf", "netconf", "ansible", "netmiko-textfsm"]:
        return {"status":"error","result":"invalid_method"}

    if not validate_action(data.get("method"), data.get("action")):
        return {"status":"error","result":"invalid_action"}

    if not(str(data.get("version")).isnumeric() and data.get("version") == 1):
        return {"status":"error","result":"invalid_version"}

    if data.get("router") not in ["10.0.29.101", "10.0.29.102", "10.0.29.103", "10.0.29.104", "10.0.29.105"]:
        return {"status":"error","result":"invalid_router"}

    if not data.get("desired"):
        return {"status":"error","result":"missing_desired"}

    if "action" not in data or data["action"] is None or data["action"] == "":
        return _error("missing_action")
    action = data["action"]
    if not isinstance(action, str) or not validate_action(method, action):
        return _error("invalid_action")

    desired = data.get("desired")
    if not isinstance(desired, Mapping):
        return _error("missing_desired")
    interface = desired.get("interface")
    if not isinstance(interface, Mapping):
        return _error("missing_interface")
    name = interface.get("name")
    if name is None or name == "":
        return _error("missing_interface_name")

    if action in {"plan", "apply"}:
        for field in ("ipv4", "description", "admin_state"):
            if field not in interface or interface[field] is None or interface[field] == "":
                return _error(f"missing_{field}")
        if not isinstance(interface["admin_state"], str) or interface["admin_state"] not in {"up", "down"}:
            return _error("invalid_admin_state")

    return True


def process_request_file(path):
    """
    Read a YAML request file, validate it,
    and return a response dictionary.
    """
    # TODO: implement
    read_data = requests.get(path).content

    try:
        data_yaml = yaml.safe_load(read_data)
        return data_yaml
    except:
        return {"status":"error","result":"invalid_yaml"}

if __name__ == "__main__":
    print(process_request_file("https://raw.githubusercontent.com/copter4310s/IPA2026-student-starter/refs/heads/main/sample-tests/webex-manual/07-plan-no-change.yaml"))
