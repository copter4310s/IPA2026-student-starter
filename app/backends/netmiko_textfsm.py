"""Netmiko/TextFSM adapter for IOS status and interface deletion."""
import ipaddress
import os

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
        code = exc
    return {"status": "error", "result": code}


def _get(router, interface_name):
    with _connect(router) as conn:
        ip_info = conn.send_command(f"show ip interface {interface_name}", use_textfsm=True)
        descriptions = conn.send_command("show interfaces description", use_textfsm=True)
    return ip_info, descriptions


def _full_name(name):
    if name.startswith("Lo") and name[2:].isdigit():
        return "Loopback" + name[2:]
    return name


def get_interface_state(router, interface_name, netmiko_get=None):
    try:
        ip_info, descriptions = (netmiko_get or _get)(router, interface_name)
        ip_info = ip_info or []
        descriptions = descriptions or []
        row = next((item for item in ip_info if _full_name(str(item.get("interface", ""))) == interface_name), None)
        if row is None:
            return {"status": "ok", "result": "not_found", "interface": None}
        desc_row = next((item for item in descriptions if _full_name(str(item.get("port", ""))) == interface_name), {})
        addresses = row.get("ip_address") or []
        prefixes = row.get("prefix_length") or []
        ipv4 = None
        if addresses:
            prefix = prefixes[0] if prefixes else "32"
            ipv4 = str(ipaddress.IPv4Interface(f"{addresses[0]}/{prefix}").with_prefixlen)
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
    if before.get("status") == "error":
        raise RuntimeError(before["result"])
    if before.get("result") == "not_found":
        return "not_found"
    with _connect(router) as conn:
        output = conn.send_config_set([f"no interface {interface_name}"])
    if any(token in output.lower() for token in ("% invalid", "% incomplete", "% ambiguous", "% failed")):
        raise RuntimeError("delete command rejected")
    after = get_interface_state(router, interface_name)
    if after.get("status") == "error":
        raise RuntimeError(after["result"])
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
