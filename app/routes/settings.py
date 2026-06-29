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
    add_holding,
    create_api_token,
    delete_broker_connection,
    fetch_api_token,
    fetch_api_tokens,
    fetch_assistant_audit_events,
    fetch_account,
    fetch_all_accounts,
    fetch_assumptions,
    fetch_broker_connection,
    fetch_broker_connections,
    fetch_broker_sync_events,
    fetch_holding,
    fetch_holding_catalogue_in_use,
    fetch_latest_price_update,
    get_connection,
    log_broker_sync_event,
    reset_all_user_data,
    revoke_api_token,
    update_account,
    update_assumptions,
    update_broker_connection_status,
    update_holding,
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
    health_label = "SQLite backup recommended"
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
                health_label = "SQLite backup recommended"
                health_message = f"Latest whole-instance SQLite backup is {latest_age_days} days old."
        except Exception:
            health_status = "warning"
            health_label = "SQLite backup recommended"
            health_message = "Whole-instance SQLite backup exists, but its age could not be determined."
    return {
        "count": len(backups),
        "latest": latest,
        "latest_name": latest["name"] if latest else None,
        "latest_name_label": latest["name"] if latest else "No SQLite backup yet",
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
            "value": "Production" if is_production else "Local/development",
            "message": (
                "Production mode is on. Keep HTTPS and secure cookies on for real use."
                if is_production
                else "Local/development mode is on. Fine for LAN/VPN checks, but review production settings before exposing SteadyPlan publicly."
            ),
        },
        "secure_cookies": {
            "label": "OK" if session_cookie_secure and remember_cookie_secure else ("Review recommended" if is_production else "Local/demo posture"),
            "value": "Secure" if session_cookie_secure and remember_cookie_secure else "Not secure",
            "message": (
                "Secure cookies are on for sessions and remembered logins."
                if session_cookie_secure and remember_cookie_secure
                else "Secure cookies are off while production mode is on. Turn them on behind HTTPS."
                if is_production
                else "Secure cookies are off. That is normal on local HTTP, but turn them on behind HTTPS."
            ),
        },
        "proxy_headers": {
            "label": "Proxy headers enabled" if trust_proxy_headers else "OK",
            "value": "Enabled" if trust_proxy_headers else "Off by default",
            "message": (
                "Forwarded proxy headers are trusted. Only leave this on behind a trusted reverse proxy or tunnel."
                if trust_proxy_headers
                else "Forwarded proxy headers stay off unless you explicitly opt in."
            ),
        },
        "demo_login": {
            "label": "Public demo enabled" if demo_public_login_enabled else "OK",
            "value": "Enabled" if demo_public_login_enabled else "Disabled",
            "message": (
                "Public read-only demo is enabled. Keep it demo-data-only and treat it as an explicit host choice."
                if demo_public_login_enabled
                else "Public read-only demo is off. Real accounts still require normal login."
            ),
        },
        "rate_limits": {
            "label": "Review recommended" if rate_limit_warning else "OK",
            "value": "Single-worker memory" if rate_limit_storage_uri == "memory://" else "Shared storage",
            "message": rate_limit_warning or (
                "Single-worker memory is fine with one worker."
                if rate_limit_storage_uri == "memory://" and worker_count == 1
                else "Shared rate-limit storage is configured for multi-worker use."
            ),
        },
    }
    needs_review = any(item["label"] == "Review recommended" for item in items.values())
    if needs_review:
        overall_label = "Review recommended"
        overall_message = "One or more settings need review before relying on this for public use."
    elif not is_production or demo_public_login_enabled:
        overall_label = "Local/demo posture"
        overall_message = "This instance looks set up for local evaluation or read-only demo use. Review production settings before exposing it publicly."
    else:
        overall_label = "OK"
        overall_message = "Basic public-facing settings look in place for this trust checkpoint."
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
    return value or "No broker snapshot check yet"


def trading212_access_mode_label(value):
    if (value or "").strip().lower() == "read_only":
        return "Read-only"
    return (value or "—").replace("_", " ").title()


def trading212_sync_support_note():
    return (
        "Trading 212's Public API currently supports Invest and Stocks ISA only. "
        "Cash ISA and SIPP accounts should stay manual/CSV-tracked for now."
    )


def trading212_connection_not_found_message():
    return "Saved broker snapshot connection not found."


def trading212_account_not_linked_message():
    return "That account is not linked to this saved broker snapshot connection."


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


def _preview_possible_broker_matches_for_holding(holding, broker_positions, *, limit=2):
    holding_tokens = _preview_match_tokens(holding.get("holding_name"), holding.get("ticker"))
    if not holding_tokens:
        return []

    candidates = []
    for row in broker_positions:
        broker_tokens = _preview_match_tokens(row.get("name"), row.get("ticker"))
        if not broker_tokens:
            continue
        overlap = sorted(holding_tokens & broker_tokens)
        if len(overlap) < 2:
            continue
        candidates.append(
            {
                "broker_row": dict(row),
                "overlap_tokens": overlap,
                "score": len(overlap),
            }
        )

    candidates.sort(
        key=lambda item: (
            -item["score"],
            item["broker_row"].get("name") or "",
            item["broker_row"].get("ticker") or "",
        )
    )
    return candidates[:limit]


def _annotate_trading212_tracked_only_rows(rows, broker_positions):
    annotated = []
    for row in rows:
        item = dict(row)
        broker_candidates = _preview_possible_broker_matches_for_holding(item, broker_positions)
        item["possible_broker_matches"] = broker_candidates
        if broker_candidates:
            item["review_label"] = "Needs rematch"
            item["review_hint"] = "Similar broker snapshot rows exist, so this tracked holding likely needs a careful rematch rather than a fresh add."
            item["next_step_hint"] = "Next step: compare this holding with the broker clue first, then use the reviewed match flow if it is genuinely the same position."
        else:
            item["review_label"] = "Likely stale/manual"
            item["review_hint"] = "No similar broker snapshot row was found, so this is more likely an older manual entry, a sold position, or something still tracked outside this API snapshot."
            item["next_step_hint"] = "Next step: review whether this holding should stay tracked manually, be archived, or be removed after you confirm it is no longer in the broker account."
        annotated.append(item)
    return annotated


def _trading212_broker_row_key(row, index):
    return f"{index}:{(row or {}).get('ticker') or ''}:{(row or {}).get('name') or ''}"


def trading212_match_type_label(match_type):
    labels = {
        "ticker": "Ticker match",
        "name": "Name match",
        "name_normalized": "Normalised name match",
    }
    return labels.get(str(match_type or "").strip().lower(), "Other match")


def _build_trading212_preview(user_id, connection, snapshot, *, linked_account=None):
    positions = list(snapshot.get("positions") or [])
    preferred_account_id = None
    if linked_account and linked_account.get("id"):
        preferred_account_id = int(linked_account["id"])
    existing_holdings = _preview_holdings_rows(user_id, account_id=preferred_account_id)
    matched, broker_only, db_only = match_parsed_to_holdings(positions, existing_holdings)
    matched_updates = []
    for pair in matched:
        broker_row = pair.get("csv") or {}
        holding_row = pair.get("holding") or {}
        broker_units = broker_row.get("units")
        tracked_units = holding_row.get("units")
        broker_value = broker_row.get("value")
        tracked_value = holding_row.get("value")
        pair["units_difference"] = None if broker_units is None or tracked_units is None else float(broker_units) - float(tracked_units)
        pair["value_difference"] = None if broker_value is None or tracked_value is None else float(broker_value) - float(tracked_value)
        if (
            (pair["units_difference"] is not None and abs(pair["units_difference"]) >= 0.0001)
            or (pair["value_difference"] is not None and abs(pair["value_difference"]) >= 0.005)
        ):
            matched_updates.append(pair)
    for row in broker_only:
        row["possible_matches"] = _preview_possible_holding_matches(
            row,
            existing_holdings,
            preferred_account_id=preferred_account_id,
        )
    db_only = _annotate_trading212_tracked_only_rows(db_only, positions)
    for idx, row in enumerate(broker_only):
        row["preview_key"] = _trading212_broker_row_key(row, idx)
    summary = snapshot.get("summary") or {}
    stats = {
        "positions_count": len(positions),
        "matched_count": len(matched),
        "broker_only_count": len(broker_only),
        "db_only_count": len(db_only),
        "position_value_total": sum(float((row or {}).get("value") or 0) for row in positions),
        "matched_value": sum(float((pair.get("csv") or {}).get("value") or 0) for pair in matched),
        "broker_only_value": sum(float((row or {}).get("value") or 0) for row in broker_only),
        "db_only_value": sum(float((row or {}).get("value") or 0) for row in db_only),
        "available_to_trade": float(summary.get("available_to_trade") or 0),
    }
    apply_plan = None
    if linked_account:
        sync_focus = linked_account.get("broker_sync_focus") or "all"

        if sync_focus == "cash_only":
            matched = []
            matched_updates = []
            broker_only = []
            db_only = []
            stats["matched_count"] = 0
            stats["broker_only_count"] = 0
            stats["db_only_count"] = 0
            stats["matched_value"] = 0.0
            stats["broker_only_value"] = 0.0
            stats["db_only_value"] = 0.0

        tracked_value_total = sum(float((row or {}).get("value") or 0) for row in existing_holdings)
        value_gap = stats["position_value_total"] - tracked_value_total
        broker_cash_total = float(summary.get("available_to_trade") or 0) + float(summary.get("cash_in_pies") or 0) + float(summary.get("cash_reserved_for_orders") or 0)
        if (
            linked_account.get("broker_sync_focus") == "cash_only"
            or linked_account.get("category") == "Cash"
            or (linked_account.get("wrapper_type") or "").lower() == "cash isa"
        ):
            tracked_cash = float(linked_account.get("current_value") or 0)
        else:
            tracked_cash = float(linked_account.get("uninvested_cash") or 0)
        cash_difference = broker_cash_total - tracked_cash
        can_apply_cash = abs(cash_difference) >= 0.01 if sync_focus in ["all", "cash_only"] else False
        
        needs_changes = False
        if sync_focus in ["all", "holdings_only"]:
            if matched_updates or broker_only or db_only or abs(value_gap) >= 0.005:
                needs_changes = True
        if can_apply_cash:
            needs_changes = True

        apply_plan = {
            "matched_updates_count": len(matched_updates),
            "broker_add_count": len(broker_only),
            "tracked_review_count": len(db_only),
            "broker_value_total": stats["position_value_total"],
            "tracked_value_total": tracked_value_total,
            "value_gap": value_gap,
            "broker_cash_total": broker_cash_total,
            "tracked_cash": tracked_cash,
            "cash_difference": cash_difference,
            "can_apply_cash": can_apply_cash,
            "needs_changes": needs_changes,
            "sync_focus": sync_focus,
            "can_apply_matched_changes": bool(matched_updates) if sync_focus in ["all", "holdings_only"] else False,
            "addable_broker_count": len([row for row in broker_only if not (row.get("possible_matches") or [])]),
            "can_apply_broker_additions": bool([row for row in broker_only if not (row.get("possible_matches") or [])]) if sync_focus in ["all", "holdings_only"] else False,
            "resolvable_possible_match_count": len([row for row in broker_only if (row.get("possible_matches") or [])]),
            "can_resolve_possible_matches": bool([row for row in broker_only if (row.get("possible_matches") or [])]) if sync_focus in ["all", "holdings_only"] else False,
        }
    return {
        "connection": dict(connection),
        "summary": summary,
        "linked_account": dict(linked_account) if linked_account else None,
        "positions": positions,
        "matched": matched,
        "matched_updates": matched_updates,
        "broker_only": broker_only,
        "db_only": db_only,
        "apply_plan": apply_plan,
        "stats": stats,
        "fetched_at": snapshot.get("fetched_at") or summary.get("fetched_at"),
    }


def _render_trading212_preview(preview):
    linked_account = preview.get("linked_account")
    account_id = linked_account.get("id") if linked_account else None
    preview = dict(preview)
    connection = preview.get("connection") or {}
    preview["sync_history"] = _recent_trading212_sync_state(current_user.id, int(connection.get("id") or 0)) if connection.get("id") else {
        "events": [],
        "last_preview": None,
        "last_apply": None,
    }
    return render_template(
        "trading212_preview.html",
        active_page="accounts" if linked_account else "settings",
        trading212_preview=preview,
        trading212_environment_label=trading212_environment_label,
        trading212_sync_support_note=trading212_sync_support_note,
        preview_back_href=url_for("accounts.account_detail", account_id=account_id) if linked_account else "/settings/#trading212-access",
        preview_back_label="Back to account" if linked_account else "Back to settings",
        trading212_match_type_label=trading212_match_type_label,
    )


def _trading212_addable_broker_rows(preview):
    return [row for row in (preview.get("broker_only") or []) if not (row.get("possible_matches") or [])]


def _trading212_resolvable_broker_rows(preview):
    return [row for row in (preview.get("broker_only") or []) if (row.get("possible_matches") or [])]


def _trading212_broker_row_by_key(preview, preview_key):
    for row in (preview.get("broker_only") or []):
        if row.get("preview_key") == preview_key:
            return row
    return None


def _trading212_update_existing_holding_from_broker_row(holding, broker_row):
    broker_units = float((broker_row or {}).get("units") or 0)
    broker_price = float((broker_row or {}).get("price") or 0)
    broker_value = float((broker_row or {}).get("value") or (broker_units * broker_price))
    return {
        "id": holding["id"],
        "account_id": holding["account_id"],
        "holding_catalogue_id": holding["holding_catalogue_id"],
        "holding_name": holding["holding_name"],
        "ticker": holding["ticker"] or "",
        "asset_type": holding["asset_type"] or "",
        "bucket": holding["bucket"] or "",
        "value": broker_value,
        "units": broker_units,
        "price": broker_price,
        "book_cost": holding["book_cost"],
        "notes": holding["notes"] or "",
    }


def _infer_trading212_holding_asset_type(row):
    text = " ".join(
        [
            str((row or {}).get("name") or ""),
            str((row or {}).get("ticker") or ""),
        ]
    ).lower()
    if any(token in text for token in ("etf", "fund", "vanguard", "ishares", "acc", "dist", "ucits")):
        return "fund"
    return "stock"


def _build_trading212_added_holding_payload(account_id, broker_row):
    units = float((broker_row or {}).get("units") or 0)
    price = float((broker_row or {}).get("price") or 0)
    value = float((broker_row or {}).get("value") or (units * price))
    return {
        "account_id": account_id,
        "holding_catalogue_id": None,
        "holding_name": (broker_row or {}).get("name") or ((broker_row or {}).get("ticker") or "Trading 212 holding"),
        "ticker": (broker_row or {}).get("ticker") or "",
        "asset_type": _infer_trading212_holding_asset_type(broker_row),
        "bucket": "stocks",
        "value": value,
        "units": units,
        "price": price,
        "notes": "Added from reviewed Trading 212 broker-only position.",
    }


def _broker_sync_event_action_label(action_type):
    labels = {
        "preview": "Broker snapshot preview saved",
        "apply_matched": "Applied matched updates",
        "apply_broker_additions": "Added broker-only positions",
        "resolve_possible_match": "Confirmed likely match",
    }
    return labels.get(action_type, str(action_type or "Sync event").replace("_", " ").title())


def _broker_sync_event_time_label(value):
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(str(value))
        return dt.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    except Exception:
        return str(value)


def _prepare_broker_sync_events(events):
    prepared = []
    for raw in (events or []):
        event = dict(raw)
        event["action_label"] = _broker_sync_event_action_label(event.get("action_type"))
        event["created_label"] = _broker_sync_event_time_label(event.get("created_at"))
        event["snapshot_label"] = _broker_sync_event_time_label(event.get("snapshot_at"))
        prepared.append(event)
    return prepared


def _recent_trading212_sync_state(user_id, connection_id):
    events = _prepare_broker_sync_events(fetch_broker_sync_events(user_id, connection_id, limit=5))
    last_preview = next((event for event in events if event.get("action_type") == "preview"), None)
    last_apply = next(
        (
            event
            for event in events
            if event.get("action_type") in {"apply_matched", "apply_broker_additions"}
        ),
        None,
    )
    return {
        "events": events,
        "last_preview": last_preview,
        "last_apply": last_apply,
    }


def _log_trading212_sync_event(*, user_id, connection_id, account_id=None, action_type, snapshot_at=None, matched_updates_count=0, broker_add_count=0, held_back_broker_count=0, tracked_only_count=0, notes=None):
    return log_broker_sync_event(
        user_id=user_id,
        connection_id=connection_id,
        account_id=account_id,
        provider=PROVIDER_TRADING212,
        action_type=action_type,
        snapshot_at=snapshot_at,
        matched_updates_count=matched_updates_count,
        broker_add_count=broker_add_count,
        held_back_broker_count=held_back_broker_count,
        tracked_only_count=tracked_only_count,
        notes=notes,
    )


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
        "trading212_access_mode_label": trading212_access_mode_label,
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
                "short": f"{last_run['run_date']} {last_run['slot']}" if last_run else "No scheduler run yet",
                "full": f"{last_run['run_date']} {last_run['slot']}" if last_run else "No scheduler run yet",
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
                "latest_name_label": "No SQLite backup yet",
                "latest_modified": None,
                "latest_size_human": None,
                "latest_age_days": None,
                "health_status": "warning",
                "health_label": "SQLite backup recommended",
                "health_message": "SQLite backup health could not be determined.",
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
    flash("Assistant token replaced. The old token no longer works, and the new raw token is only shown once.", "success")
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
        flash("Enter both the Public API key and Public API secret for this broker account.", "error")
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
        f"Saved broker snapshot {trading212_environment_label(summary['environment']).lower()} connection for {label}. "
        f"{trading212_sync_support_note()}",
        "success",
    )
    return _settings_trading212_redirect()


@settings_bp.route("/trading212/<int:connection_id>/retest", methods=["POST"])
@login_required
def retest_trading212(connection_id):
    connection = fetch_broker_connection(connection_id, current_user.id)
    if connection is None or connection.get("provider") != PROVIDER_TRADING212:
        flash(trading212_connection_not_found_message(), "error")
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
        cash_val = float(summary.get("available_to_trade") or 0) + float(summary.get("cash_in_pies") or 0) + float(summary.get("cash_reserved_for_orders") or 0)
        holdings_val = float(summary.get("investments_current_value") or 0)
        update_broker_connection_status(
            connection_id,
            current_user.id,
            status="connected",
            last_error=None,
            last_tested_at=summary["fetched_at"],
            external_account_id=summary["account_id"],
            external_account_currency=summary["currency"],
            external_total_value=summary["total_value"],
            external_cash_value=cash_val,
            external_holdings_value=holdings_val,
        )
        flash(
            f"Broker snapshot {trading212_environment_label(summary['environment']).lower()} connection retested successfully.",
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
        flash(trading212_connection_not_found_message(), "error")
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
        cash_val = float(summary.get("available_to_trade") or 0) + float(summary.get("cash_in_pies") or 0) + float(summary.get("cash_reserved_for_orders") or 0)
        holdings_val = float(summary.get("investments_current_value") or 0)
        update_broker_connection_status(
            connection_id,
            current_user.id,
            status="connected",
            last_error=None,
            last_tested_at=summary["fetched_at"],
            external_account_id=summary["account_id"],
            external_account_currency=summary["currency"],
            external_total_value=summary["total_value"],
            external_cash_value=cash_val,
            external_holdings_value=holdings_val,
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
            flash(trading212_account_not_linked_message(), "error")
            return redirect(url_for("accounts.account_detail", account_id=account_id))
    preview = _build_trading212_preview(current_user.id, refreshed_connection, snapshot, linked_account=linked_account)
    _log_trading212_sync_event(
        user_id=current_user.id,
        connection_id=connection_id,
        account_id=account_id,
        action_type="preview",
        snapshot_at=summary.get("fetched_at"),
        matched_updates_count=len(preview.get("matched_updates") or []),
        broker_add_count=len(_trading212_addable_broker_rows(preview)),
        held_back_broker_count=len(preview.get("broker_only") or []) - len(_trading212_addable_broker_rows(preview)),
        tracked_only_count=len(preview.get("db_only") or []),
        notes={"broker_only_count": len(preview.get("broker_only") or [])},
    )
    return _render_trading212_preview(preview)


@settings_bp.route("/trading212/<int:connection_id>/apply-reviewed", methods=["POST"])
@login_required
def apply_trading212_reviewed_changes(connection_id):
    connection = fetch_broker_connection(connection_id, current_user.id)
    if connection is None or connection.get("provider") != PROVIDER_TRADING212:
        flash(trading212_connection_not_found_message(), "error")
        return _settings_trading212_redirect()

    account_id = optional_int(request.form.get("account_id"), default=None)
    if not account_id:
        flash("Choose the linked account before applying matched holding updates.", "error")
        return _settings_trading212_redirect()

    linked_account = fetch_account(account_id, current_user.id)
    if linked_account is None:
        flash("Linked account not found.", "error")
        return _settings_trading212_redirect()
    if linked_account.get("linked_broker_connection_id") != connection_id:
        flash(trading212_account_not_linked_message(), "error")
        return redirect(url_for("accounts.account_detail", account_id=account_id))

    try:
        api_key = decrypt_trading212_credential(connection.get("api_key_ciphertext"))
        api_secret = decrypt_trading212_credential(connection.get("api_secret_ciphertext"))
        snapshot = fetch_trading212_portfolio_snapshot(
            api_key=api_key,
            api_secret=api_secret,
            environment=connection.get("environment") or "live",
        )
        summary = snapshot["summary"]
        cash_val = float(summary.get("available_to_trade") or 0) + float(summary.get("cash_in_pies") or 0) + float(summary.get("cash_reserved_for_orders") or 0)
        holdings_val = float(summary.get("investments_current_value") or 0)
        update_broker_connection_status(
            connection_id,
            current_user.id,
            status="connected",
            last_error=None,
            last_tested_at=summary["fetched_at"],
            external_account_id=summary["account_id"],
            external_account_currency=summary["currency"],
            external_total_value=summary["total_value"],
            external_cash_value=cash_val,
            external_holdings_value=holdings_val,
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
        return redirect(url_for("accounts.account_detail", account_id=account_id))

    refreshed_connection = fetch_broker_connection(connection_id, current_user.id) or connection
    preview = _build_trading212_preview(current_user.id, refreshed_connection, snapshot, linked_account=linked_account)

    if request.form.get("confirm_apply_matched") != "yes":
        flash("Tick the confirmation box before applying the reviewed matched updates.", "error")
        return _render_trading212_preview(preview)

    matched_updates = list(preview.get("matched_updates") or [])
    if not matched_updates:
        flash("No matched broker updates were ready to apply.", "info")
        return _render_trading212_preview(preview)

    updated = 0
    skipped = 0
    for pair in matched_updates:
        holding_row = pair.get("holding") or {}
        broker_row = pair.get("csv") or {}
        holding = fetch_holding(int(holding_row.get("id") or 0), current_user.id)
        if not holding or int(holding.get("account_id") or 0) != account_id:
            skipped += 1
            continue
        broker_units = float(broker_row.get("units") or 0)
        broker_price = float(broker_row.get("price") or 0)
        broker_value = float(broker_row.get("value") or (broker_units * broker_price))
        if update_holding({
            "id": holding["id"],
            "account_id": holding["account_id"],
            "holding_catalogue_id": holding["holding_catalogue_id"],
            "holding_name": holding["holding_name"],
            "ticker": holding["ticker"] or "",
            "asset_type": holding["asset_type"] or "",
            "bucket": holding["bucket"] or "",
            "value": broker_value,
            "units": broker_units,
            "price": broker_price,
            "book_cost": holding["book_cost"],
            "notes": holding["notes"] or "",
        }, current_user.id):
            updated += 1
        else:
            skipped += 1

    untouched_broker = len(preview.get("broker_only") or [])
    untouched_tracked = len(preview.get("db_only") or [])
    if updated:
        flash(
            f"Applied {updated} matched broker holding update{'s' if updated != 1 else ''}. "
            f"{untouched_broker} broker-only position{'s' if untouched_broker != 1 else ''} and "
            f"{untouched_tracked} tracked-only holding{'s' if untouched_tracked != 1 else ''} were left untouched for review.",
            "success",
        )
        _log_trading212_sync_event(
            user_id=current_user.id,
            connection_id=connection_id,
            account_id=account_id,
            action_type="apply_matched",
            snapshot_at=summary.get("fetched_at"),
            matched_updates_count=updated,
            broker_add_count=0,
            held_back_broker_count=untouched_broker,
            tracked_only_count=untouched_tracked,
        )
    if skipped:
        flash(f"{skipped} matched holding{'s' if skipped != 1 else ''} could not be applied.", "info")
    return redirect(url_for("accounts.account_detail", account_id=account_id))


@settings_bp.route("/trading212/<int:connection_id>/apply-cash", methods=["POST"])
@login_required
def apply_trading212_cash(connection_id):
    connection = fetch_broker_connection(connection_id, current_user.id)
    if connection is None or connection.get("provider") != PROVIDER_TRADING212:
        flash(trading212_connection_not_found_message(), "error")
        return _settings_trading212_redirect()

    account_id = optional_int(request.form.get("account_id"), default=None)
    if not account_id:
        flash("Choose the linked account before applying cash updates.", "error")
        return _settings_trading212_redirect()

    linked_account = fetch_account(account_id, current_user.id)
    if linked_account is None:
        flash("Linked account not found.", "error")
        return _settings_trading212_redirect()
    if linked_account.get("linked_broker_connection_id") != connection_id:
        flash(trading212_account_not_linked_message(), "error")
        return redirect(url_for("accounts.account_detail", account_id=account_id))

    try:
        api_key = decrypt_trading212_credential(connection.get("api_key_ciphertext"))
        api_secret = decrypt_trading212_credential(connection.get("api_secret_ciphertext"))
        snapshot = fetch_trading212_portfolio_snapshot(
            api_key=api_key,
            api_secret=api_secret,
            environment=connection.get("environment") or "live",
        )
        summary = snapshot["summary"]
        cash_val = float(summary.get("available_to_trade") or 0) + float(summary.get("cash_in_pies") or 0) + float(summary.get("cash_reserved_for_orders") or 0)
        holdings_val = float(summary.get("investments_current_value") or 0)
        update_broker_connection_status(
            connection_id,
            current_user.id,
            status="connected",
            last_error=None,
            last_tested_at=summary["fetched_at"],
            external_account_id=summary["account_id"],
            external_account_currency=summary["currency"],
            external_total_value=summary["total_value"],
            external_cash_value=cash_val,
            external_holdings_value=holdings_val,
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
        return redirect(url_for("accounts.account_detail", account_id=account_id))

    refreshed_connection = fetch_broker_connection(connection_id, current_user.id) or connection
    preview = _build_trading212_preview(current_user.id, refreshed_connection, snapshot, linked_account=linked_account)

    if request.form.get("confirm_apply_cash") != "yes":
        flash("Tick the confirmation box before applying the cash update.", "error")
        return _render_trading212_preview(preview)

    broker_cash_total = float(summary.get("available_to_trade") or 0) + float(summary.get("cash_in_pies") or 0) + float(summary.get("cash_reserved_for_orders") or 0)
    
    if (
        linked_account.get("broker_sync_focus") == "cash_only"
        or linked_account.get("category") == "Cash"
        or (linked_account.get("wrapper_type") or "").lower() == "cash isa"
    ):
        linked_account["current_value"] = broker_cash_total
        linked_account["uninvested_cash"] = 0.0
    else:
        linked_account["uninvested_cash"] = broker_cash_total
    update_account(linked_account, current_user.id)

    flash(f"Updated account cash balance to {broker_cash_total:.2f}.", "success")
    
    _log_trading212_sync_event(
        user_id=current_user.id,
        connection_id=connection_id,
        account_id=account_id,
        action_type="apply_cash",
        snapshot_at=summary.get("fetched_at"),
        matched_updates_count=0,
        broker_add_count=0,
        held_back_broker_count=0,
        tracked_only_count=0,
    )
    return redirect(url_for("accounts.account_detail", account_id=account_id))


@settings_bp.route("/trading212/<int:connection_id>/apply-reviewed-additions", methods=["POST"])
@login_required
def apply_trading212_reviewed_broker_additions(connection_id):
    connection = fetch_broker_connection(connection_id, current_user.id)
    if connection is None or connection.get("provider") != PROVIDER_TRADING212:
        flash(trading212_connection_not_found_message(), "error")
        return _settings_trading212_redirect()

    account_id = optional_int(request.form.get("account_id"), default=None)
    if not account_id:
        flash("Choose the linked account before adding broker-only positions.", "error")
        return _settings_trading212_redirect()

    linked_account = fetch_account(account_id, current_user.id)
    if linked_account is None:
        flash("Linked account not found.", "error")
        return _settings_trading212_redirect()
    if linked_account.get("linked_broker_connection_id") != connection_id:
        flash(trading212_account_not_linked_message(), "error")
        return redirect(url_for("accounts.account_detail", account_id=account_id))

    try:
        api_key = decrypt_trading212_credential(connection.get("api_key_ciphertext"))
        api_secret = decrypt_trading212_credential(connection.get("api_secret_ciphertext"))
        snapshot = fetch_trading212_portfolio_snapshot(
            api_key=api_key,
            api_secret=api_secret,
            environment=connection.get("environment") or "live",
        )
        summary = snapshot["summary"]
        cash_val = float(summary.get("available_to_trade") or 0) + float(summary.get("cash_in_pies") or 0) + float(summary.get("cash_reserved_for_orders") or 0)
        holdings_val = float(summary.get("investments_current_value") or 0)
        update_broker_connection_status(
            connection_id,
            current_user.id,
            status="connected",
            last_error=None,
            last_tested_at=summary["fetched_at"],
            external_account_id=summary["account_id"],
            external_account_currency=summary["currency"],
            external_total_value=summary["total_value"],
            external_cash_value=cash_val,
            external_holdings_value=holdings_val,
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
        return redirect(url_for("accounts.account_detail", account_id=account_id))

    refreshed_connection = fetch_broker_connection(connection_id, current_user.id) or connection
    preview = _build_trading212_preview(current_user.id, refreshed_connection, snapshot, linked_account=linked_account)

    if request.form.get("confirm_apply_broker_additions") != "yes":
        flash("Tick the confirmation box before adding reviewed broker-only positions.", "error")
        return _render_trading212_preview(preview)

    addable_broker_rows = _trading212_addable_broker_rows(preview)
    if not addable_broker_rows:
        flash("No broker-only positions were ready to add safely.", "info")
        return _render_trading212_preview(preview)

    added = 0
    skipped = 0
    for broker_row in addable_broker_rows:
        if add_holding(_build_trading212_added_holding_payload(account_id, broker_row), current_user.id):
            added += 1
        else:
            skipped += 1

    held_back_broker = len(preview.get("broker_only") or []) - len(addable_broker_rows)
    tracked_only = len(preview.get("db_only") or [])
    if added:
        flash(
            f"Added {added} reviewed broker-only position{'s' if added != 1 else ''}. "
            f"{held_back_broker} broker-only position{'s' if held_back_broker != 1 else ''} stayed out for manual review and "
            f"{tracked_only} tracked-only holding{'s' if tracked_only != 1 else ''} stayed untouched.",
            "success",
        )
        _log_trading212_sync_event(
            user_id=current_user.id,
            connection_id=connection_id,
            account_id=account_id,
            action_type="apply_broker_additions",
            snapshot_at=summary.get("fetched_at"),
            matched_updates_count=0,
            broker_add_count=added,
            held_back_broker_count=held_back_broker,
            tracked_only_count=tracked_only,
        )
    if skipped:
        flash(f"{skipped} reviewed broker-only position{'s' if skipped != 1 else ''} could not be added.", "info")
    return redirect(url_for("accounts.account_detail", account_id=account_id))


@settings_bp.route("/trading212/<int:connection_id>/resolve-possible-match", methods=["POST"])
@login_required
def resolve_trading212_possible_match(connection_id):
    connection = fetch_broker_connection(connection_id, current_user.id)
    if connection is None or connection.get("provider") != PROVIDER_TRADING212:
        flash(trading212_connection_not_found_message(), "error")
        return _settings_trading212_redirect()

    account_id = optional_int(request.form.get("account_id"), default=None)
    if not account_id:
        flash("Choose the linked account before confirming the reviewed likely match.", "error")
        return _settings_trading212_redirect()

    linked_account = fetch_account(account_id, current_user.id)
    if linked_account is None:
        flash("Linked account not found.", "error")
        return _settings_trading212_redirect()
    if linked_account.get("linked_broker_connection_id") != connection_id:
        flash(trading212_account_not_linked_message(), "error")
        return redirect(url_for("accounts.account_detail", account_id=account_id))

    try:
        api_key = decrypt_trading212_credential(connection.get("api_key_ciphertext"))
        api_secret = decrypt_trading212_credential(connection.get("api_secret_ciphertext"))
        snapshot = fetch_trading212_portfolio_snapshot(
            api_key=api_key,
            api_secret=api_secret,
            environment=connection.get("environment") or "live",
        )
        summary = snapshot["summary"]
        cash_val = float(summary.get("available_to_trade") or 0) + float(summary.get("cash_in_pies") or 0) + float(summary.get("cash_reserved_for_orders") or 0)
        holdings_val = float(summary.get("investments_current_value") or 0)
        update_broker_connection_status(
            connection_id,
            current_user.id,
            status="connected",
            last_error=None,
            last_tested_at=summary["fetched_at"],
            external_account_id=summary["account_id"],
            external_account_currency=summary["currency"],
            external_total_value=summary["total_value"],
            external_cash_value=cash_val,
            external_holdings_value=holdings_val,
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
        return redirect(url_for("accounts.account_detail", account_id=account_id))

    refreshed_connection = fetch_broker_connection(connection_id, current_user.id) or connection
    preview = _build_trading212_preview(current_user.id, refreshed_connection, snapshot, linked_account=linked_account)

    if request.form.get("confirm_resolve_possible_match") != "yes":
        flash("Tick the confirmation box before confirming this reviewed likely match.", "error")
        return _render_trading212_preview(preview)

    preview_key = (request.form.get("preview_key") or "").strip()
    selected_holding_id = optional_int(request.form.get("selected_holding_id"), default=None)
    if not preview_key or not selected_holding_id:
        flash("Choose one tracked holding before confirming this likely match.", "error")
        return _render_trading212_preview(preview)

    broker_row = _trading212_broker_row_by_key(preview, preview_key)
    if not broker_row or not (broker_row.get("possible_matches") or []):
        flash("That reviewed likely match is no longer available in this snapshot.", "error")
        return _render_trading212_preview(preview)

    candidate = next(
        (row for row in (broker_row.get("possible_matches") or []) if int(((row.get("holding") or {}).get("id") or 0)) == selected_holding_id),
        None,
    )
    if candidate is None:
        flash("Choose one of the reviewed likely match options shown for this broker position.", "error")
        return _render_trading212_preview(preview)

    holding = fetch_holding(selected_holding_id, current_user.id)
    if not holding or int(holding.get("account_id") or 0) != account_id:
        flash("That tracked holding is not available on this linked account anymore.", "error")
        return _render_trading212_preview(preview)

    if not update_holding(_trading212_update_existing_holding_from_broker_row(holding, broker_row), current_user.id):
        flash("SteadyPlan could not apply that reviewed likely match.", "error")
        return _render_trading212_preview(preview)

    untouched_broker = max(0, len(preview.get("broker_only") or []) - 1)
    tracked_only = max(0, len(preview.get("db_only") or []) - 1)
    flash(
        f"Confirmed 1 reviewed likely match for {holding.get('holding_name') or 'the tracked holding'}. "
        f"{untouched_broker} broker-only position{'s' if untouched_broker != 1 else ''} and "
        f"{tracked_only} tracked-only holding{'s' if tracked_only != 1 else ''} stayed untouched.",
        "success",
    )
    _log_trading212_sync_event(
        user_id=current_user.id,
        connection_id=connection_id,
        account_id=account_id,
        action_type="resolve_possible_match",
        snapshot_at=summary.get("fetched_at"),
        matched_updates_count=1,
        broker_add_count=0,
        held_back_broker_count=untouched_broker,
        tracked_only_count=tracked_only,
        notes={"holding_id": selected_holding_id, "broker_name": broker_row.get("name"), "broker_ticker": broker_row.get("ticker")},
    )
    return redirect(url_for("accounts.account_detail", account_id=account_id))


@settings_bp.route("/trading212/<int:connection_id>/disconnect", methods=["POST"])
@login_required
def disconnect_trading212(connection_id):
    connection = fetch_broker_connection(connection_id, current_user.id)
    if connection is None or connection.get("provider") != PROVIDER_TRADING212:
        flash(trading212_connection_not_found_message(), "error")
        return _settings_trading212_redirect()
    delete_broker_connection(connection_id, current_user.id)
    flash("Saved broker snapshot connection removed. Manual/CSV tracking stays available.", "success")
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
        flash(f"SQLite backup file created: {dest.name}", "success")
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
        flash("To overwrite this user's finance data from the export, tick the checkbox and type RESTORE to confirm.", "error")
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
        f"Restore complete. This user's finance data has been overwritten. Safety backup created first: {backup_dest.name}",
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
