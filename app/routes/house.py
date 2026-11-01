"""The House page — one screen for the deposit.

Why this exists: every other view answers "what have I got?" or "when will I get
there?". A house purchase asks a different question — *will I have enough by the
date I need it?* — and before this the app could not answer it at all, because
goals had no target date.

It reuses the Goals page's account selection (`_included_accounts_for_goal`) and the
same projection engine, so the numbers here can never disagree with Progress.
"""
from datetime import date, datetime

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.calculations import (
    projected_account_value_at_month,
    projection_monthly_contribution,
    projection_start_month_key,
)
from app.models import (
    fetch_all_accounts,
    fetch_all_goals,
    fetch_assumptions,
    fetch_contribution_overrides_for_accounts,
    fetch_holding_totals_by_account,
    fetch_isa_one_off_inflows,
    group_inflows_by_account,
)
from app.routes.goals import _included_accounts_for_goal
from app.utils import split_tags as _split_tags

house_bp = Blueprint("house", __name__)

HOUSE_TAG = "house"


def months_between(start, end):
    """Whole months from `start` to `end`, counting part-months as a month.

    A completion date of 2029-05-15 and today of 2026-11-01 is 31 months, not 30,
    because the deposit is needed somewhere inside that month.
    """
    if not end or end <= start:
        return 0
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day > start.day:
        months += 1
    return max(months, 0)


def find_house_goal(goal_rows):
    """The goal that represents the house.

    Tag match wins over a name match, because tags decide which accounts fund it.
    """
    tagged = []
    named = []
    for goal in goal_rows:
        tags = [t.lower() for t in _split_tags(goal["selected_tags"] or "")]
        if HOUSE_TAG in tags:
            tagged.append(goal)
        elif "house" in (goal["name"] or "").lower():
            named.append(goal)
    return (tagged or named or [None])[0]


def build_house_plan(goal, accounts, holdings_totals, assumptions,
                     one_off_inflows_by_account=None, today=None):
    """Everything the House page shows, or a reason it cannot show anything."""
    today = today or date.today()
    if goal is None:
        return {"state": "no_goal"}

    included = _included_accounts_for_goal(
        goal, accounts, holdings_totals, one_off_inflows_by_account
    )
    target = float(goal["target_value"] or 0)
    current_total = sum(a["current_value"] for a in included)

    raw_date = None
    try:
        raw_date = goal["target_date"]
    except (KeyError, IndexError, TypeError):
        raw_date = None
    target_date = None
    if raw_date:
        try:
            target_date = datetime.strptime(str(raw_date)[:10], "%Y-%m-%d").date()
        except ValueError:
            target_date = None

    monthly = sum(
        projection_monthly_contribution(a, assumptions, 0) for a in included
    )

    plan = {
        "state": "ok",
        "goal_id": goal["id"],
        "name": goal["name"],
        "target": target,
        "current": current_total,
        "remaining": max(target - current_total, 0.0),
        "progress": min(current_total / target * 100, 100.0) if target > 0 else 0.0,
        "monthly": monthly,
        "target_date": target_date,
        "target_date_raw": str(raw_date)[:10] if raw_date else "",
        "accounts": [
            {
                "name": a["name"],
                "wrapper": a["wrapper_type"],
                "current": a["current_value"],
                "monthly": projection_monthly_contribution(a, assumptions, 0),
                "inflows": len(a.get("_one_off_inflows") or []),
            }
            for a in included
        ],
    }

    # Already there?
    if target > 0 and current_total >= target:
        plan["status"] = "reached"
        return plan

    # No date -> we can still show progress, but cannot say on-track or short.
    if target_date is None:
        plan["status"] = "no_date"
        return plan

    if target_date <= today:
        plan["status"] = "past_due"
        plan["months"] = 0
        plan["projected"] = current_total
        plan["gap"] = target - current_total
        return plan

    months = months_between(today, target_date)
    projected = sum(
        projected_account_value_at_month(a, assumptions, months) for a in included
    )
    gap = target - projected

    plan.update({
        "months": months,
        "projected": projected,
        "gap": gap,
        "status": "on_track" if gap <= 0 else "short",
        "per_month_needed": (gap / months) if gap > 0 and months else 0.0,
    })
    return plan


def _load_accounts(uid):
    """Accounts prepared exactly as the Goals page prepares them."""
    assumptions = fetch_assumptions(uid)
    accounts = fetch_all_accounts(uid)
    holdings_totals = fetch_holding_totals_by_account(uid)
    start_month = projection_start_month_key(assumptions)
    overrides = fetch_contribution_overrides_for_accounts([a["id"] for a in accounts])
    inflows = group_inflows_by_account(fetch_isa_one_off_inflows(uid))
    prepared = [
        {
            **dict(account),
            "_contribution_overrides": overrides.get(account["id"], []),
            "_projection_start_month": start_month,
            "_one_off_inflows": inflows.get(int(account["id"]), []),
        }
        for account in accounts
    ]
    return assumptions, prepared, holdings_totals, inflows


@house_bp.route("/")
@login_required
def house():
    uid = current_user.id
    assumptions, accounts, holdings_totals, inflows = _load_accounts(uid)
    goal = find_house_goal(fetch_all_goals(uid))
    plan = build_house_plan(goal, accounts, holdings_totals, assumptions, inflows)
    return render_template("house.html", plan=plan, active_page="house")
