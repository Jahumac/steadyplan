import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from flask import Blueprint, Response, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.calculations import current_age_from_assumptions
from app.services.backups import list_backups, run_backup
from app.utils import optional_float, optional_int, valid_date
from app.models import (
    fetch_assumptions,
    fetch_holding_catalogue_in_use,
    fetch_latest_price_update,
    get_connection,
    reset_all_user_data,
    update_assumptions,
)

settings_bp = Blueprint("settings", __name__)


def _human_bytes(n):
    try:
        n = float(n or 0)
    except (TypeError, ValueError):
        n = 0.0
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while n >= 1024 and i < len(units) - 1:
        n /= 1024.0
        i += 1
    if i == 0:
        return f"{int(n)} {units[i]}"
    return f"{n:.1f} {units[i]}"


def _backup_diagnostics():
    db_path = Path(current_app.config["DB_PATH"])
    data_dir = Path(current_app.config.get("DATA_DIR", db_path.parent))
    backups = list_backups(data_dir)
    latest = backups[-1] if backups else None
    return {
        "count": len(backups),
        "latest": latest,
        "latest_name": latest["name"] if latest else None,
        "latest_modified": latest["modified"] if latest else None,
        "latest_size_human": _human_bytes(latest["size_bytes"]) if latest else None,
    }


def _safe_next_settings_url(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    if not raw.startswith("/"):
        return None
    if raw.startswith("//"):
        return None
    parts = urlsplit(raw)
    if parts.scheme or parts.netloc:
        return None
    if parts.path not in {"/settings", "/settings/"}:
        return None
    if parts.query and parts.query != "mode=diagnostics":
        return None
    if parts.fragment and parts.fragment != "danger-zone":
        return None
    out = parts.path
    if parts.query:
        out += "?" + parts.query
    if parts.fragment:
        out += "#" + parts.fragment
    return out


def _select_rows(conn, sql, params):
    return [dict(r) for r in (conn.execute(sql, params).fetchall() or [])]


def _user_export_payload(user_id):
    exported_at = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        assumptions = fetch_assumptions(user_id)
        accounts = _select_rows(
            conn,
            "SELECT * FROM accounts WHERE user_id = ? ORDER BY id ASC",
            (user_id,),
        )
        account_ids = [int(a["id"]) for a in accounts]

        holdings = _select_rows(
            conn,
            """
            SELECT h.*, a.name AS account_name
            FROM holdings h
            JOIN accounts a ON a.id = h.account_id
            WHERE a.user_id = ?
            ORDER BY a.id ASC, h.id ASC
            """,
            (user_id,),
        )
        holding_catalogue = _select_rows(
            conn,
            "SELECT * FROM holding_catalogue WHERE user_id = ? ORDER BY id ASC",
            (user_id,),
        )
        goals = _select_rows(
            conn,
            "SELECT * FROM goals WHERE user_id = ? ORDER BY id ASC",
            (user_id,),
        )
        debts = _select_rows(
            conn,
            "SELECT * FROM debts WHERE user_id = ? ORDER BY id ASC",
            (user_id,),
        )

        budget_sections = _select_rows(
            conn,
            "SELECT * FROM budget_sections WHERE user_id = ? ORDER BY sort_order ASC, id ASC",
            (user_id,),
        )
        budget_items = _select_rows(
            conn,
            "SELECT * FROM budget_items WHERE user_id = ? ORDER BY section ASC, sort_order ASC, id ASC",
            (user_id,),
        )
        budget_entries = _select_rows(
            conn,
            """
            SELECT be.*
            FROM budget_entries be
            JOIN budget_items bi ON bi.id = be.budget_item_id
            WHERE bi.user_id = ?
            ORDER BY be.month_key ASC, be.budget_item_id ASC
            """,
            (user_id,),
        )

        monthly_snapshots = _select_rows(
            conn,
            """
            SELECT ms.*
            FROM monthly_snapshots ms
            JOIN accounts a ON a.id = ms.account_id
            WHERE a.user_id = ?
            ORDER BY ms.month_key ASC, ms.account_id ASC
            """,
            (user_id,),
        )
        portfolio_daily_snapshots = _select_rows(
            conn,
            """
            SELECT snapshot_date, total_value, created_at
            FROM portfolio_daily_snapshots
            WHERE user_id = ?
            ORDER BY snapshot_date ASC
            """,
            (user_id,),
        )
        account_daily_snapshots = _select_rows(
            conn,
            """
            SELECT account_id, snapshot_date, value
            FROM account_daily_snapshots
            WHERE user_id = ?
            ORDER BY account_id ASC, snapshot_date ASC
            """,
            (user_id,),
        )

        monthly_reviews = _select_rows(
            conn,
            "SELECT * FROM monthly_reviews WHERE user_id = ? ORDER BY month_key ASC",
            (user_id,),
        )
        monthly_review_items = _select_rows(
            conn,
            """
            SELECT mri.*, mr.month_key
            FROM monthly_review_items mri
            JOIN monthly_reviews mr ON mr.id = mri.review_id
            WHERE mr.user_id = ?
            ORDER BY mr.month_key ASC, mri.account_id ASC, mri.id ASC
            """,
            (user_id,),
        )

        cash_flow_events = _select_rows(
            conn,
            """
            SELECT *
            FROM cash_flow_events
            WHERE user_id = ?
            ORDER BY event_date ASC, id ASC
            """,
            (user_id,),
        )

        isa_contributions = _select_rows(
            conn,
            "SELECT * FROM isa_contributions WHERE user_id = ? ORDER BY contribution_date ASC, id ASC",
            (user_id,),
        )
        pension_contributions = _select_rows(
            conn,
            "SELECT * FROM pension_contributions WHERE user_id = ? ORDER BY contribution_date ASC, id ASC",
            (user_id,),
        )
        dividend_records = _select_rows(
            conn,
            "SELECT * FROM dividend_records WHERE user_id = ? ORDER BY dividend_date ASC, id ASC",
            (user_id,),
        )
        cgt_disposals = _select_rows(
            conn,
            "SELECT * FROM cgt_disposals WHERE user_id = ? ORDER BY disposal_date ASC, id ASC",
            (user_id,),
        )
        pension_carry_forward = _select_rows(
            conn,
            "SELECT * FROM pension_carry_forward WHERE user_id = ? ORDER BY tax_year ASC, id ASC",
            (user_id,),
        )

        contribution_overrides = []
        premium_bonds_prizes = []
        if account_ids:
            placeholders = ", ".join("?" for _ in account_ids)
            contribution_overrides = _select_rows(
                conn,
                f"""
                SELECT * FROM contribution_overrides
                WHERE account_id IN ({placeholders})
                ORDER BY account_id ASC, from_month ASC, to_month ASC, id ASC
                """,
                tuple(account_ids),
            )
            premium_bonds_prizes = _select_rows(
                conn,
                f"""
                SELECT p.*
                FROM premium_bonds_prizes p
                JOIN accounts a ON a.id = p.account_id
                WHERE a.user_id = ?
                ORDER BY p.month_key ASC, p.id ASC
                """,
                (user_id,),
            )

    return {
        "meta": {
            "exported_at": exported_at,
            "export_schema_version": 1,
            "app": "Shelly Finance",
        },
        "assumptions": dict(assumptions) if assumptions else {},
        "accounts": accounts,
        "holdings": holdings,
        "holding_catalogue": holding_catalogue,
        "goals": goals,
        "debts": debts,
        "budget": {
            "sections": budget_sections,
            "items": budget_items,
            "entries": budget_entries,
        },
        "history": {
            "monthly_snapshots": monthly_snapshots,
            "portfolio_daily_snapshots": portfolio_daily_snapshots,
            "account_daily_snapshots": account_daily_snapshots,
            "monthly_reviews": monthly_reviews,
            "monthly_review_items": monthly_review_items,
        },
        "planning": {
            "contribution_overrides": contribution_overrides,
            "cash_flow_events": cash_flow_events,
            "isa_contributions": isa_contributions,
            "pension_contributions": pension_contributions,
            "dividend_records": dividend_records,
            "cgt_disposals": cgt_disposals,
            "pension_carry_forward": pension_carry_forward,
            "premium_bonds_prizes": premium_bonds_prizes,
        },
    }


@settings_bp.route("/", methods=["GET", "POST"])
@login_required
def settings():
    uid = current_user.id
    assumptions = fetch_assumptions(uid)

    if request.method == "POST":
        # Remember whether this is the first time DOB is being set (for redirect)
        had_no_dob = not (assumptions and assumptions["date_of_birth"])

        def _f(key, default=0.0):
            return optional_float(request.form.get(key), default=default)

        def _i(key, default=0):
            return optional_int(request.form.get(key), default=default)

        salary_day = max(0, min(31, _i("salary_day", 0)))
        update_day = max(0, min(31, _i("update_day", 0)))

        # Auto-calculate update day: salary day + 5 calendar days (settlement buffer)
        if salary_day and not update_day:
            update_day = salary_day + 5
            if update_day > 31:
                update_day = update_day - 31  # wrap into next month (early days)

        raw_dob = request.form.get("date_of_birth", "").strip()
        new_dob = valid_date(raw_dob) or ""
        if raw_dob and not new_dob:
            flash("Please enter a valid date of birth (YYYY-MM-DD).", "error")
            return redirect(url_for("settings.settings"))

        payload = {
            "annual_growth_rate": _f("annual_growth_rate", 7) / 100.0,
            "retirement_age": _i("retirement_age", 60),
            "date_of_birth": new_dob,
            "retirement_goal_value": assumptions["retirement_goal_value"] if assumptions else 1000000,
            "isa_allowance": _f("isa_allowance", 20000),
            "lisa_allowance": _f("lisa_allowance", 4000),
            "dividend_allowance": _f("dividend_allowance", 500),
            "annual_income": _f("annual_income", 0),
            "pension_annual_allowance": _f("pension_annual_allowance", 60000),
            "mpaa_enabled": 1 if request.form.get("mpaa_enabled") else 0,
            "mpaa_allowance": _f("mpaa_allowance", 10000),
            "target_dev_pct": assumptions["target_dev_pct"] if assumptions else 0.90,
            "target_em_pct": assumptions["target_em_pct"] if assumptions else 0.10,
            "emergency_fund_target": assumptions["emergency_fund_target"] if assumptions else 3000,
            "dashboard_name": request.form.get("dashboard_name", "Shelly").strip() or "Shelly",
            "salary_day": salary_day,
            "update_day": update_day,
            "retirement_date_mode": request.form.get("retirement_date_mode", "birthday"),
            "tax_band": request.form.get("tax_band", "basic"),
            "auto_update_prices": 1 if request.form.get("auto_update_prices") else 0,
            "update_time_morning": request.form.get("update_time_morning", "08:30").strip() or "08:30",
            "update_time_evening": request.form.get("update_time_evening", "18:00").strip() or "18:00",
            "benchmark_rate": _f("benchmark_rate", 0) / 100.0 if request.form.get("benchmark_rate", "").strip() else None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        update_assumptions(payload, uid)

        # First-time profile setup: bounce back to overview so the user
        # sees their onboarding progress tick forward
        if had_no_dob and new_dob:
            flash("Settings saved.", "success")
            return redirect(url_for("overview.overview"))

        flash("Settings saved.", "success")
        return redirect(url_for("settings.settings"))

    computed_age = int(current_age_from_assumptions(assumptions)) if assumptions else 0
    page_mode = request.args.get("mode", "view")
    diagnostics = None
    if page_mode == "diagnostics":
        diagnostics = {}
        with get_connection() as conn:
            diagnostics["db_ok"] = True
            try:
                conn.execute("SELECT 1").fetchone()
            except Exception:
                diagnostics["db_ok"] = False

            last_run = conn.execute(
                "SELECT run_date, slot, created_at FROM scheduler_runs WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (uid,),
            ).fetchone()
            diagnostics["scheduler_last_run"] = dict(last_run) if last_run else None

            counts = conn.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM accounts WHERE user_id = ?) AS accounts,
                    (SELECT COUNT(*) FROM holdings h JOIN accounts a ON a.id = h.account_id WHERE a.user_id = ?) AS holdings,
                    (SELECT COUNT(*) FROM holding_catalogue WHERE user_id = ? AND is_active = 1) AS catalogue_active,
                    (SELECT COUNT(*) FROM portfolio_daily_snapshots WHERE user_id = ?) AS portfolio_daily_snapshots
                """,
                (uid, uid, uid, uid),
            ).fetchone()
            diagnostics["counts"] = dict(counts) if counts else {}

            latest_snapshot = conn.execute(
                "SELECT snapshot_date, total_value FROM portfolio_daily_snapshots WHERE user_id = ? ORDER BY snapshot_date DESC LIMIT 1",
                (uid,),
            ).fetchone()
            diagnostics["latest_portfolio_snapshot"] = dict(latest_snapshot) if latest_snapshot else None

            in_use = fetch_holding_catalogue_in_use(uid)
            diagnostics["catalogue_in_use_count"] = len(in_use) if in_use else 0

            latest_price_update = fetch_latest_price_update(uid)
            diagnostics["latest_price_update_raw"] = latest_price_update
            diagnostics["latest_price_update_utc"] = str(latest_price_update) if latest_price_update else None

            sample_rows = conn.execute(
                """
                SELECT
                    hc.id,
                    hc.holding_name,
                    hc.ticker,
                    hc.last_price,
                    hc.price_currency,
                    hc.price_updated_at,
                    COUNT(h.id) AS linked_holdings
                FROM holding_catalogue hc
                JOIN holdings h ON h.holding_catalogue_id = hc.id
                JOIN accounts a ON a.id = h.account_id
                WHERE a.user_id = ?
                  AND a.is_active = 1
                  AND hc.is_active = 1
                GROUP BY hc.id
                ORDER BY hc.price_updated_at DESC NULLS LAST, hc.holding_name ASC
                LIMIT 20
                """,
                (uid,),
            ).fetchall()
            diagnostics["catalogue_in_use_sample"] = sample_rows

        stale_count = 0
        now_utc = datetime.now(timezone.utc)
        for row in diagnostics.get("catalogue_in_use_sample", []):
            ts = (row.get("price_updated_at") or "").strip()
            if not ts:
                stale_count += 1
                continue
            try:
                if ts.endswith(" UTC"):
                    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)
                else:
                    dt = datetime.fromisoformat(ts)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                if now_utc - dt > timedelta(days=2):
                    stale_count += 1
            except (ValueError, TypeError):
                stale_count += 1
        diagnostics["catalogue_stale_2d_count_in_sample"] = stale_count
        try:
            diagnostics["backups"] = _backup_diagnostics()
        except Exception:
            current_app.logger.exception("Failed to load backup diagnostics")
            diagnostics["backups"] = {"count": 0, "latest": None}

    return render_template(
        "settings.html",
        assumptions=assumptions,
        computed_age=computed_age,
        diagnostics=diagnostics,
        page_mode=page_mode,
        active_page="settings",
    )


@settings_bp.route("/backups/run", methods=["POST"])
@login_required
def run_backup_now():
    if not getattr(current_user, "is_admin", False):
        flash("Admin only: you can't run a server backup from here.", "error")
        return redirect(url_for("settings.settings", mode="diagnostics"))

    db_path = Path(current_app.config["DB_PATH"])
    data_dir = Path(current_app.config.get("DATA_DIR", db_path.parent))
    try:
        dest = run_backup(db_path, data_dir)
        flash(f"Backup created: {dest.name}", "success")
    except Exception:
        current_app.logger.exception("Manual backup failed")
        flash("Backup failed. Check server logs for details.", "error")

    next_url = _safe_next_settings_url(request.form.get("next"))
    return redirect(next_url or url_for("settings.settings", mode="diagnostics"))


@settings_bp.route("/export.json", methods=["GET"])
@login_required
def export_user_data():
    payload = _user_export_payload(current_user.id)
    today = datetime.now(timezone.utc).date().isoformat()
    filename = f"shelly-finance-export-{today}.json"
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    resp = Response(body, mimetype="application/json")
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@settings_bp.route("/reset", methods=["POST"])
@login_required
def reset_account():
    """Wipe all user data and return to a fresh-login state."""
    confirmation = request.form.get("confirm_reset", "").strip()
    if confirmation != "RESET":
        return redirect(url_for("settings.settings"))
    reset_all_user_data(current_user.id)
    return redirect(url_for("overview.overview"))
