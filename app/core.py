import yaml
import requests

def validate_action(method, action):
    """ Validate whether if action is available for chosen method """
    allow_action = {
        "restconf": ["status", "plan", "apply"],
        "netconf": ["status", "plan", "apply"],
        "ansible": ["apply"],
        "netmiko-textfsm": ["status", "delete"]
    }

    return method in allow_action and action in allow_action.get(method)

def validate_request(data: dict):
    """
    Validate one IPA2026 desired-state request.

    Return a response dictionary according to
    specs/response-spec-v1.md.
    """
    # TODO: implement
    if not(str(data.get("version")).isnumeric() and data.get("version") == 1):
        return {"status":"error","result":"invalid_version"}

    if not data.get("router"):
        return {"status":"error","result":"missing_router"}

    if data.get("router") not in ["10.0.29.101", "10.0.29.102", "10.0.29.103", "10.0.29.104", "10.0.29.105"]:
        return {"status":"error","result":"invalid_router"}

    if not data.get("method"):
        return {"status":"error","result":"missing_method"}

    if data.get("method") not in ["restconf", "netconf", "ansible", "netmiko-textfsm"]:
        return {"status":"error","result":"invalid_method"}

    if not data.get("action"):
        return {"status":"error","result":"missing_action"}

    if not validate_action(data.get("method"), data.get("action")):
        return {"status":"error","result":"invalid_action"}

    if not data.get("desired"):
        return {"status":"error","result":"missing_desired"}

    if not data.get("desired").get("interface"):
        return {"status":"error","result":"missing_interface"}

    if not data.get("desired").get("interface").get("name"):
        return {"status":"error","result":"missing_interface_name"}

    if data.get("method") in ["apply", "plan"]:
        if not data.get("desired").get("interface").get("ipv4"):
            return {"status":"error","result":"missing_ipv4"}

        if not data.get("desired").get("interface").get("description"):
            return {"status":"error","result":"missing_description"}

        if not data.get("desired").get("interface").get("admin_state"):
            return {"status":"error","result":"missing_admin_state"}

        if data.get("desired").get("interface").get("admin_state") not in ["up", "down"]:
            return {"status":"error","result":"invalid_admin_state"}

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
