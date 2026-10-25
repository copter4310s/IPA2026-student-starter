def plan_interface(
    router,
    desired_interface,
    get_interface_state,
):
    """Build a Part 2 plan from backend status."""
    from app.planner import build_plan

    response = get_interface_state(router, desired_interface["name"])
    if response.get("status") != "ok":
        return response
    current = response.get("interface") if response.get("result") == "found" else None
    if response.get("result") not in {"found", "not_found"}:
        return {"status": "error", "result": "backend_failed"}
    return build_plan(desired_interface, current)
