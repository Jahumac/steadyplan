import calendar
from datetime import date, datetime

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from app.calculations import (
    add_months_to_key,
    age_from_dob,
    current_age_from_assumptions,
    effective_account_value,
    projected_account_value,
    projected_account_value_at_month,
    projected_account_value_at_year,
    projected_account_value_no_fees,
    projected_accounts,
    projected_total_retirement_value,
    projection_start_month_key,
    to_float,
    years_to_retirement,
)
from app.models import (
    create_contribution_override,
    delete_contribution_overrides_for_reason,
    fetch_account,
    fetch_all_accounts,
    fetch_all_goals,
    fetch_assumptions,
    fetch_contribution_overrides,
    fetch_contribution_overrides_for_reason,
    fetch_holding_totals_by_account,
)

projections_bp = Blueprint("projections", __name__)


def _year_by_year_chart(accounts, assumptions):
    """Return (labels, values) for projected total, year by year to retirement.

    Uses whole-year steps up to the last full year, then adds a final point at
    the exact fractional retirement date so the chart endpoint matches the
    summary card and breakdown figures.
    """
    if not assumptions:
        return [], []
    current_age = current_age_from_assumptions(assumptions)
    retirement_age = to_float(assumptions["retirement_age"])
    exact_years = years_to_retirement(current_age, retirement_age, assumptions)
    whole_years = int(exact_years)

    labels, values = [], []
    for yr in range(0, whole_years + 1):
        total = sum(
            projected_account_value_at_year(a, assumptions, yr)
            for a in accounts
        )
        label = "Today" if yr == 0 else f"Age {int(current_age + yr)}"
        labels.append(label)
        values.append(round(total, 0))

    # Add final fractional-year point so the chart endpoint matches the card
    if exact_years > whole_years:
        total = sum(
            projected_account_value(a, assumptions)
            for a in accounts
        )
        labels.append(f"Age {int(retirement_age)}")
        values.append(round(total, 0))

    return labels, values


def _month_key_from_date(d):
    return f"{d.year:04d}-{d.month:02d}"


def _date_at_age(dob_str, age):
    if not dob_str:
        return None
    try:
        dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    try:
        year = int(dob.year + int(age))
    except (TypeError, ValueError):
        return None
    day = min(dob.day, calendar.monthrange(year, dob.month)[1])
    return date(year, dob.month, day)


def _age_at_month_key(dob_str, month_key):
    if not dob_str or not month_key:
        return None
    try:
        y, m = [int(x) for x in month_key.split("-")]
        d = date(y, m, 1)
    except (ValueError, TypeError):
        return None
    return age_from_dob(dob_str, today=d)


@projections_bp.route("/api/account-series")
@login_required
def api_account_series():
    uid = current_user.id
    account_id = request.args.get("account_id", type=int)
    mode = (request.args.get("mode") or "yearly").strip().lower()
    if not account_id:
        return jsonify({"ok": False, "error": "account_id required"}), 400
    if mode not in {"yearly", "monthly"}:
        return jsonify({"ok": False, "error": "mode must be yearly or monthly"}), 400

    assumptions = fetch_assumptions(uid)
    if not assumptions:
        return jsonify({"ok": False, "error": "assumptions missing"}), 400

    account = fetch_account(account_id, uid)
    if not account:
        return jsonify({"ok": False, "error": "account not found"}), 404

    holdings_totals = fetch_holding_totals_by_account(uid)
    start_month = projection_start_month_key(assumptions)
    a = dict(account)
    a["current_value"] = effective_account_value(account, holdings_totals)
    a["_contribution_overrides"] = fetch_contribution_overrides(account_id)
    a["_projection_start_month"] = start_month

    current_age = current_age_from_assumptions(assumptions)
    retirement_age = to_float(assumptions["retirement_age"])
    exact_years = years_to_retirement(current_age, retirement_age, assumptions)
    months_total = int(exact_years * 12)
    points = []

    if mode == "yearly":
        whole_years = int(exact_years)
        for yr in range(0, whole_years + 1):
            val = projected_account_value_at_year(a, assumptions, yr)
            mk = add_months_to_key(start_month, int(yr * 12))
            label = "Today" if yr == 0 else f"Age {int(current_age + yr)}"
            points.append({
                "label": label,
                "value": round(val, 0),
                "age": round(current_age + yr, 2),
                "month_key": mk,
            })
        if exact_years > whole_years:
            val = projected_account_value(a, assumptions)
            mk = add_months_to_key(start_month, months_total)
            points.append({
                "label": f"Age {int(retirement_age)}",
                "value": round(val, 0),
                "age": round(retirement_age, 2),
                "month_key": mk,
            })
    else:
        for idx in range(0, months_total + 1):
            mk = add_months_to_key(start_month, idx)
            val = projected_account_value_at_month(a, assumptions, idx)
            points.append({
                "label": mk,
                "value": round(val, 0),
                "age": round(current_age + idx / 12.0, 2),
                "month_key": mk,
            })

    return jsonify({"ok": True, "points": points})


@projections_bp.route("/api/account-schedule", methods=["GET", "POST"])
@login_required
def api_account_schedule():
    uid = current_user.id
    assumptions = fetch_assumptions(uid)
    if not assumptions:
        return jsonify({"ok": False, "error": "assumptions missing"}), 400

    dob = assumptions.get("date_of_birth") if isinstance(assumptions, dict) else assumptions["date_of_birth"]

    if request.method == "GET":
        account_id = request.args.get("account_id", type=int)
        if not account_id:
            return jsonify({"ok": False, "error": "account_id required"}), 400
        overrides = fetch_contribution_overrides_for_reason(account_id, uid, "schedule")
        rules = []
        for ov in overrides:
            mk = ov.get("from_month") if isinstance(ov, dict) else ov["from_month"]
            amt = ov.get("override_amount") if isinstance(ov, dict) else ov["override_amount"]
            rules.append({
                "from_month": mk,
                "start_age": _age_at_month_key(dob, mk),
                "amount": float(amt or 0),
            })
        return jsonify({"ok": True, "rules": rules, "has_dob": bool(dob)})

    data = request.get_json(silent=True) or {}
    account_id = data.get("account_id")
    if not account_id:
        return jsonify({"ok": False, "error": "account_id required"}), 400
    if not fetch_account(int(account_id), uid):
        return jsonify({"ok": False, "error": "account not found"}), 404
    if not dob:
        return jsonify({"ok": False, "error": "date_of_birth required in Settings"}), 400

    rules_in = data.get("rules") or []
    cleaned = []
    for r in rules_in:
        try:
            start_age = int(float(r.get("start_age")))
        except (TypeError, ValueError):
            continue
        try:
            amount = float(r.get("amount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if start_age <= 0:
            continue
        cleaned.append((start_age, amount))

    start_month = projection_start_month_key(assumptions)
    cleaned.sort(key=lambda x: x[0])
    uniq = []
    seen = set()
    for start_age, amount in cleaned:
        if start_age in seen:
            continue
        seen.add(start_age)
        uniq.append((start_age, amount))

    delete_contribution_overrides_for_reason(int(account_id), uid, "schedule")
    if not uniq:
        return jsonify({"ok": True})

    month_keys = []
    for start_age, amount in uniq:
        d = _date_at_age(dob, start_age)
        if not d:
            continue
        mk = _month_key_from_date(d)
        if mk < start_month:
            mk = start_month
        month_keys.append((mk, amount))
    month_keys.sort(key=lambda x: x[0])
    filtered = []
    last_mk = None
    for mk, amount in month_keys:
        if last_mk is not None and mk <= last_mk:
            continue
        last_mk = mk
        filtered.append((mk, amount))

    for i, (from_m, amount) in enumerate(filtered):
        next_m = filtered[i + 1][0] if i + 1 < len(filtered) else None
        to_m = add_months_to_key(next_m, -1) if next_m else "9999-12"
        if to_m < from_m:
            continue
        create_contribution_override(
            {
                "account_id": int(account_id),
                "from_month": from_m,
                "to_month": to_m,
                "override_amount": amount,
                "reason": "schedule",
            },
            user_id=uid,
        )

    return jsonify({"ok": True})


@projections_bp.route("/")
@login_required
def projections():
    uid = current_user.id
    raw_accounts = fetch_all_accounts(uid)
    assumptions = fetch_assumptions(uid)
    holdings_totals = fetch_holding_totals_by_account(uid)

    accounts = []
    start_month = projection_start_month_key(assumptions)
    for account in raw_accounts:
        row = dict(account)
        row["current_value"] = effective_account_value(account, holdings_totals)
        row["_contribution_overrides"] = fetch_contribution_overrides(account["id"])
        row["_projection_start_month"] = start_month
        accounts.append(row)

    account_rows = projected_accounts(accounts, assumptions)
    total_projected = projected_total_retirement_value(accounts, assumptions)
    total_no_fees = sum(projected_account_value_no_fees(a, assumptions) for a in accounts) if assumptions else 0
    total_fee_impact = total_no_fees - total_projected
    computed_age = current_age_from_assumptions(assumptions) if assumptions else 0
    years_remaining = years_to_retirement(computed_age, assumptions["retirement_age"], assumptions) if assumptions else 0
    chart_labels, chart_values = _year_by_year_chart(accounts, assumptions)

    # ── Goals on-track check ─────────────────────────────────────────────────
    goal_rows = fetch_all_goals(uid)
    goal_targets = [
        {"name": g["name"], "target": to_float(g["target_value"])}
        for g in goal_rows if to_float(g["target_value"]) > 0
    ]
    primary_goal = goal_targets[0] if goal_targets else None

    metrics = {
        "growth_rate": float(assumptions["annual_growth_rate"]) if assumptions else 0,
        "retirement_age": assumptions["retirement_age"] if assumptions else 0,
        "current_age": int(computed_age),
        "current_age_frac": computed_age,
        "years_remaining": years_remaining,
        "total_projected": total_projected,
        "total_current": sum(to_float(a["current_value"]) for a in accounts),
        "total_monthly": sum(to_float(r["effective_contribution"]) for r in account_rows),
        "total_fee_impact": total_fee_impact,
    }

    return render_template(
        "projections.html",
        metrics=metrics,
        account_rows=account_rows,
        chart_labels=chart_labels,
        chart_values=chart_values,
        primary_goal=primary_goal,
        active_page="projections",
    )
