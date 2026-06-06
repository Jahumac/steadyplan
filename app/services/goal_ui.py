def goal_track_status(projection, monthly_contribution, remaining, included_account_count, selected_tags):
    if remaining <= 0 or (projection and projection.get("reached")):
        return {"label": "Reached", "detail": "target already reached", "tone": "ahead"}
    if included_account_count == 0:
        detail = "link an account to this goal" if selected_tags else "add an account to start tracking"
        return {"label": "Needs attention", "detail": detail, "tone": "behind"}
    if monthly_contribution <= 0:
        return {"label": "Needs attention", "detail": "set a monthly contribution", "tone": "behind"}
    if projection and projection.get("total_months") is None:
        return {"label": "Needs attention", "detail": "increase contributions to bring this within range", "tone": "behind"}
    if projection and projection.get("eta_label"):
        return {"label": "On course", "detail": f"est. {projection['eta_label']}", "tone": "on-track"}
    return {"label": "On course", "detail": "at current pace", "tone": "on-track"}


def goal_projection_copy(projection, monthly_contribution, remaining, included_account_count, selected_tags):
    if remaining <= 0 or (projection and projection.get("reached")):
        return "Target reached"
    if projection and projection.get("total_months"):
        eta = f" · {projection['eta_label']}" if projection.get("eta_label") else ""
        return f"~ {projection['duration']} to go{eta}"
    detail = goal_track_status(
        projection,
        monthly_contribution,
        remaining,
        included_account_count,
        selected_tags,
    )["detail"]
    return detail[:1].upper() + detail[1:] if detail else None
