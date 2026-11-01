"""User accounts and API tokens.

User CRUD + Flask-Login User class + bearer-token management for the
JSON API. Tokens are stored in plaintext (acceptable for a self-hosted
single-instance app where DB access already implies full compromise).
"""
import sqlite3
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from ._conn import get_connection


# ── User model ────────────────────────────────────────────────────────────────

class User(UserMixin):
    def __init__(self, id, username, password_hash, is_admin):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.is_admin = bool(is_admin)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


def get_user_by_id(user_id):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    return User(row["id"], row["username"], row["password_hash"], row["is_admin"])


def get_user_by_username(username):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
    if row is None:
        return None
    return User(row["id"], row["username"], row["password_hash"], row["is_admin"])


def create_user(username, password, is_admin=False):
    from datetime import datetime, timezone
    pw_hash = generate_password_hash(password)
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash, is_admin, created_at) VALUES (?, ?, ?, ?)",
            (username, pw_hash, 1 if is_admin else 0, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cursor.lastrowid


def fetch_household_members(user_id):
    """Everyone who shares a household with this user — always including themselves.

    household_id is NULL for a solo user, so nothing is shared implicitly: two
    accounts only see each other once someone has explicitly linked them.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, household_id FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return []
        if row["household_id"] is None:
            return [{"id": row["id"], "username": row["username"]}]
        rows = conn.execute(
            "SELECT id, username FROM users WHERE household_id = ? ORDER BY id",
            (row["household_id"],),
        ).fetchall()
        return [dict(r) for r in rows]


def link_household_member(user_id, username):
    """Put another user into the caller's household.

    Returns (ok, message). Refuses when the username is unknown, is the caller, or
    already belongs to a different household — merging two households is deliberately
    not automatic, because it would silently expose one group's accounts to another.
    """
    with get_connection() as conn:
        me = conn.execute(
            "SELECT id, username, household_id FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if me is None:
            return False, "You are not signed in."
        target = conn.execute(
            "SELECT id, username, household_id FROM users WHERE username = ?",
            ((username or "").strip(),),
        ).fetchone()
        if target is None:
            return False, f"No user called “{(username or '').strip()}”."
        if target["id"] == me["id"]:
            return False, "That is your own login."
        if target["household_id"] is not None and me["household_id"] is not None \
                and target["household_id"] != me["household_id"]:
            return False, "That user already belongs to a different household."
        if target["household_id"] is not None and target["household_id"] == me["household_id"]:
            return False, f"{target['username']} is already in your household."

        household_id = me["household_id"] or target["household_id"] or me["id"]
        conn.execute("UPDATE users SET household_id = ? WHERE id IN (?, ?)",
                     (household_id, me["id"], target["id"]))
        conn.commit()
        return True, f"{target['username']} added to your household."


def unlink_household_member(user_id, member_id):
    """Remove a member. When only one person is left, their household_id is cleared."""
    with get_connection() as conn:
        me = conn.execute(
            "SELECT id, household_id FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if me is None or me["household_id"] is None:
            return False, "You are not in a household."
        if member_id == user_id:
            return False, "Use the other user's login to leave."
        target = conn.execute(
            "SELECT id, username, household_id FROM users WHERE id = ?", (member_id,)
        ).fetchone()
        if target is None or target["household_id"] != me["household_id"]:
            return False, "That user is not in your household."

        conn.execute("UPDATE users SET household_id = NULL WHERE id = ?", (member_id,))
        remaining = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE household_id = ?",
            (me["household_id"],),
        ).fetchone()["n"]
        if remaining <= 1:
            conn.execute("UPDATE users SET household_id = NULL WHERE household_id = ?",
                         (me["household_id"],))
        conn.commit()
        return True, f"{target['username']} removed from your household."


def count_users():
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]


def fetch_all_users():
    with get_connection() as conn:
        return conn.execute("SELECT id, username, is_admin, created_at FROM users ORDER BY id").fetchall()


def update_user(user_id, username=None, password=None, is_admin=None):
    """Update user fields. Pass None to leave a field unchanged.
    Returns (ok, error_message).
    """
    with get_connection() as conn:
        target = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if target is None:
            return False, "User not found."
        # Check username uniqueness if changing
        if username and username != target["username"]:
            clash = conn.execute(
                "SELECT id FROM users WHERE username = ? AND id != ?", (username, user_id)
            ).fetchone()
            if clash:
                return False, f"Username '{username}' is already taken."
        # Safety: can't remove admin from the last admin
        if is_admin is False and target["is_admin"]:
            admin_count = conn.execute(
                "SELECT COUNT(*) AS n FROM users WHERE is_admin = 1"
            ).fetchone()["n"]
            if admin_count <= 1:
                return False, "Cannot remove admin rights from the only admin account."
        # Build update
        updates = []
        params = []
        if username:
            updates.append("username = ?")
            params.append(username)
        if password:
            pw_hash = generate_password_hash(password)
            updates.append("password_hash = ?")
            params.append(pw_hash)
        if is_admin is not None:
            updates.append("is_admin = ?")
            params.append(1 if is_admin else 0)

        if updates:
            params.append(user_id)
            conn.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
                tuple(params),
            )
        conn.commit()
    return True, None


def delete_user(user_id):
    """Delete a user and all their data across all tables."""
    with get_connection() as conn:
        # Safety: must not be the last admin
        admin_count = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE is_admin = 1"
        ).fetchone()["n"]
        target = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if target is None:
            return False, "User not found."
        if target["is_admin"] and admin_count <= 1:
            return False, "Cannot delete the only admin account."

        def _table_exists(table):
            return bool(
                conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (table,),
                ).fetchone()
            )

        def _table_has_column(table, column):
            try:
                cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
            except Exception:
                return False
            return any((r.get("name") == column) for r in (cols or []))

        account_ids = []
        if _table_exists("accounts") and _table_has_column("accounts", "user_id"):
            account_ids = [
                r["id"]
                for r in conn.execute("SELECT id FROM accounts WHERE user_id = ?", (user_id,)).fetchall()
            ]

        placeholders = ",".join(["?"] * len(account_ids)) if account_ids else None

        try:
            if account_ids:
                for table in [
                    "monthly_review_items",
                    "monthly_snapshots",
                    "contribution_overrides",
                    "account_daily_snapshots",
                    "premium_bonds_prizes",
                    "holdings",
                ]:
                    if not _table_exists(table) or not _table_has_column(table, "account_id"):
                        continue
                    conn.execute(
                        f"DELETE FROM {table} WHERE account_id IN ({placeholders})",
                        account_ids,
                    )

            if _table_exists("budget_entries") and _table_exists("budget_items") and _table_has_column("budget_items", "user_id"):
                conn.execute(
                    """
                    DELETE FROM budget_entries
                    WHERE budget_item_id IN (SELECT id FROM budget_items WHERE user_id = ?)
                    """,
                    (user_id,),
                )

            for table in [
                "isa_contributions",
                "cash_flow_events",
                "scheduler_runs",
                "portfolio_daily_snapshots",
                "custom_tags",
                "hidden_tags",
                "api_tokens",
                "broker_connections",
                "budget_items",
                "budget_sections",
                "monthly_reviews",
                "goals",
                "assumptions",
                "debts",
                "holding_catalogue",
            ]:
                if not _table_exists(table) or not _table_has_column(table, "user_id"):
                    continue
                conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))

            if _table_exists("budget_entries"):
                conn.execute(
                    "DELETE FROM budget_entries WHERE budget_item_id NOT IN (SELECT id FROM budget_items)"
                )

            if _table_exists("accounts") and _table_has_column("accounts", "user_id"):
                conn.execute("DELETE FROM accounts WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            return True, None
        except sqlite3.IntegrityError as e:
            conn.rollback()
            return False, f"Could not delete user due to a database foreign-key constraint: {e}"
        except Exception:
            conn.rollback()
            raise



# ── API tokens ────────────────────────────────────────────────────────────────
# Bearer tokens for the JSON API. General tokens keep legacy broad access.
# Assistant tokens are intentionally narrower and scope-limited.

API_TOKEN_KIND_GENERAL = "general"
VALID_API_TOKEN_KINDS = {API_TOKEN_KIND_GENERAL}


def _hash_token(token):
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()


def _normalise_token_kind(token_kind):
    kind = (token_kind or API_TOKEN_KIND_GENERAL).strip().lower()
    return kind if kind in VALID_API_TOKEN_KINDS else API_TOKEN_KIND_GENERAL


def _serialise_scopes(scopes):
    return ",".join(scopes or [])


def _deserialise_scopes(raw_scopes):
    values = []
    for scope in str(raw_scopes or "").split(","):
        scope_text = scope.strip().lower()
        if scope_text and scope_text not in values:
            values.append(scope_text)
    return values


def create_api_token(user_id, label=None, token_kind=API_TOKEN_KIND_GENERAL, scopes=None):
    import secrets

    kind = _normalise_token_kind(token_kind)
    raw_scopes = []   # assistant tokens are gone; kept for the api_tokens column
    token = secrets.token_hex(32)
    hashed = _hash_token(token)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO api_tokens (user_id, token, label, token_kind, scopes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, hashed, label, kind, _serialise_scopes(raw_scopes)),
        )
        conn.commit()
    return token



def authenticate_api_token(token):
    if not token:
        return None

    hashed = _hash_token(token)
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                u.*, t.id AS token_id, t.label AS token_label,
                t.created_at AS token_created_at,
                t.last_used_at AS token_last_used_at,
                COALESCE(t.token_kind, ?) AS token_kind,
                COALESCE(t.scopes, '') AS token_scopes
            FROM users u
            JOIN api_tokens t ON t.user_id = u.id
            WHERE t.token = ?
            """,
            (API_TOKEN_KIND_GENERAL, hashed),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE api_tokens SET last_used_at = datetime('now') WHERE token = ?",
            (hashed,),
        )
        conn.commit()

    token_kind = _normalise_token_kind(row["token_kind"])
    token_scopes = _deserialise_scopes(row["token_scopes"])
    return {
        "user": User(row["id"], row["username"], row["password_hash"], row["is_admin"]),
        "token": {
            "id": row["token_id"],
            "label": row["token_label"],
            "created_at": row["token_created_at"],
            "last_used_at": row["token_last_used_at"],
            "token_kind": token_kind,
            "scopes": token_scopes,
        },
    }


def fetch_user_by_api_token(token):
    auth = authenticate_api_token(token)
    return auth["user"] if auth else None


def fetch_api_tokens(user_id, token_kind=None):
    kind = _normalise_token_kind(token_kind) if token_kind else None
    sql = """
        SELECT id, label, created_at, last_used_at,
               substr(token, 1, 8) AS token_preview,
               COALESCE(token_kind, ?) AS token_kind,
               COALESCE(scopes, '') AS scopes
        FROM api_tokens
        WHERE user_id = ?
    """
    params = [API_TOKEN_KIND_GENERAL, user_id]
    if kind:
        sql += " AND COALESCE(token_kind, ?) = ?"
        params.extend([API_TOKEN_KIND_GENERAL, kind])
    sql += " ORDER BY created_at DESC, id DESC"

    with get_connection() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()

    out = []
    for row in rows:
        item = dict(row)
        item["token_kind"] = _normalise_token_kind(item.get("token_kind"))
        item["scopes"] = _deserialise_scopes(item.get("scopes"))
        out.append(item)
    return out



def fetch_api_token(token_id, user_id, token_kind=None):
    kind = _normalise_token_kind(token_kind) if token_kind else None
    sql = """
        SELECT id, user_id, label, created_at, last_used_at,
               COALESCE(token_kind, ?) AS token_kind,
               COALESCE(scopes, '') AS scopes
        FROM api_tokens
        WHERE id = ? AND user_id = ?
    """
    params = [API_TOKEN_KIND_GENERAL, token_id, user_id]
    if kind:
        sql += " AND COALESCE(token_kind, ?) = ?"
        params.extend([API_TOKEN_KIND_GENERAL, kind])
    with get_connection() as conn:
        row = conn.execute(sql, tuple(params)).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["token_kind"] = _normalise_token_kind(item.get("token_kind"))
    item["scopes"] = _deserialise_scopes(item.get("scopes"))
    return item


def revoke_api_token(token_id, user_id):
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM api_tokens WHERE id = ? AND user_id = ?",
            (token_id, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0
