"""NETCONF adapter for Cisco IOS XE Loopback interfaces."""
import ipaddress
import os
import xml.etree.ElementTree as ET

from ncclient import manager

from app.backends.planning import plan_interface as _plan

IETF = "urn:ietf:params:xml:ns:yang:ietf-interfaces"
IP = "urn:ietf:params:xml:ns:yang:ietf-ip"
BASE = "urn:ietf:params:xml:ns:netconf:base:1.0"
NATIVE = "http://cisco.com/ns/yang/Cisco-IOS-XE-native"


def _get(router, filter_xml):
    with manager.connect(host=router, port=830, username=os.getenv("ROUTER_USER", ""),
                         password=os.getenv("ROUTER_PASS", ""), hostkey_verify=False,
                         device_params={"name": "iosxe"}, timeout=10) as session:
        return session.get_config(source="running", filter=filter_xml).data_xml


def _edit(router, config_xml):
    with manager.connect(host=router, port=830, username=os.getenv("ROUTER_USER", ""),
                         password=os.getenv("ROUTER_PASS", ""), hostkey_verify=False,
                         device_params={"name": "iosxe"}, timeout=10) as session:
        session.edit_config(target="running", config=config_xml)


def _error(exc):
    name = type(exc).__name__.lower()
    module = type(exc).__module__.lower()
    if isinstance(exc, PermissionError) or "authentication" in name or "authorization" in name:
        code = "authentication_failed"
    elif isinstance(exc, (ConnectionError, TimeoutError)) or "timeout" in name or "transport" in name or "ssh" in name or "connection" in name:
        code = "connection_failed"
    else:
        code = exc
    return {"status": "error", "result": code}


def _tag(ns, name):
    return f"{{{ns}}}{name}"


def get_interface_state(router, interface_name, netconf_get_config=None):
    flt = f'<interfaces xmlns="{IETF}"><interface><name>{interface_name}</name></interface></interfaces>'
    try:
        xml = (netconf_get_config or _get)(router, flt)
        root = ET.fromstring(xml)
        entry = next((node for node in root.iter(_tag(IETF, "interface"))
                      if node.findtext(_tag(IETF, "name")) == interface_name), None)
        if entry is None:
            return {"status": "ok", "result": "not_found", "interface": None}
        ipv4_node = entry.find(_tag(IP, "ipv4"))
        address = ipv4_node.find(_tag(IP, "address")) if ipv4_node is not None else None
        ipv4 = None
        if address is not None:
            ip = address.findtext(_tag(IP, "ip"))
            mask = address.findtext(_tag(IP, "netmask"))
            if ip and mask:
                ipv4 = str(ipaddress.IPv4Interface(f"{ip}/{mask}").with_prefixlen)
        enabled = entry.findtext(_tag(IETF, "enabled"), "true").strip().lower() == "true"
        return {"status": "ok", "result": "found", "interface": {
            "name": interface_name, "ipv4": ipv4,
            "description": entry.findtext(_tag(IETF, "description")),
            "admin_state": "up" if enabled else "down",
        }}
    except Exception as exc:
        return _error(exc)


def plan_interface(router, desired_interface, netconf_get_config=None):
    return _plan(router, desired_interface,
                 lambda host, name: get_interface_state(host, name, netconf_get_config))


def apply_interface(router, desired_interface, netconf_edit_config=None):
    try:
        number = desired_interface["name"][len("Loopback"):]
        ip = ipaddress.IPv4Interface(desired_interface["ipv4"])
        root = ET.Element(_tag(BASE, "config"), {"xmlns:nc": BASE})
        native = ET.SubElement(root, _tag(NATIVE, "native"))
        interfaces = ET.SubElement(native, _tag(NATIVE, "interface"))
        loopback = ET.SubElement(interfaces, _tag(NATIVE, "Loopback"), {_tag(BASE, "operation"): "replace"})
        ET.SubElement(loopback, _tag(NATIVE, "name")).text = number
        ET.SubElement(loopback, _tag(NATIVE, "description")).text = desired_interface["description"]
        ip_node = ET.SubElement(loopback, _tag(NATIVE, "ip"))
        address_node = ET.SubElement(ip_node, _tag(NATIVE, "address"))
        primary = ET.SubElement(address_node, _tag(NATIVE, "primary"))
        ET.SubElement(primary, _tag(NATIVE, "address")).text = str(ip.ip)
        ET.SubElement(primary, _tag(NATIVE, "mask")).text = str(ip.network.netmask)
        if desired_interface["admin_state"] == "down":
            ET.SubElement(loopback, _tag(NATIVE, "shutdown"))
        xml = ET.tostring(root, encoding="unicode")
        # ElementTree emits the operation attribute in the NETCONF namespace.
        (netconf_edit_config or _edit)(router, xml)
        return {"status": "ok", "result": "applied"}
    except Exception as exc:
        return _error(exc)
