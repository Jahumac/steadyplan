from datetime import date, datetime, timezone

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.calculations import (
    ISA_WRAPPER_TYPES,
    contribution_breakdown,
    effective_account_value,
    effective_monthly_contribution,
    is_pension_account,
    to_float,
    uk_tax_year_end,
    uk_tax_year_label,
    uk_tax_year_start,
    review_ready_date,
)
from app.models import (
    CATEGORY_OPTIONS,
    DEFAULT_TAG_OPTIONS,
    WRAPPER_TYPE_OPTIONS,
    add_custom_tag,
    add_holding,
    add_holding_catalogue_item,
    add_isa_contribution,
    create_account,
    delete_account,
    delete_custom_tag,
    delete_holding,
    delete_prize,
    fetch_account,
    fetch_all_accounts,
    fetch_catalogue_with_prices,
    fetch_contribution_overrides,
    fetch_cash_flow_events_for_account,
    add_cash_flow_event,
    delete_cash_flow_event,
    fetch_custom_tags,
    fetch_hidden_tags,
    hide_default_tag,
    tag_in_use_count,
    fetch_holding,
    fetch_holding_catalogue,
    fetch_holding_totals_by_account,
    fetch_holdings_for_account,
    fetch_isa_contributions,
    fetch_pension_contributions,
    fetch_prizes,
    fetch_prizes_tax_year,
    fetch_user_tags,
    log_prize,
    reconnect_holdings_to_catalogue,
    sync_holding_prices_from_catalogue,
    fetch_assumptions,
    fetch_latest_price_update,
    fetch_account_daily_snapshots,
    fetch_monthly_performance_data_by_account,
    save_account_daily_snapshots,
    save_daily_snapshot,
    update_account,
    update_catalogue_price,
    update_holding,
)
from app.services.prices import fetch_price, lookup_instrument, to_gbp
from app.utils import optional_float, optional_int, split_tags, valid_month_key

ASSET_TYPE_OPTIONS = ["ETF", "Fund", "Share", "Pension Fund", "Cash", "Bond", "Other"]
BUCKET_OPTIONS = [
    "Global Equity",
    "Developed World Equity",
    "Emerging Markets Equity",
    "UK Equity",
    "Bonds",
    "Cash",
    "Property / REIT",
    "Other",
]


accounts_bp = Blueprint("accounts", __name__)


def _account_payload_from_form(form):
    return {
        "name": form.get("name", ""),
        "provider": form.get("provider", ""),
        "wrapper_type": form.get("wrapper_type", ""),
        "category": form.get("category", ""),
        "tags": ", ".join(t.strip() for t in form.getlist("tags") if t.strip()),
        "current_value": optional_float(form.get("current_value"), 0.0, min_val=0.0),
        "monthly_contribution": optional_float(form.get("monthly_contribution"), 0.0, min_val=0.0),
        "pension_contribution_day": max(0, min(31, optional_int(form.get("pension_contribution_day"), default=0))),
        "goal_value": optional_float(form.get("goal_value"), None, min_val=0.0),
        "valuation_mode": form.get("valuation_mode", "manual"),
        "growth_mode": form.get("growth_mode", "default"),
        "growth_rate_override": optional_float(form.get("growth_rate_override"), None, divide_by_100=True),
        "owner": form.get("owner", ""),
        "notes": form.get("notes", ""),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "employer_contribution": optional_float(form.get("employer_contribution"), 0.0, min_val=0.0),
        "contribution_method": form.get("contribution_method", "standard"),
        "annual_fee_pct": optional_float(form.get("annual_fee_pct"), 0.0, min_val=0.0),
        "platform_fee_pct": optional_float(form.get("platform_fee_pct"), 0.0, min_val=0.0),
        "platform_fee_flat": optional_float(form.get("platform_fee_flat"), 0.0, min_val=0.0),
        "platform_fee_cap": optional_float(form.get("platform_fee_cap"), 0.0, min_val=0.0),
        "fund_fee_pct": optional_float(form.get("fund_fee_pct"), 0.0, min_val=0.0),
        "contribution_fee_pct": optional_float(form.get("contribution_fee_pct"), 0.0, min_val=0.0),
        "cash_interest_rate": optional_float(form.get("cash_interest_rate"), None, divide_by_100=True),
        "interest_payment_day": max(0, min(31, optional_int(form.get("interest_payment_day"), default=0))),
        "include_in_budget": "1" in form.getlist("include_in_budget"),
        "pre_salary": "1" in form.getlist("pre_salary"),
    }


def _render_accounts_page(user_id, selected=None, detail_mode="view", position_error=None, position_added=False, edit_holding_id=None):
    rows = fetch_all_accounts(user_id)
    assumptions = fetch_assumptions(user_id)
    holdings_totals = fetch_holding_totals_by_account(user_id)
    effective_values = {row["id"]: effective_account_value(row, holdings_totals) for row in rows}
    contrib_breakdowns = {row["id"]: contribution_breakdown(row, assumptions) for row in rows}

    # Tax-year logged contributions per account: sum of isa/pension contributions
    # logged against each account this UK tax year. Empty for taxable (GIA) accounts.
    today = date.today()
    ty_start_iso = uk_tax_year_start(today).isoformat()
    ty_end_iso = uk_tax_year_end(today).isoformat()
    tax_year_logged = {}
    for c in fetch_isa_contributions(user_id, ty_start_iso, ty_end_iso) or []:
        aid = int(c["account_id"])
        tax_year_logged[aid] = tax_year_logged.get(aid, 0.0) + float(c["amount"] or 0)
    for c in fetch_pension_contributions(user_id, ty_start_iso, ty_end_iso) or []:
        aid = int(c["account_id"])
        tax_year_logged[aid] = tax_year_logged.get(aid, 0.0) + float(c["amount"] or 0)

    # Which accounts get the "Logged {tax year}" stat cell — uses canonical
    # ISA wrapper set + pension predicate so new wrapper labels don't silently
    # miss the strip.
    tax_advantaged_ids = {
        int(row["id"]) for row in rows
        if (row["wrapper_type"] if "wrapper_type" in row.keys() else "") in ISA_WRAPPER_TYPES
        or is_pension_account(dict(row))
    }

    # Staleness: flag holdings-based accounts if prices > 7 days old
    prices_stale = False
    last_price_update = fetch_latest_price_update(user_id)
    if last_price_update:
        try:
            lpu = datetime.fromisoformat(str(last_price_update).replace(" UTC", "+00:00"))
            if lpu.tzinfo is None:
                lpu = lpu.replace(tzinfo=timezone.utc)
            prices_stale = (datetime.now(timezone.utc) - lpu).days >= 7
        except (ValueError, TypeError):
            prices_stale = True
    else:
        prices_stale = any(r["valuation_mode"] == "holdings" for r in rows)
    positions = fetch_holdings_for_account(selected["id"]) if selected else []
    if positions:
        positions = sorted(
            positions,
            key=lambda p: (-(float(p["value"] or 0)), (p["holding_name"] or "").lower()),
        )
    catalogue_rows = fetch_catalogue_with_prices(user_id)
    catalogue_prices = {row["id"]: {"price": row["last_price"], "currency": row["price_currency"]} for row in catalogue_rows if row["last_price"]}
    overrides = fetch_contribution_overrides(selected["id"]) if selected else []
    cash_flow_events = []
    account_monthly_labels = []
    account_monthly_values = []
    account_monthly_plan7 = []
    account_monthly_planglobal = []
    account_daily_labels = []
    account_daily_values = []
    account_daily_plan7 = []
    account_daily_planglobal = []
    goal_eta_7 = None
    goal_eta_global = None
    if selected:
        global_rate = float(assumptions["annual_growth_rate"]) if assumptions and assumptions.get("annual_growth_rate") else 0.05
        wrapper = (selected.get("wrapper_type") or "").strip().lower()
        if wrapper == "cash isa":
            cash_flow_events = fetch_cash_flow_events_for_account(
                int(selected["id"]),
                user_id,
                limit=200,
            )

        monthly_rows = (fetch_monthly_performance_data_by_account(user_id).get(int(selected["id"])) or {}).get("rows", [])
        if monthly_rows:
            account_monthly_labels = [m for (m, _b, _c) in monthly_rows][-36:]
            balances = [float(b or 0) for (_m, b, _c) in monthly_rows][-36:]
            personal_contribs = [float(c or 0) for (_m, _b, c) in monthly_rows][-36:]
            account_monthly_values = [round(v, 2) for v in balances]

            base_account = dict(selected)
            into_pot_contribs = []
            for personal in personal_contribs:
                if personal and personal > 0:
                    adjusted = dict(base_account)
                    adjusted["monthly_contribution"] = float(personal)
                    into_pot_contribs.append(float(effective_monthly_contribution(adjusted, assumptions) or 0))
                else:
                    into_pot_contribs.append(0.0)

            if wrapper == "cash isa" and cash_flow_events:
                month_event_totals = {}
                for e in cash_flow_events:
                    ds = (e.get("event_date") or "")[:10]
                    if len(ds) >= 7:
                        mk = ds[:7]
                        try:
                            month_event_totals[mk] = month_event_totals.get(mk, 0.0) + float(e.get("amount") or 0)
                        except (TypeError, ValueError):
                            continue
                for i, mk in enumerate(account_monthly_labels):
                    if i < len(into_pot_contribs):
                        into_pot_contribs[i] = float(into_pot_contribs[i] or 0) + float(month_event_totals.get(mk, 0.0) or 0)

            def _plan(bals, cfs_into_pot, rate):
                if not bals:
                    return []
                start = float(bals[0] or 0)
                out = [round(start, 2)]
                cur = start
                mr = float(rate or 0) / 12.0
                for i in range(1, len(bals)):
                    cur = cur * (1 + mr) + float(cfs_into_pot[i] or 0)
                    out.append(round(cur, 2))
                return out

            account_monthly_plan7 = _plan(balances, into_pot_contribs, 0.07)
            account_monthly_planglobal = _plan(balances, into_pot_contribs, global_rate)

        daily_history = fetch_account_daily_snapshots(selected["id"], limit=365)
        account_daily_labels = [d for (d, _) in daily_history]
        account_daily_values = [round(v, 2) for (_, v) in daily_history]
        if account_daily_labels and account_daily_values:
            try:
                from datetime import datetime as _dt
                from datetime import timedelta

                base_date = _dt.fromisoformat(account_daily_labels[0][:10]).date()
                base_val = float(account_daily_values[0] or 0)

                salary_day = 0
                try:
                    salary_day = int((assumptions or {}).get("salary_day") or 0)
                except (TypeError, ValueError):
                    salary_day = 0
                contrib_day = salary_day
                try:
                    pd = int((selected.get("pension_contribution_day") or 0))
                    if pd > 0:
                        contrib_day = pd
                except (TypeError, ValueError):
                    pass

                def override_for_month(mk):
                    for ov in overrides or []:
                        if (ov.get("from_month") or "") <= mk <= (ov.get("to_month") or ""):
                            try:
                                return float(ov.get("override_amount") or 0)
                            except (TypeError, ValueError):
                                return 0.0
                    return None

                personal_by_month = {}
                for (mk, _bal, contrib) in monthly_rows or []:
                    try:
                        personal_by_month[str(mk)] = float(contrib or 0)
                    except (TypeError, ValueError):
                        personal_by_month[str(mk)] = 0.0

                base_account = dict(selected)

                def _daily_plan(rate):
                    r = float(rate or 0)
                    out = []
                    cur = base_val
                    prev = base_date
                    out.append(round(cur, 2))
                    today = datetime.now().date()

                    last_date = _dt.fromisoformat(account_daily_labels[-1][:10]).date()
                    events = []
                    if contrib_day:
                        y, m = base_date.year, base_date.month
                        end_y, end_m = last_date.year, last_date.month
                        while (y, m) <= (end_y, end_m):
                            mk = f"{y:04d}-{m:02d}"
                            credit_date = review_ready_date(y, m, max(1, min(31, contrib_day)))
                            if credit_date > base_date and credit_date <= today and credit_date <= last_date:
                                personal = override_for_month(mk)
                                if personal is None:
                                    personal = personal_by_month.get(mk)
                                if personal is None:
                                    personal = float(base_account.get("monthly_contribution") or 0)
                                if personal and personal > 0:
                                    adjusted = dict(base_account)
                                    adjusted["monthly_contribution"] = float(personal)
                                    amt = float(effective_monthly_contribution(adjusted, assumptions) or 0)
                                    if amt > 0:
                                        events.append((credit_date, amt))
                            if m == 12:
                                y, m = y + 1, 1
                            else:
                                m += 1
                        events.sort(key=lambda e: e[0])
                    event_idx = 0

                    cash_events = []
                    if wrapper == "cash isa" and cash_flow_events:
                        for e in cash_flow_events:
                            try:
                                d = _dt.fromisoformat(str(e.get("event_date") or "")[:10]).date()
                            except Exception:
                                continue
                            if d <= base_date or d > last_date:
                                continue
                            try:
                                amt = float(e.get("amount") or 0)
                            except (TypeError, ValueError):
                                continue
                            if amt:
                                cash_events.append((d, amt))
                        cash_events.sort(key=lambda x: x[0])
                    cash_idx = 0

                    for ds in account_daily_labels[1:]:
                        d = _dt.fromisoformat(ds[:10]).date()
                        step = prev + timedelta(days=1)
                        while step <= d:
                            cur *= (1 + (r / 365.25))
                            while event_idx < len(events) and events[event_idx][0] == step:
                                cur += events[event_idx][1]
                                event_idx += 1
                            while cash_idx < len(cash_events) and cash_events[cash_idx][0] == step:
                                cur += cash_events[cash_idx][1]
                                cash_idx += 1
                            step += timedelta(days=1)
                        out.append(round(cur, 2))
                        prev = d
                    return out

                account_daily_plan7 = _daily_plan(0.07)
                account_daily_planglobal = _daily_plan(global_rate)
            except Exception:
                account_daily_plan7 = []
                account_daily_planglobal = []

        try:
            goal = float(selected.get("goal_value") or 0)
        except (TypeError, ValueError):
            goal = 0.0
        current_eff = float(effective_values.get(int(selected["id"]), 0) or 0)
        if goal > 0 and current_eff > 0 and current_eff < goal:
            base_account = dict(selected)
            monthly_into_pot = float(effective_monthly_contribution(base_account, assumptions) or 0)

            def _months_to_goal(current, monthly, annual_rate, target, max_months=1200):
                if current >= target:
                    return 0
                if monthly <= 0 and annual_rate <= 0:
                    return None
                v = float(current)
                mr = float(annual_rate) / 12.0
                for i in range(1, max_months + 1):
                    v = v * (1 + mr) + float(monthly)
                    if v >= target:
                        return i
                return None

            def _eta_label(months):
                if months is None:
                    return None
                if months <= 0:
                    return "goal hit"
                today = date.today()
                y = today.year
                m = today.month + int(months)
                y += (m - 1) // 12
                m = (m - 1) % 12 + 1
                return date(y, m, 1).strftime("%b %Y")

            goal_eta_7 = _eta_label(_months_to_goal(current_eff, monthly_into_pot, 0.07, goal))
            goal_eta_global = _eta_label(_months_to_goal(current_eff, monthly_into_pot, global_rate, goal))

    edit_holding = None
    if edit_holding_id and positions:
        for p in positions:
            if p["id"] == edit_holding_id:
                edit_holding = p
                break

    # Premium Bonds prize history for selected account
    pb_prizes = []
    pb_prizes_ty_total = 0.0
    pb_month_options = []
    if selected and selected.get("valuation_mode") == "premium_bonds":
        pb_prizes = fetch_prizes(selected["id"], user_id)
        ty_start_month = uk_tax_year_start(today).strftime("%Y-%m")
        ty_end_month = uk_tax_year_end(today).strftime("%Y-%m")
        pb_prizes_ty_total = fetch_prizes_tax_year(selected["id"], user_id, ty_start_month, ty_end_month)
        # Last 18 months as (value, label) for the month select
        import calendar as _cal
        logged_keys = {p["month_key"] for p in pb_prizes}
        for i in range(18):
            m = today.month - i
            y = today.year
            while m <= 0:
                m += 12
                y -= 1
            key = f"{y}-{m:02d}"
            label = f"{_cal.month_name[m]} {y}"
            pb_month_options.append((key, label, key in logged_keys))

    allocation_rows = []
    allocation_total = 0.0
    if selected and positions:
        for position in positions:
            allocation_total += float(position["value"] or 0)
        if allocation_total > 0:
            allocation_rows = sorted(
                [
                    {
                        "bucket": position["holding_name"],
                        "value": float(position["value"] or 0),
                        "percentage": (float(position["value"] or 0) / allocation_total) * 100,
                    }
                    for position in positions
                    if float(position["value"] or 0) > 0
                ],
                key=lambda r: r["value"],
                reverse=True,
            )

    return render_template(
        "accounts.html",
        accounts=rows,
        selected=selected,
        detail_mode=detail_mode,
        now_date=today,
        holdings_totals=holdings_totals,
        effective_values=effective_values,
        total_value=sum(effective_values.values()),
        total_monthly=sum(float(r["monthly_contribution"] or 0) for r in rows),
        total_personal_monthly=sum(float(b.get("personal", 0) or 0) for b in contrib_breakdowns.values()),
        total_into_pot_monthly=sum(float(b.get("total_into_pot", 0) or 0) for b in contrib_breakdowns.values()),
        contrib_breakdowns=contrib_breakdowns,
        active_page="accounts",
        wrapper_type_options=WRAPPER_TYPE_OPTIONS,
        category_options=CATEGORY_OPTIONS,
        tag_options=fetch_user_tags(user_id),
        custom_tags=fetch_custom_tags(user_id),
        default_tags=DEFAULT_TAG_OPTIONS,
        hidden_tags=fetch_hidden_tags(user_id),
        selected_tags=split_tags(selected['tags']) if selected and 'tags' in selected else [],
        positions=positions,
        catalogue_rows=catalogue_rows,
        asset_type_options=ASSET_TYPE_OPTIONS,
        bucket_options=BUCKET_OPTIONS,
        position_error=position_error,
        position_added=position_added,
        allocation_rows=allocation_rows,
        allocation_total=allocation_total,
        overrides=overrides,
        current_month_key=date.today().strftime("%Y-%m"),
        tax_year_logged=tax_year_logged,
        tax_year_label=uk_tax_year_label(today),
        tax_advantaged_ids=tax_advantaged_ids,
        catalogue_prices=catalogue_prices,
        edit_holding=edit_holding,
        tax_band=assumptions["tax_band"] if assumptions and "tax_band" in assumptions else "basic",
        account_monthly_labels=account_monthly_labels,
        account_monthly_values=account_monthly_values,
        account_monthly_plan7=account_monthly_plan7,
        account_monthly_planglobal=account_monthly_planglobal,
        account_daily_labels=account_daily_labels,
        account_daily_values=account_daily_values,
        account_daily_plan7=account_daily_plan7,
        account_daily_planglobal=account_daily_planglobal,
        global_growth_rate=float(assumptions["annual_growth_rate"]) if assumptions and assumptions["annual_growth_rate"] else 0.05,
        goal_eta_7=goal_eta_7,
        goal_eta_global=goal_eta_global,
        prices_stale=prices_stale,
        cash_flow_events=cash_flow_events,
        pb_prizes=pb_prizes,
        pb_prizes_ty_total=pb_prizes_ty_total,
        pb_month_options=pb_month_options,
    )


@accounts_bp.route("/<int:account_id>/cash-events/add", methods=["POST"])
@login_required
def add_cash_event(account_id):
    uid = current_user.id
    acc = fetch_account(account_id, uid)
    if not acc:
        flash("Account not found.", "error")
        return redirect(url_for("accounts.accounts"))

    wrapper = (acc.get("wrapper_type") or "").strip().lower()
    if wrapper != "cash isa":
        flash("Cash flow events are only available for Cash ISA accounts.", "error")
        return redirect(url_for("accounts.account_detail", account_id=account_id))

    event_date = (request.form.get("cash_event_date") or "").strip()
    kind = (request.form.get("cash_event_kind") or "transfer_out").strip()
    note = (request.form.get("cash_event_note") or "").strip()
    to_account_id = request.form.get("cash_event_to_account_id") or ""

    amt_raw = request.form.get("cash_event_amount") or ""
    try:
        amt = float(amt_raw)
    except (TypeError, ValueError):
        amt = 0.0
    amt = abs(amt)
    if not event_date or amt <= 0:
        flash("Enter a date and a positive amount.", "error")
        return redirect(url_for("accounts.account_detail", account_id=account_id) + "#acctMonthlyChart")

    signed = amt
    if kind in ("transfer_out", "withdrawal"):
        signed = -amt

    payload = {
        "account_id": account_id,
        "event_date": event_date[:10],
        "amount": signed,
        "kind": kind,
        "counterparty_account_id": int(to_account_id) if str(to_account_id).isdigit() else None,
        "note": note,
    }
    added = add_cash_flow_event(payload, uid)
    if not added:
        flash("Could not save cash flow event.", "error")
    else:
        flash("Cash flow event saved.", "success")
    return redirect(url_for("accounts.account_detail", account_id=account_id) + "#acctMonthlyChart")


@accounts_bp.route("/<int:account_id>/cash-events/<int:event_id>/delete", methods=["POST"])
@login_required
def delete_cash_event(account_id, event_id):
    uid = current_user.id
    acc = fetch_account(account_id, uid)
    if not acc:
        flash("Account not found.", "error")
        return redirect(url_for("accounts.accounts"))
    delete_cash_flow_event(event_id, uid)
    flash("Cash flow event removed.", "success")
    return redirect(url_for("accounts.account_detail", account_id=account_id) + "#acctMonthlyChart")


@accounts_bp.route("/", methods=["GET", "POST"])
@login_required
def accounts():
    uid = current_user.id
    if request.method == "POST":
        payload = _account_payload_from_form(request.form)
        if not payload["name"].strip():
            flash("Account name is required.", "error")
            return redirect(url_for("accounts.accounts"))
        new_id = create_account(payload, uid)
        return redirect(url_for("accounts.accounts"))

    return _render_accounts_page(uid, detail_mode="list")


@accounts_bp.route("/api/tags", methods=["POST"])
@login_required
def api_add_tag():
    """JSON API: add a custom tag for the current user."""
    tag = (request.form.get("tag") or "").strip()
    if not tag:
        return jsonify({"ok": False, "error": "Tag cannot be empty"}), 400
    if len(tag) > 50:
        return jsonify({"ok": False, "error": "Tag too long (max 50 chars)"}), 400
    added = add_custom_tag(current_user.id, tag)
    return jsonify({"ok": True, "added": added, "tag": tag})


@accounts_bp.route("/api/tags/delete", methods=["POST"])
@login_required
def api_delete_tag():
    """JSON API: delete or hide a tag for the current user.

    Returns in_use_count > 0 as a warning on the first call (force=0).
    Pass force=1 to proceed despite accounts using the tag.
    """
    uid = current_user.id
    tag = (request.form.get("tag") or "").strip()
    force = request.form.get("force") == "1"
    if not tag:
        return jsonify({"ok": False, "error": "Tag cannot be empty"}), 400

    count = tag_in_use_count(uid, tag)
    if count > 0 and not force:
        return jsonify({"ok": False, "in_use": True, "count": count, "tag": tag})

    if tag in DEFAULT_TAG_OPTIONS:
        hide_default_tag(uid, tag)
    else:
        delete_custom_tag(uid, tag)
    return jsonify({"ok": True, "tag": tag})


@accounts_bp.route("/api/create", methods=["POST"])
@login_required
def api_create_account():
    """JSON API: create account and return its ID (used by the wizard JS)."""
    uid = current_user.id
    payload = _account_payload_from_form(request.form)
    if not payload["name"].strip():
        return jsonify({"ok": False, "error": "Account name is required"}), 400
    new_id = create_account(payload, uid)
    return jsonify({"ok": True, "account_id": new_id})


@accounts_bp.route("/api/ticker-lookup", methods=["POST"])
@login_required
def api_ticker_lookup():
    """JSON API: look up a ticker via live market data providers and return name + price.

    Used by the wizard to validate tickers and show a live price preview
    before the account is created.
    """
    ticker = (request.form.get("ticker") or "").strip().upper()
    if not ticker:
        return jsonify({"ok": False, "error": "Enter a ticker symbol"}), 400

    instrument = None
    try:
        instrument = lookup_instrument(ticker)
    except Exception as e:
        current_app.logger.warning("lookup_instrument(%s) failed: %s", ticker, e)

    if not instrument:
        return jsonify({"ok": False, "error": f"Shelly couldn't find '{ticker}' via live market data providers. Double-check the symbol or add manually instead."}), 404

    price_gbp = instrument["price_gbp"]
    return jsonify({
        "ok": True,
        "ticker": instrument["ticker"],
        "yf_symbol": instrument.get("yf_symbol", ticker),
        "name": instrument["name"],
        "asset_type": instrument["asset_type"],
        "price": round(price_gbp, 4),
        "currency": instrument["currency"],
    })


def _add_holding_by_ticker(uid, account_id, ticker, units):
    """Shared logic: look up ticker price, create catalogue entry, and add holding.

    Returns a result dict on success. Raises ValueError with a user-facing message on failure.
    """
    price_data = fetch_price(ticker)
    if not price_data:
        raise ValueError(f"Couldn't fetch a price for '{ticker}'. Check the ticker and try again.")

    price_raw = price_data["price"]
    currency = price_data["currency"]
    price_gbp = to_gbp(price_raw, currency)

    instrument = None
    try:
        instrument = lookup_instrument(ticker)
    except Exception as e:
        current_app.logger.warning("lookup_instrument(%s) failed: %s", ticker, e)

    name = (instrument["name"] if instrument else None) or ticker
    asset_type = (instrument["asset_type"] if instrument else None) or "ETF"

    catalogue_id = add_holding_catalogue_item({
        "holding_name": name, "ticker": ticker,
        "asset_type": asset_type, "bucket": "Global Equity", "notes": "",
    }, uid)
    update_catalogue_price(
        catalogue_id, price_raw, currency,
        price_data.get("change_pct"),
        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )
    reconnect_holdings_to_catalogue(ticker, catalogue_id, uid)
    add_holding({
        "account_id": account_id, "holding_catalogue_id": catalogue_id,
        "holding_name": name, "ticker": ticker, "asset_type": asset_type,
        "bucket": "Global Equity", "value": round(units * price_gbp, 2),
        "units": units, "price": price_gbp, "notes": "",
    })
    return {"name": name, "ticker": ticker, "units": units, "price_gbp": price_gbp,
            "value": round(units * price_gbp, 2)}


def _add_holding_manual(uid, account_id, name, ticker, asset_type, units, price):
    """Shared logic: create catalogue entry and add a manual holding (no live price lookup).

    Returns a result dict. Raises ValueError with a user-facing message on failure.
    """
    catalogue_id = add_holding_catalogue_item({
        "holding_name": name, "ticker": ticker,
        "asset_type": asset_type, "bucket": "Other", "notes": "",
    }, uid)
    update_catalogue_price(
        catalogue_id, price, "GBP", None,
        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )
    if ticker:
        reconnect_holdings_to_catalogue(ticker, catalogue_id, uid)
    add_holding({
        "account_id": account_id, "holding_catalogue_id": catalogue_id,
        "holding_name": name, "ticker": ticker, "asset_type": asset_type,
        "bucket": "Other", "value": round(units * price, 2),
        "units": units, "price": price, "notes": "",
    })
    return {"name": name, "ticker": ticker, "units": units, "price_gbp": price,
            "value": round(units * price, 2)}


@accounts_bp.route("/api/<int:account_id>/holdings/add", methods=["POST"])
@login_required
def api_add_holding(account_id):
    """JSON API: add a holding by ticker and return the result (used by wizard JS)."""
    uid = current_user.id
    if not fetch_account(account_id, uid):
        return jsonify({"ok": False, "error": "Account not found"}), 404

    ticker = (request.form.get("ticker") or "").strip().upper()
    units = optional_float(request.form.get("units"), None)

    if not ticker or not units or units <= 0:
        return jsonify({"ok": False, "error": "Ticker and units are required"}), 400

    try:
        result = _add_holding_by_ticker(uid, account_id, ticker, units)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404

    return jsonify({
        "ok": True, "name": result["name"], "ticker": result["ticker"],
        "units": result["units"], "price": round(result["price_gbp"], 4),
        "value": result["value"],
    })


@accounts_bp.route("/api/<int:account_id>/holdings/add-manual", methods=["POST"])
@login_required
def api_add_holding_manual(account_id):
    """JSON API: add a manual holding and return the result (used by wizard JS)."""
    uid = current_user.id
    if not fetch_account(account_id, uid):
        return jsonify({"ok": False, "error": "Account not found"}), 404

    name = (request.form.get("name") or "").strip()
    ticker = (request.form.get("ticker") or "").strip().upper() or None
    asset_type = request.form.get("asset_type", "Fund")
    units = optional_float(request.form.get("units"), None)
    price = optional_float(request.form.get("price"), None)

    if not name or not units or not price or units <= 0 or price <= 0:
        return jsonify({"ok": False, "error": "Name, units and price are required"}), 400

    result = _add_holding_manual(uid, account_id, name, ticker, asset_type, units, price)
    return jsonify({
        "ok": True, "name": result["name"], "ticker": result["ticker"],
        "units": result["units"], "price": round(result["price_gbp"], 4),
        "value": result["value"],
    })


@accounts_bp.route("/<int:account_id>", methods=["GET", "POST"])
@login_required
def account_detail(account_id):
    uid = current_user.id
    selected = fetch_account(account_id, uid)
    if not selected:
        return redirect(url_for("accounts.accounts"))

    if request.method == "POST":
        form_name = request.form.get("form_name", "account")
        if form_name == "delete_account":
            delete_account(account_id, uid)
            return redirect(url_for("accounts.accounts"))

        if form_name == "log_prize":
            month_key = valid_month_key(request.form.get("month_key"))
            prize_amount = optional_float(request.form.get("prize_amount"), 0.0)
            if month_key and prize_amount is not None:
                log_prize(account_id, uid, month_key, prize_amount)
                flash(f"Prize of £{prize_amount:,.2f} logged for {month_key}.", "success")
            elif not month_key:
                flash("Please pick a valid month.", "error")
            return redirect(url_for("accounts.account_detail", account_id=account_id))

        if form_name == "delete_prize":
            prize_id = optional_int(request.form.get("prize_id"))
            if prize_id:
                delete_prize(prize_id, uid)
                flash("Prize entry removed.", "success")
            return redirect(url_for("accounts.account_detail", account_id=account_id))

        payload = _account_payload_from_form(request.form)
        payload["id"] = account_id
        if not payload["name"].strip():
            flash("Account name is required.", "error")
            return redirect(url_for("accounts.account_detail", account_id=account_id))
        # preserve fields managed by separate forms, not the main edit form
        if payload.get("cash_interest_rate") is None:
            payload["cash_interest_rate"] = (selected or {}).get("cash_interest_rate", 0) or 0
        if "uninvested_cash" not in payload:
            payload["uninvested_cash"] = (selected or {}).get("uninvested_cash") or 0
        if not payload.get("owner") and (selected or {}).get("owner"):
            payload["owner"] = selected["owner"]
        update_account(payload, uid)
        return redirect(url_for("accounts.account_detail", account_id=account_id))

    detail_mode = request.args.get("mode", "view")
    edit_holding_id = request.args.get("holding_id", type=int)
    return _render_accounts_page(uid, selected=selected, detail_mode=detail_mode, edit_holding_id=edit_holding_id)


@accounts_bp.route("/<int:account_id>/positions/new", methods=["GET", "POST"])
@login_required
def account_add_position(account_id):
    """Legacy route — redirect to account detail which now has an inline add form."""
    return redirect(url_for("accounts.account_detail", account_id=account_id))


@accounts_bp.route("/<int:account_id>/holdings/add", methods=["POST"])
@login_required
def account_add_holding(account_id):
    """Add a holding by ticker. Looks up price live, auto-creates catalogue entry."""
    uid = current_user.id
    account = fetch_account(account_id, uid)
    if not account:
        return redirect(url_for("accounts.accounts"))

    ticker = (request.form.get("ticker") or "").strip().upper()
    units = optional_float(request.form.get("units"), None)

    if not ticker or not units or units <= 0:
        flash("Please enter a valid ticker and number of units.", "error")
        return redirect(url_for("accounts.account_detail", account_id=account_id))

    try:
        _add_holding_by_ticker(uid, account_id, ticker, units)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("accounts.account_detail", account_id=account_id))

    if account["valuation_mode"] != "holdings":
        update_account({**dict(account), "valuation_mode": "holdings",
                        "last_updated": datetime.now(timezone.utc).isoformat()}, uid)

    return redirect(url_for("accounts.account_detail", account_id=account_id))


@accounts_bp.route("/<int:account_id>/holdings/add-manual", methods=["POST"])
@login_required
def account_add_holding_manual(account_id):
    """Add a custom holding without a live ticker (pensions, unlisted funds, etc.)."""
    uid = current_user.id
    account = fetch_account(account_id, uid)
    if not account:
        return redirect(url_for("accounts.accounts"))

    name = (request.form.get("name") or "").strip()
    ticker = (request.form.get("ticker") or "").strip().upper() or None
    asset_type = request.form.get("asset_type", "Fund")
    units = optional_float(request.form.get("units"), None)
    price = optional_float(request.form.get("price"), None)

    if not name or not units or not price or units <= 0 or price <= 0:
        flash("Please fill in the holding name, units, and price.", "error")
        return redirect(url_for("accounts.account_detail", account_id=account_id))

    _add_holding_manual(uid, account_id, name, ticker, asset_type, units, price)

    if account["valuation_mode"] != "holdings":
        update_account({**dict(account), "valuation_mode": "holdings",
                        "last_updated": datetime.now(timezone.utc).isoformat()}, uid)

    return redirect(url_for("accounts.account_detail", account_id=account_id))


@accounts_bp.route("/<int:account_id>/holdings/<int:holding_id>/log-isa-contribution", methods=["POST"])
@login_required
def log_holding_as_isa_contribution(account_id, holding_id):
    """Log this holding's current value as an ISA contribution.

    Useful when a broker hands you a free share inside an ISA — the share
    landed in your account but Shelly's allowance ledger doesn't know
    about it because no cash was deposited. One click here records the
    value as a top-up against your £20k allowance.
    """
    uid = current_user.id
    account = fetch_account(account_id, uid)
    if not account:
        return redirect(url_for("accounts.accounts"))

    if (account.get("wrapper_type") or "") not in ISA_WRAPPER_TYPES:
        flash("This shortcut only works for ISA accounts.", "error")
        return redirect(url_for("accounts.account_detail", account_id=account_id))

    holding = fetch_holding(holding_id, uid)
    if not holding or holding.get("account_id") != account_id:
        flash("Holding not found.", "error")
        return redirect(url_for("accounts.account_detail", account_id=account_id))

    units = float(holding.get("units") or 0)
    price = float(holding.get("price") or 0)
    value = round(units * price, 2) if units and price else float(holding.get("value") or 0)
    if value <= 0:
        flash("This holding has no value yet — set its units and price first.", "error")
        return redirect(url_for("accounts.account_detail", account_id=account_id))

    today_iso = datetime.now().date().isoformat()
    note = f"Free share: {holding.get('holding_name') or holding.get('ticker') or 'holding'}"
    add_isa_contribution(uid, account_id, value, today_iso, note)
    flash(f"Logged £{value:,.2f} against your ISA allowance.", "success")
    return redirect(url_for("accounts.account_detail", account_id=account_id))


@accounts_bp.route("/<int:account_id>/cash", methods=["POST"])
@login_required
def update_cash(account_id):
    uid = current_user.id
    account = fetch_account(account_id, uid)
    if not account:
        flash("Account not found.", "error")
        return redirect(url_for("accounts.accounts"))

    cash = request.form.get("uninvested_cash", "")
    rate = request.form.get("cash_interest_rate", "")
    payment_day = request.form.get("interest_payment_day", "")

    payload = dict(account)
    payload["uninvested_cash"] = to_float(cash) if cash else 0.0
    payload["cash_interest_rate"] = (to_float(rate) / 100.0) if rate else 0.0
    payload["interest_payment_day"] = max(0, min(31, optional_int(payment_day, default=0)))
    payload["last_updated"] = datetime.now(timezone.utc).isoformat()

    # ensure missing fields are populated before update
    payload.setdefault("employer_contribution", 0)
    payload.setdefault("contribution_method", "standard")
    payload.setdefault("annual_fee_pct", 0)
    payload.setdefault("platform_fee_pct", 0)
    payload.setdefault("platform_fee_flat", 0)
    payload.setdefault("platform_fee_cap", 0)
    payload.setdefault("fund_fee_pct", 0)
    payload.setdefault("contribution_fee_pct", 0)
    payload.setdefault("uninvested_cash", 0)
    payload.setdefault("cash_interest_rate", 0)
    payload.setdefault("interest_payment_day", 0)
    payload.setdefault("include_in_budget", True)
    payload.setdefault("pre_salary", False)

    update_account(payload, uid)
    holdings_totals = fetch_holding_totals_by_account(uid)
    accounts = fetch_all_accounts(uid)
    acct_vals = [(a["id"], effective_account_value(a, holdings_totals)) for a in accounts]
    save_daily_snapshot(uid, sum(v for _, v in acct_vals))
    save_account_daily_snapshots(uid, acct_vals)
    flash("Cash balance updated.", "success")
    return redirect(url_for("accounts.account_detail", account_id=account_id))


@accounts_bp.route("/<int:account_id>/holdings/<int:holding_id>/delete", methods=["POST"])
@login_required
def account_delete_holding(account_id, holding_id):
    delete_holding(holding_id, current_user.id)
    return redirect(url_for("accounts.account_detail", account_id=account_id))


@accounts_bp.route("/<int:account_id>/holdings/<int:holding_id>/edit", methods=["POST"])
@login_required
def account_edit_holding(account_id, holding_id):
    # Verify the account belongs to the current user before doing anything.
    if fetch_account(account_id, current_user.id) is None:
        return redirect(url_for("accounts.accounts"))

    units = optional_float(request.form.get("units"), None)
    price = optional_float(request.form.get("price"), None)
    book_cost = optional_float(request.form.get("book_cost"), None)
    notes = request.form.get("notes", "").strip()

    if units is not None and price is not None:
        value = units * price
    else:
        value = optional_float(request.form.get("value"), None)

    existing_list = [h for h in fetch_holdings_for_account(account_id) if h["id"] == holding_id]
    if not existing_list:
        return redirect(url_for("accounts.account_detail", account_id=account_id))
    existing = existing_list[0]

    payload = {
        "id": holding_id,
        "account_id": account_id,
        "holding_catalogue_id": existing["holding_catalogue_id"],
        "holding_name": existing["holding_name"],
        "ticker": existing["ticker"],
        "asset_type": existing["asset_type"],
        "bucket": existing["bucket"],
        "value": value if value is not None else float(existing["value"] or 0),
        "units": units if units is not None else float(existing["units"] or 0),
        "price": price if price is not None else float(existing["price"] or 0),
        "book_cost": book_cost if book_cost is not None else (float(existing["book_cost"]) if existing["book_cost"] is not None else None),
        "notes": notes,
    }
    update_holding(payload, current_user.id)

    # Also update catalogue price if modified
    if price is not None and existing["holding_catalogue_id"]:
        update_catalogue_price(
            existing["holding_catalogue_id"],
            price,
            "GBP",
            None,
            datetime.now(timezone.utc).isoformat()
        )
        sync_holding_prices_from_catalogue(existing["holding_catalogue_id"], price, "GBP")

    uid = current_user.id
    holdings_totals = fetch_holding_totals_by_account(uid)
    accounts = fetch_all_accounts(uid)
    acct_vals = [(a["id"], effective_account_value(a, holdings_totals)) for a in accounts]
    save_daily_snapshot(uid, sum(v for _, v in acct_vals))
    save_account_daily_snapshots(uid, acct_vals)
    flash(f"Updated {existing['holding_name']}", "success")
    return redirect(url_for("accounts.account_detail", account_id=account_id))
