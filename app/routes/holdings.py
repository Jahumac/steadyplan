"""Holdings blueprint — instruments catalogue page + API routes."""
from flask import Blueprint, jsonify, request, current_app, flash, redirect, url_for, render_template
from flask_login import current_user, login_required

from datetime import datetime, timezone, date as date_type

from app.calculations import effective_account_value
from app.models import (
    add_holding,
    add_holding_catalogue_item,
    delete_holding_catalogue_item,
    fetch_all_accounts,
    fetch_assumptions,
    fetch_catalogue_holding,
    fetch_first_position_for_catalogue_holding,
    fetch_holding_catalogue,
    fetch_holding_totals_by_account,
    fetch_instruments_in_use,
    fetch_or_create_monthly_review,
    mark_review_item_updated,
    save_account_daily_snapshots,
    save_daily_snapshot,
    sync_holding_prices_from_catalogue,
    update_catalogue_price,
    update_holding,
    update_holding_catalogue_item,
)
from app.services.prices import fetch_price, fetch_history, lookup_instrument, to_gbp, YFINANCE_AVAILABLE
from app.services.scheduler import trigger_manual_update

holdings_bp = Blueprint("holdings", __name__)

ASSET_TYPE_OPTIONS = ["ETF", "Fund", "Share", "Pension Fund", "Cash", "Bond", "Other"]
BUCKET_OPTIONS = ["Global Equity", "UK Equity", "US Equity", "Bonds", "Property", "Cash", "Commodities", "Other"]


@holdings_bp.route("/", methods=["GET", "POST"])
@login_required
def holdings_list():
    """Instruments catalogue list and search page."""
    uid = current_user.id

    if request.method == "POST":
        form_name = request.form.get("form_name", "")

        if form_name == "catalogue":
            name = request.form.get("catalogue_holding_name", "").strip()
            ticker = request.form.get("catalogue_ticker", "").strip()
            asset_type = request.form.get("catalogue_asset_type", "ETF")
            bucket = request.form.get("catalogue_bucket", "Global Equity")
            notes = request.form.get("catalogue_notes", "")
            cat_id = request.form.get("catalogue_id", "").strip()
            if name:
                if cat_id:
                    update_holding_catalogue_item({
                        "id": int(cat_id), "holding_name": name, "ticker": ticker,
                        "asset_type": asset_type, "bucket": bucket, "notes": notes,
                    })
                    flash(f"{name} updated.", "success")
                    return redirect(f"/holdings/{cat_id}")
                else:
                    new_id = add_holding_catalogue_item({
                        "holding_name": name, "ticker": ticker,
                        "asset_type": asset_type, "bucket": bucket, "notes": notes,
                    }, uid)
                    flash(f"{name} saved to instruments.", "success")
                    return redirect(f"/holdings/{new_id}")

        elif form_name == "delete_catalogue_holding":
            cat_id = request.form.get("catalogue_id", "").strip()
            if cat_id:
                item = fetch_catalogue_holding(int(cat_id))
                if item and item.get("user_id") == uid:
                    delete_holding_catalogue_item(int(cat_id))
                    flash("Instrument removed.", "success")
            return redirect("/holdings/")

        elif form_name == "refresh_all":
            trigger_manual_update(current_app, uid)
            flash("Price refresh triggered.", "success")

        return redirect("/holdings/")

    instruments = fetch_instruments_in_use(uid)
    all_accounts = fetch_all_accounts(uid)
    return render_template(
        "holdings.html",
        instruments_in_use=instruments,
        all_accounts=all_accounts,
        selected=None,
        asset_type_options=ASSET_TYPE_OPTIONS,
        bucket_options=BUCKET_OPTIONS,
        yfinance_available=YFINANCE_AVAILABLE,
        active_page="accounts",
    )


@holdings_bp.route("/<int:catalogue_id>/add-to-account", methods=["POST"])
@login_required
def add_to_account(catalogue_id):
    """Add a catalogue instrument to a specific account."""
    uid = current_user.id
    item = fetch_catalogue_holding(catalogue_id)
    if not item or item.get("user_id") != uid:
        flash("Instrument not found.", "error")
        return redirect("/holdings/")

    account_id = request.form.get("account_id", type=int)
    units = request.form.get("units", type=float) or 0.0
    price_input = (request.form.get("price") or "").strip()
    notes = request.form.get("notes", "")

    if not account_id or units <= 0:
        flash("Please select an account and enter a valid unit count.", "error")
        return redirect(f"/holdings/{catalogue_id}")

    last_price = float(item.get("last_price") or 0)
    currency = item.get("price_currency") or "GBP"
    catalogue_price_gbp = last_price / 100 if currency == "GBp" else last_price

    price = float(price_input) if price_input else catalogue_price_gbp
    value = units * price

    add_holding({
        "account_id": account_id,
        "holding_catalogue_id": catalogue_id,
        "holding_name": item["holding_name"],
        "ticker": item.get("ticker") or "",
        "asset_type": item.get("asset_type") or "",
        "bucket": item.get("bucket") or "",
        "value": value,
        "units": units,
        "price": price,
        "notes": notes,
    })
    flash(f"{item['holding_name']} added to account.", "success")
    return redirect(f"/accounts/{account_id}")


@holdings_bp.route("/<int:catalogue_id>")
@login_required
def holding_detail(catalogue_id):
    """Render a detail page for a specific catalogue instrument."""
    item_row = fetch_catalogue_holding(catalogue_id)
    if not item_row:
        flash("Instrument not found.", "error")
        return redirect(url_for("overview.overview"))

    item = dict(item_row)
    if item.get("user_id") != current_user.id:
        flash("Instrument not found.", "error")
        return redirect(url_for("overview.overview"))

    period = (request.args.get("period") or "1y").strip().lower()
    period_map = {
        "1d": "1d",
        "1m": "1mo",
        "6m": "6mo",
        "1y": "1y",
    }
    history_period = period_map.get(period, "1y")

    history_data = None
    ticker = (item.get("ticker") or "").strip()
    if ticker:
        history_data = fetch_history(ticker, period=history_period)

    first_pos = fetch_first_position_for_catalogue_holding(catalogue_id, current_user.id)
    view_in_account_url = None
    if first_pos:
        view_in_account_url = url_for(
            "accounts.account_detail",
            account_id=int(first_pos["account_id"]),
            holding_id=int(first_pos["holding_id"]),
            mode="view",
        ) + "#holdings-section"

    # ── Benchmark comparison ─────────────────────────────────────────────────
    # Compare price performance over the selected period against the user's
    # benchmark rate (from assumptions, default 7% p.a.).
    # Only meaningful for multi-day periods with ≥2 price points.
    perf_stats = None
    benchmark_data = None
    if history_data and len(history_data) >= 2 and period != "1d":
        try:
            assumptions = fetch_assumptions(current_user.id)
            raw_rate = (assumptions.get("benchmark_rate") if assumptions else None)
            # Stored as a decimal fraction (0.10 = 10%); convert to a
            # percentage here because the chart math below divides by 100 again.
            benchmark_rate = float(raw_rate) * 100 if raw_rate else 7.0  # % p.a.

            first_price = float(history_data[0]["price"])
            last_price = float(history_data[-1]["price"])

            # Parse first and last dates to get elapsed days
            first_label = history_data[0]["date"]
            last_label = history_data[-1]["date"]
            try:
                d0 = date_type.fromisoformat(first_label)
                d1 = date_type.fromisoformat(last_label)
                days_elapsed = max((d1 - d0).days, 1)
            except ValueError:
                days_elapsed = None

            if first_price > 0 and days_elapsed:
                actual_pct = (last_price / first_price - 1) * 100
                rate_decimal = benchmark_rate / 100
                benchmark_pct = ((1 + rate_decimal) ** (days_elapsed / 365) - 1) * 100
                vs_pct = actual_pct - benchmark_pct

                perf_stats = {
                    "actual_pct": round(actual_pct, 2),
                    "benchmark_pct": round(benchmark_pct, 2),
                    "vs_pct": round(vs_pct, 2),
                    "benchmark_rate": benchmark_rate,
                    "period_label": {"1m": "1 month", "6m": "6 months", "1y": "1 year"}.get(period, period),
                    "days": days_elapsed,
                }

                # Build normalised benchmark price series (starts at same price as fund)
                benchmark_data = []
                for entry in history_data:
                    try:
                        d = date_type.fromisoformat(entry["date"])
                        days_from_start = max((d - d0).days, 0)
                        bench_price = first_price * ((1 + rate_decimal) ** (days_from_start / 365))
                        benchmark_data.append({"date": entry["date"], "price": round(bench_price, 4)})
                    except ValueError:
                        pass
        except Exception:
            pass  # benchmark is optional — never crash the page over it

    return render_template(
        "holding_detail.html",
        item=item,
        history_data=history_data,
        history_period=period,
        view_in_account_url=view_in_account_url,
        perf_stats=perf_stats,
        benchmark_data=benchmark_data,
    )


@holdings_bp.route("/api/lookup")
@login_required
def api_lookup():
    """Search for an instrument by ticker and return enriched metadata + price."""
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "no query"}), 400

    catalogue = fetch_holding_catalogue(current_user.id)
    existing = next((r for r in catalogue if (r["ticker"] or "").upper() == q.upper()), None)

    result = lookup_instrument(q)
    if not result:
        return jsonify({"error": f"Could not find '{q}' via live market data providers"}), 404

    result["in_catalogue"] = existing is not None
    result["catalogue_id"] = existing["id"] if existing else None
    result["catalogue_name"] = existing["holding_name"] if existing else None
    return jsonify(result)


@holdings_bp.route("/api/price")
@login_required
def api_price():
    """Lightweight price lookup used by the monthly update and add-holding bar."""
    ticker = request.args.get("ticker", "").strip()
    if not ticker:
        return jsonify({"error": "no ticker"}), 400
    data = fetch_price(ticker)
    if not data:
        return jsonify({"error": "not found"}), 404
    price_raw = data["price"]
    currency_raw = data["currency"]
    price_gbp = to_gbp(price_raw, currency_raw)
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return jsonify({
        "price": round(price_gbp, 4),
        "currency": "GBP",
        "price_raw": round(float(price_raw), 4),
        "currency_raw": currency_raw,
        "change_pct": data.get("change_pct"),
        "updated_at": updated_at,
        "yf_symbol": data.get("yf_symbol", ticker),
    })


@holdings_bp.route("/api/save-price", methods=["POST"])
@login_required
def api_save_price():
    """Save an updated price (and recalculated value) for a single holding.

    Called automatically after a live price fetch so the user doesn't need
    a separate Save click.
    """
    data = request.get_json(silent=True)
    if not data or "holding_id" not in data:
        return jsonify({"error": "missing data"}), 400

    holding_id = int(data["holding_id"])
    price = float(data.get("price", 0))
    units = float(data.get("units", 0))
    holding_catalogue_id = data.get("holding_catalogue_id")

    ok = update_holding({
        "id": holding_id,
        "account_id": int(data.get("account_id", 0)),
        "holding_catalogue_id": holding_catalogue_id,
        "holding_name": data.get("holding_name", ""),
        "ticker": data.get("ticker", ""),
        "asset_type": data.get("asset_type", ""),
        "bucket": data.get("bucket", ""),
        "value": units * price,
        "units": units,
        "price": price,
        "notes": data.get("notes", ""),
    }, current_user.id)
    if not ok:
        return jsonify({"error": "holding not found"}), 404

    price_source = (data.get("price_source") or "").strip().lower()
    currency_raw = (data.get("currency_raw") or "").strip() or None
    price_raw = data.get("price_raw", None)
    change_pct = data.get("change_pct", None)
    updated_at = (data.get("updated_at") or "").strip() or None
    if not updated_at:
        updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if holding_catalogue_id and (price_source == "live" or currency_raw or price_raw is not None):
        try:
            catalogue_id_int = int(holding_catalogue_id)
            price_raw_f = float(price_raw) if price_raw is not None else float(price)
            currency_raw_s = currency_raw or "GBP"
            change_pct_f = float(change_pct) if change_pct is not None else None

            update_catalogue_price(catalogue_id_int, price_raw_f, currency_raw_s, change_pct_f, updated_at)
            sync_holding_prices_from_catalogue(catalogue_id_int, price_raw_f, currency_raw_s)

            uid = current_user.id
            accounts = fetch_all_accounts(uid)
            holdings_totals = fetch_holding_totals_by_account(uid)
            acct_vals = [(a["id"], effective_account_value(a, holdings_totals)) for a in accounts]
            save_daily_snapshot(uid, sum(v for _, v in acct_vals))
            save_account_daily_snapshots(uid, acct_vals)
        except Exception as e:
            current_app.logger.warning("Failed to update catalogue price or snapshot: %s", e)

    # Mark the monthly review item as updated so the review progress is accurate
    month_key = (data.get("month_key") or "").strip()
    account_id = data.get("account_id")
    if month_key and account_id:
        try:
            uid = current_user.id
            review = fetch_or_create_monthly_review(month_key, uid)
            mark_review_item_updated(review["id"], int(account_id), "holdings_updated")
        except Exception as e:
            current_app.logger.warning("Failed to mark review item updated: %s", e)

    return jsonify({"ok": True, "value": round(units * price, 2)})


@holdings_bp.route("/api/trigger-price-update", methods=["POST"])
@login_required
def api_trigger_price_update():
    """Manually trigger a price update for the current user.

    This fetches fresh prices for all holdings, updates the catalogue,
    and saves a daily snapshot.
    """
    result = trigger_manual_update(current_app, current_user.id)
    if result.get("ok"):
        status_code = 200
    elif result.get("cooldown"):
        status_code = 429
    else:
        status_code = 400
    return jsonify(result), status_code


@holdings_bp.route("/trigger-price-update", methods=["POST"])
@login_required
def trigger_price_update():
    result = trigger_manual_update(current_app, current_user.id)
    if result.get("ok"):
        flash(result.get("message") or "Prices updated.", "success")
    elif result.get("cooldown"):
        flash(result.get("message") or "Please wait a moment before refreshing again.", "warning")
    else:
        flash(result.get("message") or result.get("error") or "Price update failed.", "error")
    return redirect(request.referrer or url_for("overview.overview"))
