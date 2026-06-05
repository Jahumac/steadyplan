import pytz
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, render_template, make_response, request
from flask_login import current_user, login_required

from app.calculations import (
    SCHEDULER_STALE_AFTER_HOURS,
    allowance_progress,
    apply_pension_carry_forward,
    calculate_isa_usage,
    calculate_pension_usage,
    current_age_from_assumptions,
    effective_account_value,
    effective_monthly_contribution,
    goal_current_value,
    is_review_due,
    is_salary_day,
    pension_allowance_limits,
    progress_to_goal,
    projected_total_retirement_value,
    projection_monthly_contribution,
    projection_start_month_key,
    review_ready_date,
    tag_totals,
    to_float,
    total_invested,
    total_monthly_contributions,
    uk_tax_year_label,
    uk_tax_year_start,
    uk_tax_year_end,
    days_until_tax_year_end,
)
from app.models import (
    fetch_all_accounts,
    fetch_all_active_overrides,
    fetch_budget_items,
    fetch_all_debts,
    fetch_all_goals,
    fetch_all_holdings,
    fetch_all_holdings_grouped,
    fetch_assumptions,
    fetch_contribution_overrides,
    fetch_holding_totals_by_account,
    fetch_isa_contributions,
    fetch_isa_overrides_for_tax_year,
    fetch_pension_overrides_for_tax_year,
    fetch_pension_carry_forward,
    fetch_monthly_review,
    fetch_monthly_review_items,
    fetch_pension_contributions,
    fetch_latest_price_update,
    fetch_net_worth_history,
    fetch_primary_goal,
    fetch_daily_snapshots,
    fetch_completed_tax_year_contributions,
)
from app.services.data_health import build_data_health_summary
from app.services.goal_projection import project_goal
from app.services.goal_ui import goal_projection_copy, goal_track_status
from app.services.planning_insights import build_accessible_security_summary

overview_bp = Blueprint("overview", __name__)


def _build_daily_contributions_cumulative(uid, daily_labels, accounts, assumptions):
    """Cumulative contributions credited on each daily snapshot date.

    cumulative[i] = total contributions landed strictly after the first
    snapshot date and on/before daily_labels[i]. The first snapshot's
    value already includes any contributions made on or before that day,
    so anything pre-period is excluded to avoid double-counting.

    Per (account, month):
      1. Skipped (override_amount=0) → £0
      2. Has a monthly_review_item → expected_contribution (user-edited truth)
      3. No review yet → effective_monthly_contribution default; the month
         is added to pending_months so the UI can show "estimated".

    Contributions land on the user's review-ready date (salary day shifted for
    weekends, plus settlement). Months strictly in the future are not counted.
    """
    if not daily_labels:
        return [], []

    salary_day = 28
    try:
        salary_day = max(1, min(31, int((assumptions or {}).get("salary_day") or 28)))
    except (TypeError, ValueError):
        pass

    today = datetime.now().date()

    try:
        first_label_date = datetime.strptime(daily_labels[0], "%Y-%m-%d").date()
        last_label_date = datetime.strptime(daily_labels[-1], "%Y-%m-%d").date()
    except ValueError:
        return [0.0] * len(daily_labels), []

    # Walk months from first snapshot's month to today's month (inclusive).
    pending_months = []
    events = []  # (date, amount)

    y, m = first_label_date.year, first_label_date.month
    end_y, end_m = today.year, today.month
    while (y, m) <= (end_y, end_m):
        mk = f"{y:04d}-{m:02d}"
        invest_date = review_ready_date(y, m, salary_day)
        # Only consider months whose investment date has actually arrived,
        # otherwise we'd inject contributions that haven't happened yet.
        if invest_date <= today and invest_date <= last_label_date:
            review = fetch_monthly_review(mk, uid)
            review_items_by_acc = {}
            if review:
                for item in fetch_monthly_review_items(review["id"]):
                    review_items_by_acc[item["account_id"]] = item

            active_overrides = fetch_all_active_overrides(mk, uid)
            skipped_ids = {
                aid for aid, ov in active_overrides.items()
                if float(ov.get("override_amount") or 0) == 0
            }

            month_total = 0.0
            month_has_estimate = False
            for a in accounts:
                aid = a["id"]
                if aid in skipped_ids:
                    continue
                if aid in review_items_by_acc:
                    # The review stores the *personal* contribution. To match
                    # what's actually landing in the pot (and Performance's
                    # numbers), run it through the full into-pot helper so
                    # SIPP picks up tax relief, Workplace Pension picks up
                    # employer + relief, LISA picks up the bonus, etc.
                    personal = float(review_items_by_acc[aid]["expected_contribution"] or 0)
                    if personal > 0:
                        adjusted = dict(a)
                        adjusted["monthly_contribution"] = personal
                        month_total += effective_monthly_contribution(adjusted, assumptions)
                else:
                    default_amt = effective_monthly_contribution(a, assumptions)
                    if default_amt > 0:
                        month_total += default_amt
                        month_has_estimate = True

            if month_total > 0:
                events.append((invest_date, month_total))
            if month_has_estimate:
                pending_months.append(mk)

        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1

    # Drop events on/before the first snapshot date — already in the start value.
    events = [(d, a) for d, a in events if d > first_label_date]
    events.sort(key=lambda e: e[0])

    cumulative = []
    running = 0.0
    idx = 0
    for label in daily_labels:
        try:
            d = datetime.strptime(label, "%Y-%m-%d").date()
        except ValueError:
            cumulative.append(round(running, 2))
            continue
        while idx < len(events) and events[idx][0] <= d:
            running += events[idx][1]
            idx += 1
        cumulative.append(round(running, 2))

    return cumulative, pending_months


@overview_bp.route("/")
@login_required
def overview():
    uid = current_user.id
    raw_accounts = fetch_all_accounts(uid)
    budget_items = fetch_budget_items(uid)
    budget_item_count = sum(
        1
        for item in budget_items
        if not item.get("linked_account_id") or float(item.get("default_amount") or 0) > 0
    )
    debts = fetch_all_debts(uid)
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

    invested_total = total_invested(accounts, holdings_totals)
    total_debt_balance = round(sum(float(d["current_balance"] or 0) for d in debts), 2)
    has_debts = total_debt_balance > 0
    position_view = request.args.get("position")
    if position_view not in {"assets", "after_debts"}:
        position_view = "assets"
    if position_view == "after_debts" and not has_debts:
        position_view = "assets"

    hero_value = invested_total - total_debt_balance if position_view == "after_debts" else invested_total
    hero_label = "After debts" if position_view == "after_debts" else "Assets"
    hero_helper = None
    if has_debts:
        if position_view == "after_debts":
            hero_helper = f"Subtracting £{total_debt_balance:,.2f} in active debts."
        else:
            hero_helper = f"Active debts kept separate: £{total_debt_balance:,.2f}."

    monthly_total = total_monthly_contributions(accounts, assumptions)
    tag_totals_map = tag_totals(accounts, holdings_totals)
    projected_total = projected_total_retirement_value(accounts, assumptions)

    # Keep a single primary goal for the hero stat + backward compat
    goal = fetch_primary_goal(uid)
    goal_target = float(goal["target_value"]) if goal else 0
    if goal:
        _primary_tags = [t.strip() for t in (goal["selected_tags"] or "").split(",") if t.strip()]
        _primary_current = goal_current_value(_primary_tags, accounts, holdings_totals) if _primary_tags else invested_total
    else:
        _primary_current = invested_total
    goal_progress = progress_to_goal(_primary_current, goal_target)

    current_tax_year = uk_tax_year_label()
    now_date = datetime.now().date()

    all_goals = fetch_all_goals(uid)
    goals_data = []
    for g in all_goals:
        gt = float(g["target_value"] or 0)
        selected_tags = [t.strip() for t in (g["selected_tags"] or "").split(",") if t.strip()]
        included_accounts = []
        if selected_tags:
            for account in accounts:
                account_tags = [t.strip() for t in (account.get("tags") or "").split(",") if t.strip()]
                if any(tag in account_tags for tag in selected_tags):
                    included_accounts.append(account)
        else:
            included_accounts = list(accounts)
        current = sum(float(account.get("current_value") or 0) for account in included_accounts) if selected_tags else invested_total
        gp = progress_to_goal(current, gt)
        monthly_contribution = sum(
            projection_monthly_contribution(account, assumptions, 0) for account in included_accounts
        )
        remaining = max(gt - current, 0)
        projection = project_goal(included_accounts, gt, assumptions)
        goals_data.append({
            "id": g["id"],
            "name": g["name"],
            "target": gt,
            "current": current,
            "progress": gp,
            "remaining": remaining,
            "monthly_contribution": monthly_contribution,
            "projection": projection,
            "track_status": goal_track_status(
                projection,
                monthly_contribution,
                remaining,
                len(included_accounts),
                selected_tags,
            ),
            "projection_copy": goal_projection_copy(
                projection,
                monthly_contribution,
                remaining,
                len(included_accounts),
                selected_tags,
            ),
        })

    # Primary goal year for hero stat
    goal_year = goals_data[0].get("projection", {}).get("eta_label") if goals_data and goals_data[0].get("projection") else None
    try:
        salary_day = int(assumptions["salary_day"]) if assumptions and assumptions["salary_day"] else 0
    except (KeyError, TypeError):
        salary_day = 0
    ty_start_date = uk_tax_year_start(now_date)
    ty_end_date = uk_tax_year_end(now_date)
    ty_start = ty_start_date.isoformat()
    ty_end = ty_end_date.isoformat()
    ad_hoc = fetch_isa_contributions(uid, ty_start, ty_end)
    isa_overrides = fetch_isa_overrides_for_tax_year(uid, ty_start, ty_end)
    review_contribs = fetch_completed_tax_year_contributions(
        uid,
        ty_start_date.strftime("%Y-%m"),
        ty_end_date.strftime("%Y-%m"),
    )
    current_age = current_age_from_assumptions(assumptions) if assumptions else 0
    isa_usage = calculate_isa_usage(
        raw_accounts, ad_hoc, now_date, salary_day,
        isa_overrides=isa_overrides,
        review_contributions=review_contribs,
        lisa_contributions_allowed=(not current_age or current_age < 50),
    )
    isa_used = isa_usage["isa_used"]
    lisa_used = isa_usage["lisa_used"]

    pension_contribs = fetch_pension_contributions(uid, ty_start, ty_end)
    pension_overrides = fetch_pension_overrides_for_tax_year(uid, ty_start, ty_end)
    pension_review_contribs = fetch_completed_tax_year_contributions(
        uid,
        ty_start_date.strftime("%Y-%m"),
        ty_end_date.strftime("%Y-%m"),
    )
    pension_usage = calculate_pension_usage(
        raw_accounts,
        pension_contribs,
        assumptions,
        now_date,
        salary_day,
        pension_overrides=pension_overrides,
        review_contributions=pension_review_contribs,
    )
    pension_limits = pension_allowance_limits(dict(assumptions) if assumptions else {})
    pension_carry_forward_entries = fetch_pension_carry_forward(uid)
    pension_limits_with_carry = apply_pension_carry_forward(
        pension_limits,
        pension_carry_forward_entries,
    )
    pension_allowance = pension_limits_with_carry["effective_allowance"]

    now = datetime.now()

    metrics = {
        "invested_total": invested_total,
        "total_debt_balance": total_debt_balance,
        "monthly_total": monthly_total,
        "tag_totals": tag_totals_map,
        "projected_total": projected_total,
        "goal_target": goal_target,
        "goal_progress": goal_progress,
        "goal_year": goal_year,
        "tax_year": current_tax_year,
        "tax_year_days_left": days_until_tax_year_end(now.date()),
        "current_date": now.strftime("%A, %d %B %Y"),
        "current_time": now.strftime("%H:%M"),
        "isa_allowance": float(assumptions["isa_allowance"]) if assumptions else 0,
        "lisa_allowance": float(assumptions["lisa_allowance"]) if assumptions else 0,
        "pension_allowance": pension_allowance,
        "isa_used": isa_used,
        "lisa_used": lisa_used,
        "pension_used": pension_usage["pension_used"],
        "projected_isa": isa_usage["projected_isa"],
        "projected_lisa": isa_usage["projected_lisa"],
        "projected_pension": pension_usage["projected_total"],
        "isa_progress": allowance_progress(isa_used, float(assumptions["isa_allowance"]) if assumptions else 0),
        "lisa_progress": allowance_progress(lisa_used, float(assumptions["lisa_allowance"]) if assumptions else 0),
        "pension_progress": allowance_progress(pension_usage["pension_used"], pension_allowance),
        "pension_personal_limit": pension_limits_with_carry["personal_relief_limit"],
        "effective_values": {account["id"]: effective_account_value(account, holdings_totals) for account in accounts},
        "has_lisa": any("Lifetime" in (a.get("wrapper_type") or "") or "LISA" in (a.get("wrapper_type") or "") for a in raw_accounts),
    }

    # ── Monthly review nudge ──────────────────────────────────────────────────
    current_month_key = now_date.strftime("%Y-%m")
    review_nudge = False
    review_ready = None
    payday_banner = salary_day and is_salary_day(now_date, salary_day)
    if salary_day:
        review_due = is_review_due(now_date, salary_day)
        if review_due:
            review = fetch_monthly_review(current_month_key, uid)
            if review is None or review["status"] != "complete":
                review_nudge = True
                review_ready = review_ready_date(now_date.year, now_date.month, salary_day)

    history = fetch_net_worth_history(uid)
    history_labels = [h[0] for h in history]
    history_values = [round(h[1], 2) for h in history]

    # Fetch daily snapshots (up to 365 days)
    daily_snapshots = fetch_daily_snapshots(uid, limit=365)
    daily_labels = [d[0] for d in daily_snapshots]
    daily_values = [round(d[1], 2) for d in daily_snapshots]
    last_snapshot_date = daily_labels[-1] if daily_labels else None
    last_price_update = fetch_latest_price_update(uid)
    last_price_update_display = None
    next_update_display = None
    uk = pytz.timezone("Europe/London")
    now_uk = datetime.now(timezone.utc).astimezone(uk)
    lpu_dt_uk = None
    if last_price_update:
        try:
            if isinstance(last_price_update, str) and last_price_update.endswith(" UTC"):
                dt = datetime.strptime(last_price_update, "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)
            else:
                dt = datetime.fromisoformat(str(last_price_update))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            lpu_dt_uk = dt.astimezone(uk)
            last_price_update_display = lpu_dt_uk.strftime("%d %b %H:%M")
        except (ValueError, TypeError):
            last_price_update_display = str(last_price_update)[:16]

    # Compute next expected auto-update time
    if assumptions and bool(assumptions.get("auto_update_prices", 1)):
        try:
            def _hhmm(val, default_h):
                try:
                    p = str(val).strip().split(":")
                    return int(p[0]), int(p[1])
                except (ValueError, IndexError):
                    return default_h, 0
            mh, mm = _hhmm(assumptions.get("update_time_morning", "08:30"), 8)
            eh, em = _hhmm(assumptions.get("update_time_evening", "22:00"), 22)
            win_start = now_uk.replace(hour=mh, minute=mm, second=0, microsecond=0)
            win_end   = now_uk.replace(hour=eh, minute=em, second=0, microsecond=0)

            if lpu_dt_uk:
                candidate = lpu_dt_uk + timedelta(hours=1)
            else:
                candidate = now_uk.replace(hour=mh, minute=mm, second=0, microsecond=0)

            # Normalize to a future slot inside the configured window
            if now_uk < win_start:
                candidate = win_start
            elif now_uk > win_end:
                candidate = (now_uk + timedelta(days=1)).replace(hour=mh, minute=mm, second=0, microsecond=0)
            else:
                if candidate <= now_uk:
                    candidate = now_uk + timedelta(hours=1)
                if candidate < win_start:
                    candidate = win_start
                if candidate > win_end:
                    candidate = (now_uk + timedelta(days=1)).replace(hour=mh, minute=mm, second=0, microsecond=0)

            if candidate.date() == now_uk.date():
                next_update_display = candidate.strftime("%H:%M")
            else:
                next_update_display = "Tomorrow " + candidate.strftime("%H:%M")
        except (ValueError, TypeError):
            next_update_display = None

    # ── Alerts ────────────────────────────────────────────────────────────────
    alerts = []

    # Price stale: only nag if auto-update is on and prices haven't refreshed in 24h
    if assumptions and assumptions["auto_update_prices"]:
        price_stale = True
        if last_price_update:
            try:
                if isinstance(last_price_update, str) and last_price_update.endswith(" UTC"):
                    lpu_dt = datetime.strptime(last_price_update, "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)
                else:
                    lpu_dt = datetime.fromisoformat(str(last_price_update))
                    if lpu_dt.tzinfo is None:
                        lpu_dt = lpu_dt.replace(tzinfo=timezone.utc)
                price_stale = (datetime.now(timezone.utc) - lpu_dt).total_seconds() > SCHEDULER_STALE_AFTER_HOURS * 3600
            except (ValueError, TypeError):
                price_stale = True
        if price_stale:
            alerts.append({
                "kind": "warning",
                "message": "Prices haven't updated in over 24 hours — the scheduler may have missed a window.",
                "cta_text": "Refresh prices now",
                "cta_href": None,
                "cta_form_action": "/holdings/trigger-price-update",
            })

    # ISA projected to exceed allowance
    isa_allowance_val = float(assumptions["isa_allowance"]) if assumptions and assumptions["isa_allowance"] else 0
    if isa_allowance_val > 0 and metrics["projected_isa"] > isa_allowance_val:
        over = metrics["projected_isa"] - isa_allowance_val
        alerts.append({
            "kind": "danger",
            "message": f"At your current contribution pace, you're estimated to exceed your ISA allowance by £{over:,.0f} this tax year.",
            "cta_text": "Review ISA allowance",
            "cta_href": "/allowance/",
        })

    # Pension projected to exceed allowance
    if pension_allowance > 0 and metrics["projected_pension"] > pension_allowance:
        over = metrics["projected_pension"] - pension_allowance
        alerts.append({
            "kind": "danger",
            "message": f"At your current contribution pace, you're estimated to exceed your pension annual allowance by £{over:,.0f} this tax year.",
            "cta_text": "Review pension annual allowance",
            "cta_href": "/allowance/#pension",
        })

    # Tax year ending soon with unused ISA allowance
    days_left = metrics["tax_year_days_left"]
    isa_remaining = isa_allowance_val - metrics["isa_used"]
    if 0 < days_left <= 30 and isa_remaining > 500:
        alerts.append({
            "kind": "info",
            "message": f"{days_left} days left in the tax year — £{isa_remaining:,.0f} of your ISA allowance is still unused.",
            "cta_text": "Record ISA top-up",
            "cta_href": "/allowance/#isa-log-panel",
        })

    # Unlinked holdings: held via "holdings" valuation but no catalogue link → won't auto-price
    if assumptions and assumptions.get("auto_update_prices"):
        all_holdings = fetch_all_holdings(uid)
        unlinked = [h for h in all_holdings if not h.get("holding_catalogue_id") and h.get("ticker")]
        if unlinked:
            count = len(unlinked)
            alerts.append({
                "kind": "info",
                "message": f"{count} holding{'s' if count != 1 else ''} {'have' if count != 1 else 'has'} a ticker but no price source linked — {'their' if count != 1 else 'its'} price won't refresh here.",
                "cta_text": "Link price sources",
                "cta_href": "/holdings/",
            })

    premium_bond_accounts = [
        a for a in accounts
        if (a.get("wrapper_type") or "").lower() == "premium bonds"
    ]
    premium_bonds_total = sum(float(a.get("current_value") or 0) for a in premium_bond_accounts)
    if premium_bonds_total > 50000:
        alerts.append({
            "kind": "warning",
            "message": f"Your Premium Bonds total is £{premium_bonds_total:,.0f}. NS&I's current maximum eligible holding is £50,000.",
            "cta_text": "Review Premium Bonds",
            "cta_href": "/accounts/",
        })

    # Nudge to set investment day if accounts exist but salary_day is not configured
    if not salary_day and raw_accounts:
        alerts.append({
            "kind": "info",
            "message": "Set your investment day in Settings — it tells SteadyPlan when to remind you to do your monthly update.",
            "cta_text": "Set your investment day",
            "cta_href": "/settings/?mode=edit",
            "cta_form_action": None,
        })

    # Missed last-month review: past the ready date and review not complete
    if salary_day:
        lm_year, lm_month = (now_date.year - 1, 12) if now_date.month == 1 else (now_date.year, now_date.month - 1)
        lm_key = f"{lm_year}-{lm_month:02d}"
        lm_ready = review_ready_date(lm_year, lm_month, salary_day)
        if now_date >= lm_ready:
            lm_review = fetch_monthly_review(lm_key, uid)
            if lm_review is None or lm_review["status"] != "complete":
                lm_label = datetime(lm_year, lm_month, 1).strftime("%B")
                alerts.append({
                    "kind": "warning",
                    "message": f"Your {lm_label} monthly update is still open — complete it so balances, contributions, and tracking stay based on confirmed numbers.",
                    "cta_text": "Open monthly update",
                    "cta_href": f"/monthly-review/?month={lm_key}",
                    "cta_form_action": None,
                })

    # Unconfirmed contributions: review is complete but some contributions weren't ticked off
    current_review = fetch_monthly_review(current_month_key, uid)
    if current_review and current_review["status"] == "complete":
        review_items = fetch_monthly_review_items(current_review["id"])
        active_overrides = fetch_all_active_overrides(current_month_key, uid)
        skipped_ids = {
            aid for aid, ov in active_overrides.items()
            if float(ov.get("override_amount") or 0) == 0
        }
        unconfirmed = [
            item for item in review_items
            if (item.get("expected_contribution") or 0) > 0
            and not item.get("contribution_confirmed")
            and item["account_id"] not in skipped_ids
        ]
        if unconfirmed:
            names = ", ".join(item["account_name"] for item in unconfirmed[:3])
            if len(unconfirmed) > 3:
                names += f" and {len(unconfirmed) - 3} more"
            alerts.append({
                "kind": "info",
                "message": f"Your {now_date.strftime('%B')} update is done but {len(unconfirmed)} contribution{'s' if len(unconfirmed) != 1 else ''} weren't confirmed — did they all arrive? ({names})",
                "cta_text": "Open monthly update",
                "cta_href": f"/monthly-review/?month={current_month_key}",
                "cta_form_action": None,
            })


    next_action = None
    if raw_accounts:
        if review_nudge:
            next_action = {
                "eyebrow": "Your next nudge",
                "title": "Monthly update is ready",
                "body": "A quick check keeps your history honest. Update balances, confirm contributions, then SteadyPlan can draw the next little line.",
                "cta_text": "Open monthly update",
                "cta_href": "/monthly-review/",
            }
        elif not goals_data:
            next_action = {
                "eyebrow": "Your next nudge",
                "title": "Give this money a destination",
                "body": "A goal turns the dashboard from a pile of numbers into a plan. Retirement, emergency fund, house deposit — one target is enough to start.",
                "cta_text": "Create a goal",
                "cta_href": "/goals/?mode=create&focus=first_goal",
            }
        elif not history_labels:
            next_action = {
                "eyebrow": "Your next nudge",
                "title": "Save your first snapshot",
                "body": "Complete one Monthly Update to create a proper starting point for progress, performance, and projections.",
                "cta_text": "Do first update",
                "cta_href": "/monthly-review/?focus=first_update",
            }
        elif not salary_day:
            next_action = {
                "eyebrow": "Your next nudge",
                "title": "Set your monthly rhythm",
                "body": "Add your investment day so SteadyPlan knows when the month is ready to review, instead of nudging at the wrong time.",
                "cta_text": "Open settings",
                "cta_href": "/settings/?mode=edit",
            }

    alert_cta_targets = {alert.get("cta_href") for alert in alerts if alert.get("cta_href")}
    next_action_href = next_action.get("cta_href") if next_action else None
    show_next_action = bool(
        next_action
        and next_action_href not in alert_cta_targets
        and not (review_nudge and next_action_href == "/monthly-review/")
        and not (payday_banner and next_action_href == "/budget/")
    )

    # ── Asset allocation by individual holding ────────────────────────────────
    all_holdings_grouped = fetch_all_holdings_grouped(uid)
    holding_totals: dict = {}
    for h in all_holdings_grouped:
        name = (h["holding_name"] or "Unknown").strip() or "Unknown"
        val = float(h["value"] or 0)
        if val > 0:
            holding_totals[name] = holding_totals.get(name, 0) + val
    # Sort by value descending
    allocation = sorted(
        holding_totals.items(),
        key=lambda x: -x[1],
    )
    allocation_labels = [a[0] for a in allocation]
    allocation_values = [round(a[1], 2) for a in allocation]

    assumed_rate_pct = round(to_float((assumptions or {}).get("annual_growth_rate", 0.07)) * 100, 1)
    access_summary = build_accessible_security_summary(accounts, assumptions)

    daily_contributions, pending_review_months = _build_daily_contributions_cumulative(
        uid, daily_labels, accounts, assumptions
    )

    data_health_summary = build_data_health_summary(uid)

    onboarding_complete = bool(
        assumptions
        and assumptions.get("date_of_birth")
        and raw_accounts
        and goals_data
        and history_labels
    )

    mr_review = fetch_monthly_review(current_month_key, uid)
    if mr_review is None:
        mr_status = "Not started"
        mr_badge_class = "badge badge-meta"
    else:
        mr_status = "Complete" if mr_review.get("status") == "complete" else "In progress"
        mr_badge_class = "badge badge-complete" if mr_review.get("status") == "complete" else "badge badge-meta"

    monthly_review_card = None
    if onboarding_complete and not review_nudge:
        monthly_review_card = {
            "month_key": current_month_key,
            "month_label": datetime(now_date.year, now_date.month, 1).strftime("%B %Y"),
            "status": mr_status,
            "badge_class": mr_badge_class,
            "href": f"/monthly-review/?month={current_month_key}",
        }

    # Render the response and ensure it's not cached by the browser
    resp = make_response(render_template(
        "overview.html",
        metrics=metrics,
        accounts=accounts,
        goals_data=goals_data,
        assumptions=assumptions,
        assumed_rate_pct=assumed_rate_pct,
        history_labels=history_labels,
        history_values=history_values,
        daily_labels=daily_labels,
        daily_values=daily_values,
        daily_contributions=daily_contributions,
        pending_review_months=pending_review_months,
        last_snapshot_date=last_snapshot_date,
        last_price_update=last_price_update,
        last_price_update_display=last_price_update_display,
        next_update_display=next_update_display,
        review_nudge=review_nudge,
        review_ready=review_ready,
        payday_banner=payday_banner,
        alerts=alerts,
        next_action=next_action,
        show_next_action=show_next_action,
        allocation_labels=allocation_labels,
        allocation_values=allocation_values,
        active_page="overview",
        current_month_num=now.month,
        data_health_summary=data_health_summary,
        monthly_review_card=monthly_review_card,
        access_summary=access_summary,
        hero_label=hero_label,
        hero_value=hero_value,
        hero_helper=hero_helper,
        has_debts=has_debts,
        budget_item_count=budget_item_count,
        position_view=position_view,
    ))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@overview_bp.route("/refresh-prices", methods=["POST"])
@login_required
def refresh_prices():
    """Manually trigger a price update.

    This is now a FORCED update — it bypasses the 15-minute freshness check
    to ensure the user sees an immediate result and can verify API keys.
    """
    from flask import current_app, redirect, url_for
    from app.services.scheduler import _run_price_update_for_user

    # We pass slot_name="manual" which our scheduler treats as a forced update
    _run_price_update_for_user(current_app, current_user.id, slot_name="manual")

    return redirect(url_for("overview.overview"))
