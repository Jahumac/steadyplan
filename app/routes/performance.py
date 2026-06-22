from datetime import datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.calculations import (
    _resolve_contribution_day,
    compute_performance_series,
    contribution_breakdown,
    effective_monthly_contribution,
    review_ready_date,
    to_float,
    uk_tax_year_start,
    uk_tax_year_end,
    uk_tax_year_label,
)
from app.models import (
    add_cash_flow_event,
    add_account_transfer_events,
    delete_cash_flow_event,
    fetch_all_accounts,
    fetch_all_active_overrides,
    fetch_account_daily_snapshot_points_on_or_after_date,
    fetch_account_daily_snapshot_points_on_or_before_date,
    fetch_assumptions,
    fetch_cash_flow_events_for_account,
    fetch_daily_snapshots,
    fetch_holding_totals_by_account,
    fetch_monthly_performance_data,
    fetch_monthly_performance_data_by_account,
    fetch_monthly_review,
    fetch_monthly_review_items,
    fetch_tax_year_contributions,
    get_connection,
    upsert_monthly_snapshot,
)
from app.services.financial_truth import refresh_account_snapshots_for_month

performance_bp = Blueprint("performance", __name__)


def _parse_money(value, default=None):
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _valid_month_key(value):
    try:
        datetime.strptime(str(value or ""), "%Y-%m")
        return True
    except ValueError:
        return False


def _existing_monthly_snapshot_balance(account_id, month_key):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT balance FROM monthly_snapshots WHERE account_id = ? AND month_key = ?",
            (account_id, month_key),
        ).fetchone()
    return None if row is None else float(row["balance"] or 0)


def _recent_performance_event_rows(accounts, user_id, limit=8):
    account_names = {int(a["id"]): a["name"] for a in accounts}
    rows = []
    for account_id, account_name in account_names.items():
        for event in fetch_cash_flow_events_for_account(account_id, user_id, limit=50):
            effect = (event.get("allowance_effect") or "none")
            if effect not in {"performance_only", "transfer_neutral"}:
                continue
            amount = float(event.get("amount") or 0)
            counterparty_id = event.get("counterparty_account_id")
            counterparty_name = account_names.get(int(counterparty_id)) if counterparty_id else None
            rows.append(
                {
                    "id": event["id"],
                    "account_name": account_name,
                    "counterparty_name": counterparty_name,
                    "event_date": event.get("event_date") or "",
                    "amount": amount,
                    "kind": event.get("kind") or "movement",
                    "note": event.get("note") or "",
                    "allowance_effect": effect,
                    "signed_label": f"{'+' if amount >= 0 else '−'}£{abs(amount):,.2f}",
                }
            )
    rows.sort(key=lambda r: (r["event_date"], r["id"]), reverse=True)
    return rows[:limit]


@performance_bp.route("/cash-flow-events", methods=["POST"])
@login_required
def record_cash_flow_event():
    uid = current_user.id
    accounts = fetch_all_accounts(uid)
    account_map = {int(a["id"]): a for a in accounts}
    try:
        account_id = int(request.form.get("account_id") or 0)
    except (TypeError, ValueError):
        account_id = 0
    if account_id not in account_map:
        flash("Choose one of your accounts before recording a performance movement.", "error")
        return redirect(url_for("performance.performance"))

    raw_date = (request.form.get("event_date") or "").strip()
    try:
        event_date = datetime.strptime(raw_date, "%Y-%m-%d").date().isoformat()
    except ValueError:
        flash("Enter the movement date as YYYY-MM-DD.", "error")
        return redirect(url_for("performance.performance"))

    amount = _parse_money(request.form.get("amount"), 0.0) or 0.0
    if abs(amount) < 0.005:
        flash("Enter an amount for the performance movement.", "error")
        return redirect(url_for("performance.performance"))

    kind = (request.form.get("kind") or "deposit").strip().lower()
    if kind in {"withdrawal", "transfer_out"}:
        signed_amount = -abs(amount)
        kind = "withdrawal"
    else:
        signed_amount = abs(amount)
        kind = "deposit"

    opening_month = (request.form.get("opening_month") or "").strip()
    opening_value = _parse_money(request.form.get("opening_value"), None)
    if opening_month or opening_value is not None:
        if not _valid_month_key(opening_month) or opening_value is None or opening_value < 0:
            flash("Opening baseline needs a YYYY-MM month and a non-negative value.", "error")
            return redirect(url_for("performance.performance"))
        existing_opening_value = _existing_monthly_snapshot_balance(account_id, opening_month)
        replace_existing_opening = request.form.get("replace_existing_opening") == "1"
        if existing_opening_value is not None and abs(existing_opening_value - opening_value) >= 0.005 and not replace_existing_opening:
            flash(
                f"Opening baseline for {opening_month} is already £{existing_opening_value:,.2f}. Tick replace existing baseline to overwrite it.",
                "error",
            )
            return redirect(url_for("performance.performance"))
        upsert_monthly_snapshot(account_id, opening_month, opening_value)

    note = (request.form.get("note") or "Manual performance movement").strip()
    event_id = add_cash_flow_event(
        {
            "account_id": account_id,
            "event_date": event_date,
            "amount": signed_amount,
            "kind": kind,
            "note": note,
            "allowance_effect": "performance_only",
        },
        uid,
    )
    if not event_id:
        flash("Could not record that performance movement.", "error")
        return redirect(url_for("performance.performance"))

    account_name = account_map[account_id]["name"]
    if opening_month and opening_value is not None:
        flash(
            f"Recorded {account_name} opening baseline £{opening_value:,.2f} and {kind} £{abs(signed_amount):,.2f}.",
            "success",
        )
    else:
        flash(f"Recorded {account_name} {kind} £{abs(signed_amount):,.2f} for Performance.", "success")
    return redirect(url_for("performance.performance"))


@performance_bp.route("/cash-flow-events/<int:event_id>/delete", methods=["POST"])
@login_required
def delete_performance_cash_flow_event(event_id):
    deleted = delete_cash_flow_event(event_id, current_user.id, allowance_effect="performance_only")
    if deleted:
        flash("Removed that Performance movement. Account balances and snapshots were not changed.", "success")
    else:
        flash("That Performance movement was not found or has already been removed.", "error")
    return redirect(url_for("performance.performance"))


@performance_bp.route("/account-transfers", methods=["POST"])
@login_required
def record_account_transfer():
    uid = current_user.id
    accounts = fetch_all_accounts(uid)
    account_map = {int(a["id"]): a for a in accounts}
    try:
        from_account_id = int(request.form.get("from_account_id") or 0)
        to_account_id = int(request.form.get("to_account_id") or 0)
    except (TypeError, ValueError):
        from_account_id = 0
        to_account_id = 0

    if from_account_id not in account_map or to_account_id not in account_map:
        flash("Choose two of your accounts for the transfer.", "error")
        return redirect(url_for("performance.performance"))
    if from_account_id == to_account_id:
        flash("Choose two different accounts for the transfer.", "error")
        return redirect(url_for("performance.performance"))

    raw_date = (request.form.get("event_date") or "").strip()
    try:
        event_date = datetime.strptime(raw_date, "%Y-%m-%d").date().isoformat()
    except ValueError:
        flash("Enter the transfer date as YYYY-MM-DD.", "error")
        return redirect(url_for("performance.performance"))

    amount = _parse_money(request.form.get("amount"), 0.0) or 0.0
    if amount < 0.005:
        flash("Enter an amount for the account transfer.", "error")
        return redirect(url_for("performance.performance"))

    note = (request.form.get("note") or "Account transfer").strip()
    event_ids = add_account_transfer_events(
        {
            "from_account_id": from_account_id,
            "to_account_id": to_account_id,
            "event_date": event_date,
            "amount": amount,
            "note": note,
        },
        uid,
    )
    if not event_ids:
        flash("Could not record that account transfer.", "error")
        return redirect(url_for("performance.performance"))

    from_name = account_map[from_account_id]["name"]
    to_name = account_map[to_account_id]["name"]
    flash(f"Recorded transfer £{abs(amount):,.2f} from {from_name} to {to_name}.", "success")
    return redirect(url_for("performance.performance"))


@performance_bp.route("/")
@login_required
def performance():
    uid = current_user.id
    current_month_key = datetime.now().strftime('%Y-%m')
    refresh_account_snapshots_for_month(uid, current_month_key, require_existing_month=True)
    assumptions   = fetch_assumptions(uid)
    accounts      = fetch_all_accounts(uid)
    current_monthly_update_href = f"/monthly-review/?month={current_month_key}#expected-contributions"

    assumed_rate   = to_float(assumptions["annual_growth_rate"]) if assumptions else 0.07

    # Daily snapshots for the chart (same as overview)
    daily_snapshots = fetch_daily_snapshots(uid, limit=730)
    snapshot_count = len(daily_snapshots)
    has_data = snapshot_count >= 2
    has_snapshot_history = snapshot_count >= 1
    export_period_links = [
        {"label": "1M", "href": "/performance/export.xlsx?period=1M"},
        {"label": "6M", "href": "/performance/export.xlsx?period=6M"},
        {"label": "1Y", "href": "/performance/export.xlsx?period=1Y"},
        {"label": "ALL", "href": "/performance/export.xlsx?period=ALL"},
    ]

    daily_labels   = []  # raw YYYY-MM-DD for client-side period filtering
    daily_actual   = []
    daily_plan     = []
    plan_value     = None
    current_value  = None
    monthly_contribution_total = None
    planned_monthly_avg = None
    performance_summary = None
    account_reconciliation_rows = []
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
        monthly_performance_data = fetch_monthly_performance_data(uid)
        performance_summary = compute_performance_series(
            monthly_performance_data,
            assumed_rate,
            monthly_contribution_total or 0,
        )
        per_account_monthly_data = fetch_monthly_performance_data_by_account(uid)
        for aid, payload in per_account_monthly_data.items():
            rows = payload.get("rows") or []
            if not rows:
                continue
            perf_acc = compute_performance_series(rows, assumed_rate, 0)
            if not perf_acc:
                continue
            gain = float(perf_acc.get("total_market_gain") or 0)
            account_reconciliation_rows.append({
                "account_id": aid,
                "account_name": payload.get("account_name") or "Account",
                "imported_baseline": float(perf_acc.get("total_imported_baseline") or 0),
                "contributed": float(perf_acc.get("total_contributed") or 0),
                "gain": gain,
                "current_value": float(perf_acc.get("current_value") or 0),
            })
        account_reconciliation_rows.sort(key=lambda r: -r["current_value"])

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

            def account_contribution_date(a, year, month):
                try:
                    account_day = int((a or {}).get("pension_contribution_day") or 0)
                except (TypeError, ValueError):
                    account_day = 0
                day = account_day or salary_day
                return datetime(year, month, _resolve_contribution_day(year, month, day)).date()

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
                active_overrides, items_by_acc = month_ctx(mk)
                month_amount = 0.0
                for a in accounts:
                    credit_date = account_contribution_date(a, y, m)
                    if credit_date <= today and credit_date <= end_date and credit_date > start_date:
                        amt = into_pot_for_account_month(a, mk, active_overrides, items_by_acc)
                        month_amount += amt
                        if amt > 0:
                            events.append((credit_date, mk, amt))
                if month_amount > 0:
                    month_amount_cache[mk] = month_amount
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

        def account_contribution_date_for_breakdown(a, year, month):
            try:
                account_day = int((a or {}).get("pension_contribution_day") or 0)
            except (TypeError, ValueError):
                account_day = 0
            day = account_day or salary_day
            return datetime(year, month, _resolve_contribution_day(year, month, day)).date()

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
                cd = account_contribution_date_for_breakdown(a, y, m)
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
        has_snapshot_history=has_snapshot_history,
        snapshot_count=snapshot_count,
        daily_labels=daily_labels,
        daily_actual=daily_actual,
        daily_plan=daily_plan,
        assumed_rate_pct=round(assumed_rate * 100, 1),
        monthly_contribution_total=monthly_contribution_total,
        planned_monthly_avg=planned_monthly_avg,
        contribution_breakdown_rows=contribution_breakdown_rows,
        account_reconciliation_rows=account_reconciliation_rows,
        performance_summary=performance_summary,
        account_perf=account_perf,
        account_breakdown=account_breakdown,
        plan_value=plan_value,
        current_value=current_value,
        current_monthly_update_href=current_monthly_update_href,
        export_period_links=export_period_links,
        performance_event_accounts=accounts,
        recent_performance_events=_recent_performance_event_rows(accounts, uid),
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
