from datetime import datetime, timedelta

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.calculations import (
    contribution_breakdown,
    effective_monthly_contribution,
    review_ready_date,
    to_float,
    uk_tax_year_start,
    uk_tax_year_end,
    uk_tax_year_label,
)
from app.models import (
    fetch_all_accounts,
    fetch_all_active_overrides,
    fetch_account_daily_snapshot_points_on_or_after_date,
    fetch_account_daily_snapshot_points_on_or_before_date,
    fetch_assumptions,
    fetch_cash_flow_events_for_account,
    fetch_daily_snapshots,
    fetch_holding_totals_by_account,
    fetch_monthly_review,
    fetch_monthly_review_items,
    fetch_tax_year_contributions,
)

performance_bp = Blueprint("performance", __name__)


@performance_bp.route("/")
@login_required
def performance():
    uid = current_user.id
    assumptions   = fetch_assumptions(uid)
    accounts      = fetch_all_accounts(uid)
    current_monthly_update_href = f"/monthly-review/?month={datetime.now().strftime('%Y-%m')}#expected-contributions"

    assumed_rate   = to_float(assumptions["annual_growth_rate"]) if assumptions else 0.07

    # Daily snapshots for the chart (same as overview)
    daily_snapshots = fetch_daily_snapshots(uid, limit=730)
    snapshot_count = len(daily_snapshots)
    has_data = snapshot_count >= 2

    daily_labels   = []  # raw YYYY-MM-DD for client-side period filtering
    daily_actual   = []
    daily_plan     = []
    plan_value     = None
    current_value  = None
    monthly_contribution_total = None
    planned_monthly_avg = None
    contribution_breakdown_rows = []

    if has_data:
        # Plan = where you should be if you'd been contributing on schedule and
        # earning `assumed_rate`.
        #
        # Unlike the old "flat £X/mo at month boundaries" approach, this matches
        # how the rest of the app thinks about contributions:
        # - overrides can skip or adjust months
        # - monthly review (if present) is the source of truth for that month
        # - otherwise we fall back to each account's default monthly contribution
        # Contributions are credited on the user's salary day (resolved for short
        # months/weekends), and are only counted once their date has arrived.
        monthly_contribution_total = sum(
            effective_monthly_contribution(a, assumptions) for a in accounts
        )

        # Per-account breakdown so the user can see exactly which accounts feed
        # into the plan total — and spot stale `monthly_contribution` values on
        # accounts they no longer pay into at that level.
        for a in accounts:
            br = contribution_breakdown(a, assumptions)
            if br["total_into_pot"] <= 0:
                continue
            contribution_breakdown_rows.append({
                "name": a["name"],
                "personal": br["personal"],
                "tax_relief": br["tax_relief"],
                "government_bonus": br["government_bonus"],
                "employer": br["employer"],
                "contribution_fee": br["contribution_fee"],
                "total_into_pot": br["total_into_pot"],
                "method_label": br["method_label"],
            })
        contribution_breakdown_rows.sort(key=lambda r: -r["total_into_pot"])

        start_date_str, start_val = daily_snapshots[0]
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        except ValueError:
            start_date = None

        end_date_str = daily_snapshots[-1][0]
        try:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            end_date = None

        # Walk day-by-day from start to end, applying daily compound growth and
        # adding the month-specific contribution on the review-ready date
        # (salary day, shifted for weekends, plus settlement).
        # Sample on snapshot days so the plan line aligns with the actual line.
        plan_by_date = {}
        if start_date and end_date:
            salary_day = 28
            try:
                salary_day = int((assumptions or {}).get("salary_day") or 28)
            except (TypeError, ValueError):
                salary_day = 28
            salary_day = max(1, min(31, salary_day))

            today = datetime.now().date()
            daily_rate = (1 + assumed_rate) ** (1 / 365.25) - 1

            month_ctx_cache = {}
            def month_ctx(mk):
                if mk in month_ctx_cache:
                    return month_ctx_cache[mk]
                active_overrides = fetch_all_active_overrides(mk, uid)
                review = fetch_monthly_review(mk, uid)
                items_by_acc = {}
                if review and (review.get("status") == "complete"):
                    for it in fetch_monthly_review_items(review["id"]):
                        items_by_acc[int(it["account_id"])] = it
                month_ctx_cache[mk] = (active_overrides or {}, items_by_acc)
                return month_ctx_cache[mk]

            def into_pot_for_account_month(a, mk, active_overrides, items_by_acc):
                aid = int(a["id"])
                personal = None
                ov = (active_overrides or {}).get(aid)
                if ov is not None:
                    personal = float(ov.get("override_amount") or 0)
                elif aid in (items_by_acc or {}):
                    personal = float((items_by_acc[aid] or {}).get("expected_contribution") or 0)
                if personal is not None:
                    if personal <= 0:
                        return 0.0
                    adjusted = dict(a)
                    adjusted["monthly_contribution"] = personal
                    return float(effective_monthly_contribution(adjusted, assumptions) or 0)
                return float(effective_monthly_contribution(a, assumptions) or 0)

            def month_total_for(mk):
                active_overrides, items_by_acc = month_ctx(mk)
                total = 0.0
                for a in accounts:
                    total += into_pot_for_account_month(a, mk, active_overrides, items_by_acc)
                return total

            month_amount_cache = {}   # mk -> portfolio total

            # Pre-build contribution events so month_key and credit_date don't
            # drift when the review-ready date lands in the next month.
            events = []  # (credit_date, mk, amount)
            y, m = start_date.year, start_date.month
            end_y, end_m = end_date.year, end_date.month
            while (y, m) <= (end_y, end_m):
                mk = f"{y:04d}-{m:02d}"
                credit_date = review_ready_date(y, m, salary_day)
                if credit_date <= today and credit_date <= end_date and credit_date > start_date:
                    amt = month_total_for(mk)
                    month_amount_cache[mk] = amt
                    if amt > 0:
                        events.append((credit_date, mk, amt))
                if m == 12:
                    y, m = y + 1, 1
                else:
                    m += 1
            events.sort(key=lambda e: e[0])
            event_idx = 0

            value = start_val
            plan_by_date[start_date] = value
            cur = start_date
            while cur < end_date:
                nxt = cur + timedelta(days=1)
                value *= (1 + daily_rate)
                while event_idx < len(events) and events[event_idx][0] == nxt:
                    value += events[event_idx][2]
                    event_idx += 1

                cur = nxt
                plan_by_date[cur] = value

            if month_amount_cache:
                planned_monthly_avg = sum(month_amount_cache.values()) / max(1, len(month_amount_cache))

        for date_str, val in daily_snapshots:
            try:
                snap_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                snap_date = None
            daily_labels.append(date_str)
            daily_actual.append(round(val, 2))
            plan_val = plan_by_date.get(snap_date) if snap_date else None
            daily_plan.append(round(plan_val, 2) if plan_val is not None else None)

        current_value = daily_actual[-1]
        plan_value    = daily_plan[-1]

    # By Account — live values only, no monthly snapshot dependency
    holding_totals = fetch_holding_totals_by_account(uid)
    account_perf = []
    for a in accounts:
        if a.get("valuation_mode") == "holdings":
            cv = float(holding_totals.get(a["id"], 0))
        else:
            cv = to_float(a.get("current_value"))
        if cv > 0:
            account_perf.append({"account_id": a["id"], "account_name": a["name"], "current_value": cv})
    account_perf.sort(key=lambda x: -x["current_value"])

    # Per-account "ahead/behind" using the same end-date as the portfolio chart.
    account_breakdown = []
    if has_data and start_date and end_date:
        start_pts_before = fetch_account_daily_snapshot_points_on_or_before_date(uid, start_date_str)
        start_pts_after = fetch_account_daily_snapshot_points_on_or_after_date(uid, start_date_str)
        end_pts = fetch_account_daily_snapshot_points_on_or_before_date(uid, end_date_str)

        salary_day = 28
        try:
            salary_day = int((assumptions or {}).get("salary_day") or 28)
        except (TypeError, ValueError):
            salary_day = 28
        salary_day = max(1, min(31, salary_day))

        today = datetime.now().date()
        daily_rate = (1 + assumed_rate) ** (1 / 365.25) - 1

        for a in accounts:
            aid = int(a["id"])
            end_pt = end_pts.get(aid)

            # Show the row even if this account has no snapshot history yet.
            # This commonly happens for Premium Bonds / manual accounts if the
            # user hasn't run a refresh since creating the account.
            if not end_pt:
                cv = None
                if a.get("valuation_mode") == "holdings":
                    cv = float(holding_totals.get(a["id"], 0))
                else:
                    cv = to_float(a.get("current_value"))
                account_breakdown.append({
                    "account_id": aid,
                    "account_name": a["name"],
                    "actual_end": cv,
                    "plan_end": None,
                    "diff": None,
                    "untracked": True,
                })
                continue

            try:
                end_d = datetime.strptime(end_pt["snapshot_date"], "%Y-%m-%d").date()
            except ValueError:
                continue
            end_val = float(end_pt["value"] or 0)

            base_pt = start_pts_before.get(aid) or start_pts_after.get(aid)
            if base_pt:
                try:
                    base_d = datetime.strptime(base_pt["snapshot_date"], "%Y-%m-%d").date()
                except ValueError:
                    base_d = end_d
                base_val = float(base_pt["value"] or 0)
            else:
                base_d = end_d
                base_val = end_val

            value = base_val
            cur = base_d
            events = []

            y, m = cur.year, cur.month
            end_y, end_m = end_d.year, end_d.month
            while (y, m) <= (end_y, end_m):
                mk = f"{y:04d}-{m:02d}"
                cd = review_ready_date(y, m, salary_day)
                if cd <= today and cd <= end_d and cd > base_d:
                    active_overrides, items_by_acc = month_ctx(mk)
                    amt = into_pot_for_account_month(a, mk, active_overrides, items_by_acc)
                    if amt > 0:
                        events.append((cd, amt))
                if m == 12:
                    y, m = y + 1, 1
                else:
                    m += 1

            wrapper = (a.get("wrapper_type") or "").strip().lower()
            if wrapper == "cash isa":
                from_date = (base_d + timedelta(days=1)).isoformat()
                to_date = end_d.isoformat()
                for e in fetch_cash_flow_events_for_account(aid, uid, from_date=from_date, to_date=to_date, limit=500):
                    try:
                        ed = datetime.strptime(str(e.get("event_date") or "")[:10], "%Y-%m-%d").date()
                    except Exception:
                        continue
                    if ed <= base_d or ed > end_d or ed > today:
                        continue
                    try:
                        amt = float(e.get("amount") or 0)
                    except (TypeError, ValueError):
                        continue
                    if amt:
                        events.append((ed, amt))
            events.sort(key=lambda e: e[0])
            idx = 0

            while cur < end_d:
                nxt = cur + timedelta(days=1)
                value *= (1 + daily_rate)
                while idx < len(events) and events[idx][0] == nxt:
                    value += events[idx][1]
                    idx += 1
                cur = nxt

            plan_end = value
            diff = end_val - plan_end
            account_breakdown.append({
                "account_id": aid,
                "account_name": a["name"],
                "actual_end": end_val,
                "plan_end": plan_end,
                "diff": diff,
                "untracked": False,
            })

        account_breakdown.sort(key=lambda r: (1 if r.get("untracked") else 0, -(abs(r["diff"]) if r.get("diff") is not None else 0.0)))

    return render_template(
        "performance.html",
        has_data=has_data,
        snapshot_count=snapshot_count,
        daily_labels=daily_labels,
        daily_actual=daily_actual,
        daily_plan=daily_plan,
        assumed_rate_pct=round(assumed_rate * 100, 1),
        monthly_contribution_total=monthly_contribution_total,
        planned_monthly_avg=planned_monthly_avg,
        contribution_breakdown_rows=contribution_breakdown_rows,
        account_perf=account_perf,
        account_breakdown=account_breakdown,
        plan_value=plan_value,
        current_value=current_value,
        current_monthly_update_href=current_monthly_update_href,
        active_page="performance",
    )


@performance_bp.route("/contributions/")
@login_required
def contribution_summary():
    uid = current_user.id
    today = datetime.now().date()
    current_monthly_update_href = f"/monthly-review/?month={today.strftime('%Y-%m')}#expected-contributions"
    ty_start = uk_tax_year_start(today)
    ty_end   = uk_tax_year_end(today)
    from_month = ty_start.strftime("%Y-%m")
    to_month   = ty_end.strftime("%Y-%m")

    rows = fetch_tax_year_contributions(uid, from_month, to_month)

    # Build month list for the tax year (Apr through Mar, only past/current months)
    months = []
    y, m = ty_start.year, ty_start.month
    current_ym = today.strftime("%Y-%m")
    while True:
        mk = f"{y:04d}-{m:02d}"
        if mk > current_ym:
            break
        months.append(mk)
        m += 1
        if m > 12:
            m = 1
            y += 1
        if mk > to_month:
            break

    # Index rows by (account_id, month_key)
    data = {}      # {account_id: {"name": str, "wrapper_type": str, "months": {mk: {expected, confirmed}}}}
    for r in rows:
        aid = r["account_id"]
        if aid not in data:
            data[aid] = {
                "name": r["account_name"],
                "wrapper_type": r["wrapper_type"],
                "months": {},
            }
        data[aid]["months"][r["month_key"]] = {
            "expected": float(r["expected_contribution"] or 0),
            "confirmed": bool(r["contribution_confirmed"]),
            "skipped": bool(r["is_skipped"]),
        }

    # Sort accounts by name
    accounts = sorted(data.values(), key=lambda a: a["name"])

    # Month display labels
    month_labels = []
    for mk in months:
        try:
            month_labels.append(datetime.strptime(mk, "%Y-%m").strftime("%b %Y"))
        except ValueError:
            month_labels.append(mk)

    # Column totals
    month_totals = {}
    for mk in months:
        month_totals[mk] = sum(
            a["months"].get(mk, {}).get("expected", 0) for a in accounts
        )

    return render_template(
        "contribution_summary.html",
        accounts=accounts,
        months=months,
        month_labels=month_labels,
        month_totals=month_totals,
        tax_year=uk_tax_year_label(today),
        current_monthly_update_href=current_monthly_update_href,
        active_page="performance",
    )
