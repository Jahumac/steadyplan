"""Broker and external integration connection records."""

import json
from datetime import datetime, timezone

from ._conn import get_connection


PROVIDER_TRADING212 = "trading212"
TRADING212_ENV_LIVE = "live"
TRADING212_ENV_DEMO = "demo"
VALID_TRADING212_ENVS = {TRADING212_ENV_LIVE, TRADING212_ENV_DEMO}


def _row_to_connection(row):
    if not row:
        return None
    item = dict(row)
    item["is_active"] = bool(item.get("is_active", 1))
    return item


def fetch_broker_connections(user_id, provider=None, include_inactive=False):
    query = "SELECT * FROM broker_connections WHERE user_id = ?"
    params = [user_id]
    if provider:
        query += " AND provider = ?"
        params.append(provider)
    if not include_inactive:
        query += " AND is_active = 1"
    query += " ORDER BY provider ASC, environment ASC, id ASC"
    with get_connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return [_row_to_connection(row) for row in rows]


def fetch_broker_connection(connection_id, user_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM broker_connections WHERE id = ? AND user_id = ? LIMIT 1",
            (connection_id, user_id),
        ).fetchone()
    return _row_to_connection(row)


def upsert_broker_connection(
    *,
    user_id,
    provider,
    environment,
    label,
    access_mode,
    api_key_ciphertext,
    api_secret_ciphertext,
    status,
    last_error=None,
    last_tested_at=None,
    external_account_id=None,
    external_account_currency=None,
    external_total_value=None,
):
    now = datetime.now(timezone.utc).isoformat()
    tested_at = last_tested_at or now
    external_account_id = (str(external_account_id).strip() if external_account_id is not None else None) or None
    with get_connection() as conn:
        if external_account_id:
            existing = conn.execute(
                """
                SELECT id
                FROM broker_connections
                WHERE user_id = ?
                  AND provider = ?
                  AND environment = ?
                  AND external_account_id = ?
                LIMIT 1
                """,
                (user_id, provider, environment, external_account_id),
            ).fetchone()
        else:
            existing = conn.execute(
                """
                SELECT id
                FROM broker_connections
                WHERE user_id = ? AND provider = ? AND environment = ? AND label = ?
                LIMIT 1
                """,
                (user_id, provider, environment, label),
            ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE broker_connections
                SET label = ?,
                    access_mode = ?,
                    api_key_ciphertext = ?,
                    api_secret_ciphertext = ?,
                    status = ?,
                    last_error = ?,
                    last_tested_at = ?,
                    external_account_id = ?,
                    external_account_currency = ?,
                    external_total_value = ?,
                    is_active = 1,
                    updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (
                    label,
                    access_mode,
                    api_key_ciphertext,
                    api_secret_ciphertext,
                    status,
                    last_error,
                    tested_at,
                    external_account_id,
                    external_account_currency,
                    external_total_value,
                    now,
                    existing["id"],
                    user_id,
                ),
            )
            connection_id = existing["id"]
        else:
            cursor = conn.execute(
                """
                INSERT INTO broker_connections (
                    user_id,
                    provider,
                    label,
                    environment,
                    access_mode,
                    api_key_ciphertext,
                    api_secret_ciphertext,
                    status,
                    last_error,
                    last_tested_at,
                    external_account_id,
                    external_account_currency,
                    external_total_value,
                    is_active,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    user_id,
                    provider,
                    label,
                    environment,
                    access_mode,
                    api_key_ciphertext,
                    api_secret_ciphertext,
                    status,
                    last_error,
                    tested_at,
                    external_account_id,
                    external_account_currency,
                    external_total_value,
                    now,
                    now,
                ),
            )
            connection_id = cursor.lastrowid
        conn.commit()
    return fetch_broker_connection(connection_id, user_id)


def update_broker_connection_status(
    connection_id,
    user_id,
    *,
    status,
    last_error=None,
    last_tested_at=None,
    external_account_id=None,
    external_account_currency=None,
    external_total_value=None,
    external_cash_value=None,
    external_holdings_value=None,
):
    now = datetime.now(timezone.utc).isoformat()
    tested_at = last_tested_at or now
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE broker_connections
            SET status = ?,
                last_error = ?,
                last_tested_at = ?,
                external_account_id = ?,
                external_account_currency = ?,
                external_total_value = ?,
                external_cash_value = ?,
                external_holdings_value = ?,
                updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                status,
                last_error,
                tested_at,
                external_account_id,
                external_account_currency,
                external_total_value,
                external_cash_value,
                external_holdings_value,
                now,
                connection_id,
                user_id,
            ),
        )
        conn.commit()
    return fetch_broker_connection(connection_id, user_id)


def log_broker_sync_event(
    *,
    user_id,
    connection_id,
    provider,
    action_type,
    account_id=None,
    status="success",
    snapshot_at=None,
    matched_updates_count=0,
    broker_add_count=0,
    held_back_broker_count=0,
    tracked_only_count=0,
    notes=None,
):
    created_at = datetime.now(timezone.utc).isoformat()
    payload = notes
    if isinstance(payload, (dict, list)):
        payload = json.dumps(payload, sort_keys=True)
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO broker_sync_events (
                user_id,
                connection_id,
                account_id,
                provider,
                action_type,
                status,
                snapshot_at,
                matched_updates_count,
                broker_add_count,
                held_back_broker_count,
                tracked_only_count,
                notes,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                connection_id,
                account_id,
                provider,
                action_type,
                status,
                snapshot_at,
                int(matched_updates_count or 0),
                int(broker_add_count or 0),
                int(held_back_broker_count or 0),
                int(tracked_only_count or 0),
                payload,
                created_at,
            ),
        )
        conn.commit()
        event_id = cursor.lastrowid
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM broker_sync_events WHERE id = ?", (event_id,)).fetchone()
    return dict(row) if row else None


def fetch_broker_sync_events(user_id, connection_id, limit=5):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM broker_sync_events
            WHERE user_id = ? AND connection_id = ?
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT ?
            """,
            (user_id, connection_id, int(limit or 5)),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_broker_connection(connection_id, user_id):
    with get_connection() as conn:
        conn.execute(
            "UPDATE accounts SET linked_broker_connection_id = NULL WHERE user_id = ? AND linked_broker_connection_id = ?",
            (user_id, connection_id),
        )
        conn.execute(
            "DELETE FROM broker_connections WHERE id = ? AND user_id = ?",
            (connection_id, user_id),
        )
        conn.commit()
