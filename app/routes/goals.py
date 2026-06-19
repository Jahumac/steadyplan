from datetime import date
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.calculations import (
    effective_account_value,
    projected_account_value,
    projection_monthly_contribution,
    projection_start_month_key,
    progress_to_goal,
    remaining_to_goal,
)
from app.utils import optional_float, optional_int, split_tags as _split_tags
from app.models import (
    fetch_assumptions,
    fetch_user_tags,
    create_goal,
    delete_goal,
    fetch_all_accounts,
    fetch_all_goals,
    fetch_contribution_overrides_for_accounts,
    fetch_goal,
    fetch_holding_totals_by_account,
    update_goal,
)
from app.services.goal_projection import project_goal
from app.services.goal_ui import goal_projection_copy

goals_bp = Blueprint("goals", __name__)


def _goal_payload_from_form(form):
    # getlist handles multiple checkboxes named "selected_tags" (direct submit approach).
    # Falls back to a single hidden input value if only one value is present.
    tag_values = [t.strip() for t in form.getlist("selected_tags") if t.strip()]
    return {
        "name": form.get("name", "").strip(),
        "target_value": max(0.0, optional_float(form.get("target_value"), default=0.0)),
        "goal_type": form.get("goal_type", "Tagged Goal").strip(),
        "selected_tags": ", ".join(tag_values),
        "notes": form.get("notes", "").strip(),
    }


def _project_goal(included_accounts, target, assumptions):
    return project_goal(included_accounts, target, assumptions, today=date.today())


def _has_contribution_overrides(accounts):
    return any(account.get("_contribution_overrides") for account in accounts)


def _is_retirement_goal(goal, selected_tags):
    goal_type = (goal["goal_type"] or "").lower()
    tags = " ".join(selected_tags).lower()
    return "retirement" in goal_type or "pension" in goal_type or "retirement" in tags or "pension" in tags


def _build_projection_source_summary(goal, included_accounts, assumptions, monthly_contribution, selected_tags):
    if not included_accounts:
        return None

    has_overrides = _has_contribution_overrides(included_accounts)
    summary = {
        "account_count": len(included_accounts),
        "monthly_contribution": monthly_contribution,
        "uses_overrides": has_overrides,
        "calendar_label": "Overrides active" if has_overrides else "Account defaults",
        "growth_label": "Growth assumptions",
        "method_note": "Same month-by-month projection as Planning.",
        "caveat": "Not a guarantee.",
        "retirement_projection": None,
    }

    if assumptions and _is_retirement_goal(goal, selected_tags):
        summary["retirement_projection"] = sum(
            projected_account_value(account, assumptions) for account in included_accounts
        )

    return summary


def _build_goal_card(goal, accounts, holdings_totals, assumptions=None):
    selected_tags = _split_tags(goal["selected_tags"]) if "selected_tags" in goal else []
    included_accounts = []

    for account in accounts:
        account_tags = _split_tags(account["tags"]) if "tags" in account else []
        if selected_tags and any(tag in account_tags for tag in selected_tags):
            # Mirror what the Projections page does: override current_value with
            # the effective value (so holdings-based accounts use live holdings totals)
            row = dict(account)
            row["current_value"] = effective_account_value(account, holdings_totals)
            included_accounts.append(row)

    current_total = sum(a["current_value"] for a in included_accounts)
    target = float(goal["target_value"] or 0)
    remaining = remaining_to_goal(current_total, target)

    monthly_contribution = sum(
        projection_monthly_contribution(a, assumptions, 0) for a in included_accounts
    )
    projection = _project_goal(included_accounts, target, assumptions)

    return {
        "id": goal["id"],
        "name": goal["name"],
        "goal_type": goal["goal_type"] or "Tagged Goal",
        "selected_tags": selected_tags,
        "current": current_total,
        "target": target,
        "progress": progress_to_goal(current_total, target),
        "remaining": remaining,
        "account_count": len(included_accounts),
        "notes": goal["notes"] or "",
        "monthly_contribution": monthly_contribution,
        "projection": projection,
        "projection_copy": goal_projection_copy(
            projection,
            monthly_contribution,
            remaining,
            len(included_accounts),
            selected_tags,
        ),
        "source_summary": _build_projection_source_summary(
            goal,
            included_accounts,
            assumptions,
            monthly_contribution,
            selected_tags,
        ),
    }


@goals_bp.route("/", methods=["GET", "POST"])
@login_required
def goals():
    uid = current_user.id
    if request.method == "POST":
        form_name = request.form.get("form_name", "create_goal")

        if form_name == "delete_goal":
            goal_id = optional_int(request.form.get("goal_id"))
            if goal_id:
                delete_goal(goal_id, uid)
            return redirect(url_for("goals.goals"))

        payload = _goal_payload_from_form(request.form)
        if not payload["name"]:
            flash("Goal name is required.", "error")
            return redirect(url_for("goals.goals"))
        goal_id = optional_int(request.form.get("goal_id"))
        if goal_id:
            payload["id"] = goal_id
            if not update_goal(payload, uid):
                flash("Goal not found.", "error")
        else:
            create_goal(payload, uid)
        return redirect(url_for("goals.goals"))

    assumptions = fetch_assumptions(uid)
    accounts = fetch_all_accounts(uid)
    holdings_totals = fetch_holding_totals_by_account(uid)
    start_month = projection_start_month_key(assumptions)
    overrides_by_account = fetch_contribution_overrides_for_accounts([account["id"] for account in accounts])
    accounts = [
        {
            **dict(account),
            "_contribution_overrides": overrides_by_account.get(account["id"], []),
            "_projection_start_month": start_month,
        }
        for account in accounts
    ]
    goal_rows = fetch_all_goals(uid)

    goal_cards = [_build_goal_card(goal, accounts, holdings_totals, assumptions) for goal in goal_rows]

    # Deduplicated total saved: sum each account at most once across all goals
    included_ids = set()
    for goal_row in goal_rows:
        tags = _split_tags(goal_row["selected_tags"]) if goal_row["selected_tags"] else []
        for account in accounts:
            acct_tags = set(_split_tags(account["tags"]) if account["tags"] else [])
            if tags and acct_tags & set(tags):
                included_ids.add(account["id"])
    total_saved = sum(
        effective_account_value(a, holdings_totals)
        for a in accounts if a["id"] in included_ids
    )

    selected_goal = None
    selected_goal_tags = []
    page_mode = request.args.get("mode", "view")
    first_goal_focus = request.args.get("focus") == "first_goal" and not goal_rows and page_mode == "create"
    selected_goal_id = request.args.get("goal_id", type=int)
    if selected_goal_id:
        selected_goal = fetch_goal(selected_goal_id, uid)
        if selected_goal:
            selected_goal_tags = _split_tags(selected_goal["selected_tags"]) if "selected_tags" in selected_goal else []

    return render_template(
        "goals.html",
        goal_cards=goal_cards,
        total_saved=total_saved,
        selected_goal=selected_goal,
        selected_goal_tags=selected_goal_tags,
        tag_options=fetch_user_tags(current_user.id),
        page_mode=page_mode,
        first_goal_focus=first_goal_focus,
        active_page="goals",
    )
