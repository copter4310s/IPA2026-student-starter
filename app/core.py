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
    """Validate a parsed request; return its error response or ``True``."""
    if not isinstance(data, Mapping):
        return _error("invalid_yaml")

    # Field order is specified and determines which error is returned first.
    version = data.get("version")
    if type(version) is not int or version != 1:
        return _error("invalid_version")

    router = data.get("router")
    if router is None or router == "":
        return _error("missing_router")
    if not isinstance(router, str) or router not in ALLOWED_ROUTERS:
        return _error("invalid_router")

    method = data.get("method")
    if method is None or method == "":
        return _error("missing_method")
    if not isinstance(method, str) or method not in ALLOWED_ACTIONS:
        return _error("invalid_method")

    action = data.get("action")
    if action is None or action == "":
        return _error("missing_action")
    if not validate_action(method, action):
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
            value = interface.get(field)
            if field not in interface or value is None or value == "":
                return _error(f"missing_{field}")
        admin_state = interface["admin_state"]
        if not isinstance(admin_state, str) or admin_state not in {"up", "down"}:
            return _error("invalid_admin_state")

    return True


def load_request_data(path):
    """Parse a YAML request file once; return ``(mapping, error)``."""
    try:
        with Path(path).open("r", encoding="utf-8") as request_file:
            data = yaml.safe_load(request_file)
    except (OSError, UnicodeError, yaml.YAMLError):
        return None, _error("invalid_yaml")
    if not isinstance(data, Mapping):
        return None, _error("invalid_yaml")
    return data, None


def process_request_file(path):
    """Load and validate a YAML request file, returning its response."""
    data, parse_error = load_request_data(path)
    if parse_error is not None:
        return parse_error
    validation_error = validate_request(data)
    if validation_error is not True:
        return validation_error
    return {"status": "ok", "result": "accepted"}
