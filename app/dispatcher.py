"""Part 4 student implementation."""

from app.backends import ansible, netconf, netmiko_textfsm, restconf

def dispatch_request(data):
    method = data["method"]
    action = data["action"]
    router = data["router"]
    interface = data["desired"]["interface"]
    if action in {"status", "delete"}:
        name = interface["name"]
        if method == "restconf":
            return restconf.get_interface_state(router, name)
        if method == "netconf":
            return netconf.get_interface_state(router, name)
        if method == "netmiko-textfsm":
            return netmiko_textfsm.get_interface_state(router, name) if action == "status" else netmiko_textfsm.delete_interface(router, name)
    if method == "restconf":
        return restconf.plan_interface(router, interface) if action == "plan" else restconf.apply_interface(router, interface)
    if method == "netconf":
        return netconf.plan_interface(router, interface) if action == "plan" else netconf.apply_interface(router, interface)
    if method == "ansible" and action == "apply":
        return ansible.apply_interface(router, interface)
    return {"status": "error", "result": "invalid_action"}
