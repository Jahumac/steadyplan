import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from flask import Blueprint, Response, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from app.calculations import current_age_from_assumptions
from app.services.assistant_access import (
    assistant_action_label,
    assistant_amount_change_label,
    assistant_scope_labels,
    assistant_scope_options,
    assistant_target_label,
    assistant_token_label,
    assistant_token_last_used_label,
    assistant_token_secret_heading,
    normalise_requested_assistant_scopes,
    pop_plaintext_assistant_token,
    stash_plaintext_assistant_token,
)
from app.services.backups import list_backups, run_backup
from app.services.csv_parsers import match_parsed_to_holdings
from app.services.restore_service import RestoreValidationError, restore_backup_for_user
from app.services.restore_staging import (
    cleanup_restore_staging,
    create_pre_restore_backup,
    delete_staged_restore_file,
    is_staged_restore_expired,
    read_staged_restore_file,
    stage_restore_file,
)
from app.services.restore_validation import validate_restore_backup_json
from app.services.trading212 import (
    Trading212ConnectionError,
    Trading212CredentialError,
    decrypt_trading212_credential,
    encrypt_trading212_credential,
    fetch_trading212_portfolio_snapshot,
    mask_trading212_key,
    probe_trading212_connection,
    trading212_environment_label,
    trading212_environment_options,
    trading212_status_label,
)
from app.utils import optional_float, optional_int, valid_date
from app.models import (
    API_TOKEN_KIND_ASSISTANT,
    ASSISTANT_SCOPE_READ,
    PROVIDER_TRADING212,
    create_api_token,
    delete_broker_connection,
    fetch_api_token,
    fetch_api_tokens,
    fetch_assistant_audit_events,
    fetch_account,
    fetch_assumptions,
    fetch_broker_connection,
    fetch_broker_connections,
    fetch_holding_catalogue_in_use,
    fetch_latest_price_update,
    get_connection,
    reset_all_user_data,
    revoke_api_token,
    update_assumptions,
    update_broker_connection_status,
    upsert_broker_connection,
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
    latest = None
    if backups:
        def _sort_key(row):
            try:
                return datetime.fromisoformat(str(row.get("modified") or ""))
            except Exception:
                return datetime.min
        latest = max(backups, key=_sort_key)
    latest_age_days = None
    health_status = "warning"
    health_label = "Needs backup"
    health_message = "No whole-instance SQLite backup found."
    if latest and latest.get("modified"):
        try:
            modified_dt = datetime.fromisoformat(str(latest["modified"]))
            now_dt = datetime.now()
            age_seconds = max(0, (now_dt - modified_dt).total_seconds())
            latest_age_days = int(age_seconds // (24 * 60 * 60))
            if latest_age_days <= 7:
                health_status = "good"
                health_label = "OK"
                health_message = f"OK — latest whole-instance SQLite backup is {latest_age_days} day{'s' if latest_age_days != 1 else ''} old."
            else:
                health_status = "warning"
                health_label = "Needs backup"
                health_message = f"Latest whole-instance SQLite backup is {latest_age_days} days old."
        except Exception:
            health_status = "warning"
            health_label = "Needs backup"
            health_message = "Whole-instance SQLite backup exists, but its age could not be determined."
    return {
        "count": len(backups),
        "latest": latest,
        "latest_name": latest["name"] if latest else None,
        "latest_modified": latest["modified"] if latest else None,
        "latest_size_human": _human_bytes(latest["size_bytes"]) if latest else None,
        "latest_age_days": latest_age_days,
        "health_status": health_status,
        "health_label": health_label,
        "health_message": health_message,
    }


def _trust_posture_diagnostics():
    is_production = bool(current_app.config.get("IS_PRODUCTION", False))
    session_cookie_secure = bool(current_app.config.get("SESSION_COOKIE_SECURE", False))
    remember_cookie_secure = bool(current_app.config.get("REMEMBER_COOKIE_SECURE", False))
    trust_proxy_headers = bool(current_app.config.get("TRUST_PROXY_HEADERS", False))
    demo_public_login_enabled = bool(current_app.config.get("DEMO_PUBLIC_LOGIN_ENABLED", False))
    rate_limit_warning = current_app.config.get("RATELIMIT_STORAGE_WARNING")
    worker_count = int(current_app.config.get("WEB_CONCURRENCY", 1) or 1)
    rate_limit_storage_uri = str(current_app.config.get("RATELIMIT_STORAGE_URI") or "memory://").strip().lower()

    items = {
        "app_mode": {
            "label": "OK" if is_production else "Local/demo posture",
            "value": "Production" if is_production else "Development/local",
            "message": (
                "Production mode is on. Pair this with HTTPS and secure cookies for real use."
                if is_production
                else "Local/development mode is active. Fine for LAN/VPN evaluation, but review production settings before exposing SteadyPlan publicly."
            ),
        },
        "secure_cookies": {
            "label": "OK" if session_cookie_secure and remember_cookie_secure else ("Review recommended" if is_production else "Local/demo posture"),
            "value": "Secure" if session_cookie_secure and remember_cookie_secure else "Not secure",
            "message": (
                "Secure session and remember cookies are on."
                if session_cookie_secure and remember_cookie_secure
                else "Secure cookies are off while production mode is on. Turn them on behind HTTPS."
                if is_production
                else "Secure cookies are off. That is normal on local HTTP, but turn them on behind HTTPS."
            ),
        },
        "proxy_headers": {
            "label": "Deliberate public/proxy" if trust_proxy_headers else "OK",
            "value": "Trusted" if trust_proxy_headers else "Ignored by default",
            "message": (
                "SteadyPlan trusts forwarded proxy headers. Only leave this on behind a trusted reverse proxy or tunnel."
                if trust_proxy_headers
                else "Forwarded proxy headers are ignored unless you explicitly opt in."
            ),
        },
        "demo_login": {
            "label": "Deliberate public demo" if demo_public_login_enabled else "OK",
            "value": "Enabled" if demo_public_login_enabled else "Disabled",
            "message": (
                "Public read-only demo login is enabled. Keep it demo-data-only and treat it as an explicit host choice."
                if demo_public_login_enabled
                else "Public demo login is off. Real accounts still require normal login."
            ),
        },
        "rate_limits": {
            "label": "Review recommended" if rate_limit_warning else "OK",
            "value": "Process-local memory" if rate_limit_storage_uri == "memory://" else "Shared storage",
            "message": rate_limit_warning or (
                "Process-local memory storage is fine with a single worker."
                if rate_limit_storage_uri == "memory://" and worker_count == 1
                else "Shared rate-limit storage is configured for multi-worker use."
            ),
        },
    }
    needs_review = any(item["label"] == "Review recommended" for item in items.values())
    if needs_review:
        overall_label = "Review recommended"
        overall_message = "One or more settings need review before treating this as a polished public deployment."
    elif not is_production or demo_public_login_enabled:
        overall_label = "Local/demo posture"
        overall_message = "This instance looks deliberate for local evaluation or read-only demo use. Review production settings before exposing SteadyPlan publicly."
    else:
        overall_label = "OK"
        overall_message = "Production-ready basics look in place for this trust checkpoint."
    return {"overall_label": overall_label, "overall_message": overall_message, "items": items}


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


def broker_connection_last_tested_label(value):
    return value or "Not yet tested"


def trading212_sync_support_note():
    return (
        "Trading 212's Public API currently only covers Invest and Stocks ISA accounts. "
        "SIPP data is not available through the broker API yet, so keep CSV/manual paths for pension tracking."
    )


def _prepare_trading212_connections(rows):
    prepared = []
    for row in rows or []:
        item = dict(row)
        try:
            item["masked_api_key"] = mask_trading212_key(
                decrypt_trading212_credential(item.get("api_key_ciphertext"))
            )
        except Trading212CredentialError:
            item["masked_api_key"] = "Unavailable"
        prepared.append(item)
    return prepared


def _preview_holdings_rows(user_id, account_id=None):
    with get_connection() as conn:
        sql = """
            SELECT
                h.id,
                h.account_id,
                h.holding_name,
                h.ticker,
                h.units,
                h.price,
                h.value,
                a.name AS account_name,
                a.provider AS account_provider,
                a.wrapper_type AS account_wrapper_type
            FROM holdings h
            JOIN accounts a ON a.id = h.account_id
            WHERE a.user_id = ?
        """
        params = [user_id]
        if account_id is not None:
            sql += " AND a.id = ?"
            params.append(account_id)
        sql += " ORDER BY a.name ASC, h.holding_name ASC, h.id ASC"
        return _select_rows(conn, sql, tuple(params))


_TRADING212_MATCH_STOPWORDS = {
    "acc",
    "accumulating",
    "class",
    "etf",
    "fund",
    "gbp",
    "global",
    "inc",
    "income",
    "ltd",
    "markets",
    "plc",
    "shares",
    "stock",
    "ucits",
    "usd",
}


def _preview_match_tokens(*values):
    tokens = set()
    for value in values:
        text = str(value or "").lower()
        for token in re.findall(r"[a-z0-9]+", text):
            if len(token) <= 2:
                continue
            if token in _TRADING212_MATCH_STOPWORDS:
                continue
            tokens.add(token)
    return tokens


def _preview_possible_holding_matches(position, existing_holdings, *, preferred_account_id=None, limit=3):
    position_tokens = _preview_match_tokens(position.get("name"), position.get("ticker"))
    if not position_tokens:
        return []

    candidates = []
    for holding in existing_holdings:
        holding_tokens = _preview_match_tokens(holding.get("holding_name"), holding.get("ticker"))
        if not holding_tokens:
            continue
        overlap = sorted(position_tokens & holding_tokens)
        if len(overlap) < 2:
            continue
        score = len(overlap)
        if holding.get("account_provider") == "Trading 212":
            score += 1
        if preferred_account_id and holding.get("account_id") == preferred_account_id:
            score += 3
        candidates.append(
            {
                "holding": dict(holding),
                "overlap_tokens": overlap,
                "score": score,
                "preferred_account": bool(preferred_account_id and holding.get("account_id") == preferred_account_id),
            }
        )

    candidates.sort(
        key=lambda row: (
            -row["score"],
            row["holding"].get("account_name") or "",
            row["holding"].get("holding_name") or "",
        )
    )
    return candidates[:limit]


def _build_trading212_preview(user_id, connection, snapshot, *, linked_account=None):
    positions = list(snapshot.get("positions") or [])
    preferred_account_id = None
    if linked_account and linked_account.get("id"):
        preferred_account_id = int(linked_account["id"])
    existing_holdings = _preview_holdings_rows(user_id, account_id=preferred_account_id)
    matched, broker_only, db_only = match_parsed_to_holdings(positions, existing_holdings)
    for pair in matched:
        broker_row = pair.get("csv") or {}
        holding_row = pair.get("holding") or {}
        broker_units = broker_row.get("units")
        tracked_units = holding_row.get("units")
        broker_value = broker_row.get("value")
        tracked_value = holding_row.get("value")
        pair["units_difference"] = None if broker_units is None or tracked_units is None else float(broker_units) - float(tracked_units)
        pair["value_difference"] = None if broker_value is None or tracked_value is None else float(broker_value) - float(tracked_value)
    for row in broker_only:
        row["possible_matches"] = _preview_possible_holding_matches(
            row,
            existing_holdings,
            preferred_account_id=preferred_account_id,
        )
    summary = snapshot.get("summary") or {}
    return {
        "connection": dict(connection),
        "summary": summary,
        "linked_account": dict(linked_account) if linked_account else None,
        "positions": positions,
        "matched": matched,
        "broker_only": broker_only,
        "db_only": db_only,
        "stats": {
            "positions_count": len(positions),
            "matched_count": len(matched),
            "broker_only_count": len(broker_only),
            "db_only_count": len(db_only),
            "position_value_total": sum(float((row or {}).get("value") or 0) for row in positions),
            "matched_value": sum(float((pair.get("csv") or {}).get("value") or 0) for pair in matched),
            "broker_only_value": sum(float((row or {}).get("value") or 0) for row in broker_only),
            "db_only_value": sum(float((row or {}).get("value") or 0) for row in db_only),
            "available_to_trade": float(summary.get("available_to_trade") or 0),
        },
        "fetched_at": snapshot.get("fetched_at") or summary.get("fetched_at"),
    }


def _select_rows(conn, sql, params):
    return [dict(r) for r in (conn.execute(sql, params).fetchall() or [])]


def _settings_template_context(uid, *, assumptions=None, computed_age=None, diagnostics=None, page_mode="view", **extra):
    assumptions = assumptions if assumptions is not None else fetch_assumptions(uid)
    computed_age = computed_age if computed_age is not None else (int(current_age_from_assumptions(assumptions)) if assumptions else 0)
    assistant_tokens = fetch_api_tokens(uid, token_kind=API_TOKEN_KIND_ASSISTANT)
    assistant_audit_events = fetch_assistant_audit_events(uid, limit=12)
    assistant_token_secret = pop_plaintext_assistant_token(session)
    trading212_connections = _prepare_trading212_connections(
        fetch_broker_connections(uid, provider=PROVIDER_TRADING212)
    )
    return {
        "assumptions": assumptions,
        "computed_age": computed_age,
        "diagnostics": diagnostics,
        "page_mode": page_mode,
        "active_page": "settings",
        "assistant_tokens": assistant_tokens,
        "assistant_audit_events": assistant_audit_events,
        "assistant_scope_options": assistant_scope_options(),
        "assistant_scope_labels": assistant_scope_labels,
        "assistant_action_label": assistant_action_label,
        "assistant_amount_change_label": assistant_amount_change_label,
        "assistant_target_label": assistant_target_label,
        "assistant_token_label": assistant_token_label,
        "assistant_token_last_used_label": assistant_token_last_used_label,
        "assistant_token_secret_heading": assistant_token_secret_heading,
        "assistant_token_secret": assistant_token_secret,
        "trading212_connections": trading212_connections,
        "trading212_environment_options": trading212_environment_options(),
        "trading212_environment_label": trading212_environment_label,
        "trading212_status_label": trading212_status_label,
        "mask_trading212_key": mask_trading212_key,
        "broker_connection_last_tested_label": broker_connection_last_tested_label,
        "trading212_sync_support_note": trading212_sync_support_note,
        **extra,
    }


def _clear_restore_staging_session():
    session.pop("restore_staged_token", None)
    session.pop("restore_staged_at", None)
    session.pop("restore_staged_user_id", None)


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
        allowance_tracking = _select_rows(
            conn,
            """
            SELECT * FROM allowance_tracking
            WHERE user_id = ?
            ORDER BY tax_year ASC, id ASC
            """,
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
            "app": "SteadyPlan",
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
            "allowance_tracking": allowance_tracking,
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
            "dashboard_name": request.form.get("dashboard_name", "SteadyPlan").strip() or "SteadyPlan",
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

    page_mode = request.args.get("mode", "view")
    focus = request.args.get("focus", "")
    focus_planning_dates = page_mode == "edit" and focus == "planning_dates"
    focus_scenario_estimate_assumptions = page_mode == "edit" and focus == "scenario_estimate_assumptions"
    computed_age = int(current_age_from_assumptions(assumptions)) if assumptions else 0
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
            diagnostics["scheduler_status"] = {
                "short": f"{last_run['run_date']} {last_run['slot']}" if last_run else "Not yet",
                "full": f"{last_run['run_date']} {last_run['slot']}" if last_run else "Not yet recorded",
                "message": (
                    "A scheduler run has been recorded for this user."
                    if last_run
                    else "No scheduler run has been recorded yet. That is normal on a fresh instance or when you mainly update prices and balances manually."
                ),
            }

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
            diagnostics["backups"] = {
                "count": 0,
                "latest": None,
                "latest_name": None,
                "latest_modified": None,
                "latest_size_human": None,
                "latest_age_days": None,
                "health_status": "warning",
                "health_label": "Needs backup",
                "health_message": "Backup health could not be determined.",
            }
        diagnostics["trust_posture"] = _trust_posture_diagnostics()

    return render_template(
        "settings.html",
        **_settings_template_context(
            uid,
            assumptions=assumptions,
            computed_age=computed_age,
            diagnostics=diagnostics,
            focus_planning_dates=focus_planning_dates,
            focus_scenario_estimate_assumptions=focus_scenario_estimate_assumptions,
            page_mode=page_mode,
        ),
    )


@settings_bp.route("/assistant-access/create", methods=["POST"])
@login_required
def create_assistant_access_token():
    label = request.form.get("label", "").strip() or "Pip"
    scopes = normalise_requested_assistant_scopes(request.form.getlist("scopes"))
    token = create_api_token(
        current_user.id,
        label=label,
        token_kind=API_TOKEN_KIND_ASSISTANT,
        scopes=scopes,
    )
    stash_plaintext_assistant_token(session, token=token, label=label, scopes=scopes, action="created")
    flash("Assistant token created. Copy it now — it will only be shown once.", "success")
    return redirect(url_for("settings.settings"))


@settings_bp.route("/assistant-access/<int:token_id>/regenerate", methods=["POST"])
@login_required
def regenerate_assistant_access_token(token_id):
    existing = fetch_api_token(token_id, current_user.id, token_kind=API_TOKEN_KIND_ASSISTANT)
    if existing is None:
        flash("Assistant token not found.", "error")
        return redirect(url_for("settings.settings"))

    new_token = create_api_token(
        current_user.id,
        label=existing.get("label") or "Pip",
        token_kind=API_TOKEN_KIND_ASSISTANT,
        scopes=existing.get("scopes") or [ASSISTANT_SCOPE_READ],
    )
    revoke_api_token(token_id, current_user.id)
    stash_plaintext_assistant_token(
        session,
        token=new_token,
        label=existing.get("label") or "Pip",
        scopes=existing.get("scopes") or [ASSISTANT_SCOPE_READ],
        action="regenerated",
    )
    flash("Assistant token regenerated. The old token no longer works, and the new raw token is only shown once.", "success")
    return redirect(url_for("settings.settings"))


@settings_bp.route("/assistant-access/<int:token_id>/revoke", methods=["POST"])
@login_required
def revoke_assistant_access_token(token_id):
    existing = fetch_api_token(token_id, current_user.id, token_kind=API_TOKEN_KIND_ASSISTANT)
    if existing is None:
        flash("Assistant token not found.", "error")
        return redirect(url_for("settings.settings"))

    revoke_api_token(token_id, current_user.id)
    flash("Assistant token revoked. It no longer works.", "success")
    return redirect(url_for("settings.settings"))


def _settings_trading212_redirect():
    return redirect(url_for("settings.settings") + "#trading212-access")


@settings_bp.route("/trading212/connect", methods=["POST"])
@login_required
def connect_trading212():
    label = request.form.get("label", "").strip() or "Trading 212"
    environment = (request.form.get("environment", "live") or "live").strip().lower()
    api_key = request.form.get("api_key", "").strip()
    api_secret = request.form.get("api_secret", "").strip()
    if not api_key or not api_secret:
        flash("Enter both the Trading 212 API key and API secret.", "error")
        return _settings_trading212_redirect()

    try:
        probe = probe_trading212_connection(
            api_key=api_key,
            api_secret=api_secret,
            environment=environment,
        )
        summary = probe["summary"]
        upsert_broker_connection(
            user_id=current_user.id,
            provider=PROVIDER_TRADING212,
            environment=summary["environment"],
            label=label,
            access_mode="read_only",
            api_key_ciphertext=encrypt_trading212_credential(api_key),
            api_secret_ciphertext=encrypt_trading212_credential(api_secret),
            status="connected",
            last_error=None,
            last_tested_at=summary["fetched_at"],
            external_account_id=summary["account_id"],
            external_account_currency=summary["currency"],
            external_total_value=summary["total_value"],
        )
    except (Trading212ConnectionError, Trading212CredentialError) as exc:
        flash(str(exc), "error")
        return _settings_trading212_redirect()

    flash(
        f"Saved {label} as a read-only Trading 212 {trading212_environment_label(summary['environment']).lower()} connection. "
        f"{trading212_sync_support_note()}",
        "success",
    )
    return _settings_trading212_redirect()


@settings_bp.route("/trading212/<int:connection_id>/retest", methods=["POST"])
@login_required
def retest_trading212(connection_id):
    connection = fetch_broker_connection(connection_id, current_user.id)
    if connection is None or connection.get("provider") != PROVIDER_TRADING212:
        flash("Trading 212 connection not found.", "error")
        return _settings_trading212_redirect()

    try:
        api_key = decrypt_trading212_credential(connection.get("api_key_ciphertext"))
        api_secret = decrypt_trading212_credential(connection.get("api_secret_ciphertext"))
        probe = probe_trading212_connection(
            api_key=api_key,
            api_secret=api_secret,
            environment=connection.get("environment") or "live",
        )
        summary = probe["summary"]
        update_broker_connection_status(
            connection_id,
            current_user.id,
            status="connected",
            last_error=None,
            last_tested_at=summary["fetched_at"],
            external_account_id=summary["account_id"],
            external_account_currency=summary["currency"],
            external_total_value=summary["total_value"],
        )
        flash(
            f"Trading 212 {trading212_environment_label(summary['environment']).lower()} connection retested successfully.",
            "success",
        )
    except (Trading212ConnectionError, Trading212CredentialError) as exc:
        update_broker_connection_status(
            connection_id,
            current_user.id,
            status="error",
            last_error=str(exc),
            last_tested_at=datetime.now(timezone.utc).isoformat(),
        )
        flash(str(exc), "error")
    return _settings_trading212_redirect()


@settings_bp.route("/trading212/<int:connection_id>/preview", methods=["POST"])
@login_required
def preview_trading212(connection_id):
    connection = fetch_broker_connection(connection_id, current_user.id)
    if connection is None or connection.get("provider") != PROVIDER_TRADING212:
        flash("Trading 212 connection not found.", "error")
        return _settings_trading212_redirect()

    try:
        api_key = decrypt_trading212_credential(connection.get("api_key_ciphertext"))
        api_secret = decrypt_trading212_credential(connection.get("api_secret_ciphertext"))
        snapshot = fetch_trading212_portfolio_snapshot(
            api_key=api_key,
            api_secret=api_secret,
            environment=connection.get("environment") or "live",
        )
        summary = snapshot["summary"]
        update_broker_connection_status(
            connection_id,
            current_user.id,
            status="connected",
            last_error=None,
            last_tested_at=summary["fetched_at"],
            external_account_id=summary["account_id"],
            external_account_currency=summary["currency"],
            external_total_value=summary["total_value"],
        )
    except (Trading212ConnectionError, Trading212CredentialError) as exc:
        update_broker_connection_status(
            connection_id,
            current_user.id,
            status="error",
            last_error=str(exc),
            last_tested_at=datetime.now(timezone.utc).isoformat(),
        )
        flash(str(exc), "error")
        return _settings_trading212_redirect()

    refreshed_connection = fetch_broker_connection(connection_id, current_user.id) or connection
    linked_account = None
    account_id = optional_int(request.form.get("account_id"), default=None)
    if account_id:
        linked_account = fetch_account(account_id, current_user.id)
        if linked_account is None:
            flash("Linked account not found.", "error")
            return _settings_trading212_redirect()
        if linked_account.get("linked_broker_connection_id") != connection_id:
            flash("That account is not linked to this Trading 212 connection.", "error")
            return redirect(url_for("accounts.account_detail", account_id=account_id))
    preview = _build_trading212_preview(current_user.id, refreshed_connection, snapshot, linked_account=linked_account)
    return render_template(
        "trading212_preview.html",
        active_page="accounts" if linked_account else "settings",
        trading212_preview=preview,
        trading212_environment_label=trading212_environment_label,
        trading212_sync_support_note=trading212_sync_support_note,
        preview_back_href=url_for("accounts.account_detail", account_id=account_id) if linked_account else "/settings/#trading212-access",
        preview_back_label="Back to account" if linked_account else "Back to settings",
    )


@settings_bp.route("/trading212/<int:connection_id>/disconnect", methods=["POST"])
@login_required
def disconnect_trading212(connection_id):
    connection = fetch_broker_connection(connection_id, current_user.id)
    if connection is None or connection.get("provider") != PROVIDER_TRADING212:
        flash("Trading 212 connection not found.", "error")
        return _settings_trading212_redirect()
    delete_broker_connection(connection_id, current_user.id)
    flash("Trading 212 connection removed. CSV/manual imports remain available.", "success")
    return _settings_trading212_redirect()


@settings_bp.route("/backups/run", methods=["POST"])
@login_required
def run_backup_now():
    if not getattr(current_user, "is_admin", False):
        flash("Admin only: you can't create a whole-instance SQLite backup from here.", "error")
        return redirect(url_for("settings.settings", mode="diagnostics"))

    db_path = Path(current_app.config["DB_PATH"])
    data_dir = Path(current_app.config.get("DATA_DIR", db_path.parent))
    try:
        dest = run_backup(db_path, data_dir)
        flash(f"SQLite backup created: {dest.name}", "success")
    except Exception:
        current_app.logger.exception("Manual backup failed")
        flash("SQLite backup failed. Check server logs for details.", "error")

    next_url = _safe_next_settings_url(request.form.get("next"))
    return redirect(next_url or url_for("settings.settings", mode="diagnostics"))


@settings_bp.route("/export.json", methods=["GET"])
@login_required
def export_user_data():
    payload = _user_export_payload(current_user.id)
    today = datetime.now(timezone.utc).date().isoformat()
    filename = f"steadyplan-export-{today}.json"
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    resp = Response(body, mimetype="application/json")
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@settings_bp.route("/restore/validate", methods=["POST"])
@login_required
def validate_restore_backup_upload():
    cleanup_restore_staging(current_app.config)
    uploaded = request.files.get("backup_file")
    prior_token = session.get("restore_staged_token")
    delete_staged_restore_file(current_app.config, prior_token)
    _clear_restore_staging_session()
    restore_token = None
    if not uploaded or not getattr(uploaded, "filename", ""):
        result = {
            "valid": False,
            "export_schema_version": None,
            "exported_at": None,
            "counts": {},
            "errors": ["Please choose a .json export file to upload."],
            "warnings": [],
        }
    else:
        try:
            json_bytes = uploaded.read()
        except Exception:
            json_bytes = b""
        if not json_bytes:
            result = {
                "valid": False,
                "export_schema_version": None,
                "exported_at": None,
                "counts": {},
                "errors": ["Uploaded file was empty or could not be read."],
                "warnings": [],
            }
        else:
            result = validate_restore_backup_json(json_bytes)
            if result.get("valid"):
                restore_token = stage_restore_file(current_app.config, json_bytes)
                session["restore_staged_token"] = restore_token
                session["restore_staged_at"] = time.time()
                session["restore_staged_user_id"] = current_user.id

    uid = current_user.id
    assumptions = fetch_assumptions(uid)
    computed_age = int(current_age_from_assumptions(assumptions)) if assumptions else 0
    return render_template(
        "settings.html",
        **_settings_template_context(
            uid,
            assumptions=assumptions,
            computed_age=computed_age,
            diagnostics=None,
            page_mode="view",
            restore_check_result=result,
            restore_token=restore_token,
        ),
    )


@settings_bp.route("/restore/commit", methods=["POST"])
@login_required
def commit_restore_backup():
    cleanup_restore_staging(current_app.config)
    restore_token = request.form.get("restore_token", "").strip()
    expected_token = session.get("restore_staged_token")
    expected_user_id = session.get("restore_staged_user_id")
    staged_at = session.get("restore_staged_at")
    if (
        not restore_token
        or not expected_token
        or restore_token != expected_token
        or expected_user_id != current_user.id
        or is_staged_restore_expired(current_app.config, restore_token, staged_at)
    ):
        delete_staged_restore_file(current_app.config, expected_token)
        _clear_restore_staging_session()
        flash("This restore preview has expired. Please upload the export file again.", "error")
        return redirect(url_for("settings.settings"))

    json_bytes = read_staged_restore_file(current_app.config, restore_token)
    if not json_bytes:
        delete_staged_restore_file(current_app.config, restore_token)
        _clear_restore_staging_session()
        flash("Restore file could not be read. Please upload the export file again.", "error")
        return redirect(url_for("settings.settings"))

    result = validate_restore_backup_json(json_bytes)
    if not result.get("valid"):
        delete_staged_restore_file(current_app.config, restore_token)
        _clear_restore_staging_session()
        flash("That restore file is not valid. No data has been changed.", "error")
        uid = current_user.id
        assumptions = fetch_assumptions(uid)
        computed_age = int(current_age_from_assumptions(assumptions)) if assumptions else 0
        return render_template(
            "settings.html",
            **_settings_template_context(
                uid,
                assumptions=assumptions,
                computed_age=computed_age,
                diagnostics=None,
                page_mode="view",
                restore_check_result=result,
                restore_token=None,
            ),
        )

    confirm_checked = request.form.get("confirm_replace") == "1"
    confirm_phrase = request.form.get("confirm_phrase", "").strip()
    if not confirm_checked or confirm_phrase.upper() != "RESTORE":
        flash("To restore and overwrite data, tick the checkbox and type RESTORE to confirm.", "error")
        uid = current_user.id
        assumptions = fetch_assumptions(uid)
        computed_age = int(current_age_from_assumptions(assumptions)) if assumptions else 0
        return render_template(
            "settings.html",
            **_settings_template_context(
                uid,
                assumptions=assumptions,
                computed_age=computed_age,
                diagnostics=None,
                page_mode="view",
                restore_check_result=result,
                restore_token=restore_token,
            ),
        )

    try:
        payload = json.loads(json_bytes.decode("utf-8"))
    except Exception:
        delete_staged_restore_file(current_app.config, restore_token)
        _clear_restore_staging_session()
        flash("Export file could not be parsed. No data has been changed.", "error")
        return redirect(url_for("settings.settings"))

    try:
        backup_dest = create_pre_restore_backup(current_app.config)
    except Exception:
        current_app.logger.exception("Pre-restore backup failed for user_id=%s", current_user.id)
        flash(
            "Restore stopped before any data was changed because SteadyPlan could not create a fresh whole-instance SQLite backup.",
            "error",
        )
        uid = current_user.id
        assumptions = fetch_assumptions(uid)
        computed_age = int(current_age_from_assumptions(assumptions)) if assumptions else 0
        return render_template(
            "settings.html",
            **_settings_template_context(
                uid,
                assumptions=assumptions,
                computed_age=computed_age,
                diagnostics=None,
                page_mode="view",
                restore_check_result=result,
                restore_token=restore_token,
            ),
        )

    try:
        with get_connection() as conn:
            restore_summary = restore_backup_for_user(current_user.id, payload, conn=conn)
    except RestoreValidationError as e:
        current_app.logger.info("Restore blocked by validation for user_id=%s", current_user.id)
        delete_staged_restore_file(current_app.config, restore_token)
        _clear_restore_staging_session()
        flash("That restore file is not valid. No data has been changed.", "error")
        uid = current_user.id
        assumptions = fetch_assumptions(uid)
        computed_age = int(current_age_from_assumptions(assumptions)) if assumptions else 0
        return render_template(
            "settings.html",
            **_settings_template_context(
                uid,
                assumptions=assumptions,
                computed_age=computed_age,
                diagnostics=None,
                page_mode="view",
                restore_check_result=e.validation_result,
                restore_token=None,
            ),
        )
    except Exception:
        current_app.logger.exception("Restore failed for user_id=%s", current_user.id)
        delete_staged_restore_file(current_app.config, restore_token)
        _clear_restore_staging_session()
        flash("Restore failed. Your data was not changed.", "error")
        return redirect(url_for("settings.settings"))

    delete_staged_restore_file(current_app.config, restore_token)
    _clear_restore_staging_session()
    cleanup_restore_staging(current_app.config)
    flash(
        f"Restore complete. Data for this user has been overwritten. Safety backup created first: {backup_dest.name}",
        "success",
    )

    uid = current_user.id
    assumptions = fetch_assumptions(uid)
    computed_age = int(current_age_from_assumptions(assumptions)) if assumptions else 0
    return render_template(
        "settings.html",
        **_settings_template_context(
            uid,
            assumptions=assumptions,
            computed_age=computed_age,
            diagnostics=None,
            page_mode="view",
            restore_check_result=result,
            restore_token=None,
            restore_commit_result=restore_summary,
        ),
    )


@settings_bp.route("/reset", methods=["POST"])
@login_required
def reset_account():
    """Wipe all user data and return to a fresh-login state."""
    confirmation = request.form.get("confirm_reset", "").strip()
    if confirmation.upper() != "RESET":
        return redirect(url_for("settings.settings"))
    reset_all_user_data(current_user.id)
    return redirect(url_for("overview.overview"))
