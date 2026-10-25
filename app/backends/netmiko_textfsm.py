"""Netmiko/TextFSM adapter for IOS status and interface deletion."""
import ipaddress
import os
import re
from collections.abc import Mapping

from netmiko import ConnectHandler


def _connect(router):
    return ConnectHandler(device_type="cisco_ios", host=router,
                         username=os.getenv("ROUTER_USER", ""),
                         password=os.getenv("ROUTER_PASS", ""),
                         disabled_algorithms={"pubkeys": ["rsa-sha2-256", "rsa-sha2-512"]},
                         timeout=10)

def _error(exc):
    name = type(exc).__name__.lower()
    if isinstance(exc, PermissionError) or "authentication" in name:
        code = "authentication_failed"
    elif isinstance(exc, (ConnectionError, TimeoutError)) or "timeout" in name or "connection" in name or "ssh" in name:
        code = "connection_failed"
    else:
        code = "backend_failed"
    return {"status": "error", "result": code}


def _get(router, interface_name):
    with _connect(router) as conn:
        command = f"show ip interface {interface_name}"
        try:
            ip_info = conn.send_command(command, use_textfsm=True)
        except Exception as exc:
            # IOS can reject a query for an interface that does not exist.
            # Netmiko then passes that CLI response to TextFSM, which raises
            # StateError instead of returning an empty record list. Inspect
            # the raw response and translate only that specific case to [];
            # unrelated TextFSM errors remain backend failures.
            if "textfsm" not in type(exc).__name__.lower() and "state error raised" not in str(exc).lower():
                raise
            raw = conn.send_command(command, use_textfsm=False)
            raw_lower = raw.lower() if isinstance(raw, str) else ""
            missing_markers = (
                "invalid input detected at '^' marker",
                "invalid interface",
                "interface not found",
                "no such interface",
            )
            if any(marker in raw_lower for marker in missing_markers):
                return [], []
            raise
        descriptions = conn.send_command("show interfaces description", use_textfsm=True)
    return ip_info, descriptions

def _full_name(name):
    if name.startswith("Lo") and name[2:].isdigit():
        return "Loopback" + name[2:]
    return name


def _records(value, command):
    """Require Netmiko's TextFSM result shape (a list of field mappings).

    Netmiko returns the unparsed CLI output as a string when it cannot find or
    apply a TextFSM template. Treat that as a parsing failure instead of
    iterating over its characters and reporting a misleading AttributeError.
    """
    if value is None or value == []:
        return []
    if not isinstance(value, list) or any(not isinstance(row, Mapping) for row in value):
        raise ValueError(f"TextFSM did not return parsed records for {command}")
    return value


def _first(value, default=None):
    """Handle TextFSM fields represented as either scalars or lists."""
    if isinstance(value, (list, tuple)):
        return value[0] if value else default
    return value if value not in (None, "") else default


def _interface_exists_raw(router, interface_name):
    """Verify interface existence from IOS output without relying on TextFSM.

    Some IOS versions return an unparsed CLI error when querying an interface
    that was just removed. The command's normal interface heading is enough to
    tell whether the interface is still present.
    """
    with _connect(router) as conn:
        output = conn.send_command(f"show ip interface {interface_name}")
    if not isinstance(output, str):
        raise ValueError("Unexpected output while verifying interface deletion")
    heading = re.compile(rf"^\s*{re.escape(interface_name)}\s+is\s+", re.IGNORECASE | re.MULTILINE)
    if heading.search(output):
        return True
    if any(token in output.lower() for token in ("% ambiguous", "% incomplete")):
        raise ValueError("Could not verify interface deletion")
    return False


def get_interface_state(router, interface_name, netmiko_get=None):
    try:
        ip_info, descriptions = (netmiko_get or _get)(router, interface_name)
        ip_info = _records(ip_info, "show ip interface")
        descriptions = _records(descriptions, "show interfaces description")
        row = next((item for item in ip_info if _full_name(str(item.get("interface", ""))) == interface_name), None)
        if row is None:
            return {"status": "ok", "result": "not_found", "interface": None}
        desc_row = next((item for item in descriptions if _full_name(str(item.get("port", ""))) == interface_name), {})
        address = _first(row.get("ip_address"))
        prefix = _first(row.get("prefix_length"), "32")
        ipv4 = None
        if address:
            ipv4 = str(ipaddress.IPv4Interface(f"{address}/{prefix}").with_prefixlen)
        state = str(row.get("link_status", "up")).strip().lower()
        admin_state = "down" if "administratively down" in state or state in {"admin down", "down"} else "up"
        return {"status": "ok", "result": "found", "interface": {
            "name": interface_name, "ipv4": ipv4,
            "description": desc_row.get("description") or None,
            "admin_state": admin_state,
        }}
    except Exception as exc:
        return _error(exc)


def _delete(router, interface_name):
    before = get_interface_state(router, interface_name)
    if not isinstance(before, Mapping):
        raise RuntimeError("backend_failed")
    if before.get("status") == "error":
        raise RuntimeError(before["result"])
    if before.get("result") == "not_found":
        return "not_found"
    with _connect(router) as conn:
        output = conn.send_config_set([f"no interface {interface_name}"])
    if any(token in output.lower() for token in ("% invalid", "% incomplete", "% ambiguous", "% failed")):
        raise RuntimeError("delete command rejected")
    after = get_interface_state(router, interface_name)
    if not isinstance(after, Mapping):
        raise RuntimeError("backend_failed")
    if after.get("status") == "error":
        # A missing interface may produce raw IOS output that TextFSM cannot
        # parse. Confirm absence directly before treating it as deleted.
        if _interface_exists_raw(router, interface_name):
            return "failed"
        return "deleted"
    return "deleted" if after.get("result") == "not_found" else "failed"


def delete_interface(router, interface_name, netmiko_delete=None):
    try:
        result = (netmiko_delete or _delete)(router, interface_name)
        if result == "deleted":
            return {"status": "ok", "result": "deleted"}
        if result == "not_found":
            return {"status": "ok", "result": "not_found", "interface": None}
        return {"status": "error", "result": "backend_failed"}
    except Exception as exc:
        # Preserve normalized failures raised by the live helper.
        if isinstance(exc, RuntimeError) and str(exc) in {"authentication_failed", "connection_failed", "backend_failed"}:
            return {"status": "error", "result": str(exc)}
        return _error(exc)
