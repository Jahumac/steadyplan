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
        if username:
            conn.execute("UPDATE users SET username = ? WHERE id = ?", (username, user_id))
        if password:
            pw_hash = generate_password_hash(password)
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user_id))
        if is_admin is not None:
            conn.execute("UPDATE users SET is_admin = ? WHERE id = ?", (int(is_admin), user_id))
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
                "pension_contributions",
                "dividend_records",
                "cgt_disposals",
                "pension_carry_forward",
                "allowance_tracking",
                "cash_flow_events",
                "scheduler_runs",
                "portfolio_daily_snapshots",
                "custom_tags",
                "api_tokens",
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
# Bearer tokens for the JSON API. Mint via scripts/api_token.py create <user>.
# Tokens are stored as SHA-256 hashes.

def _hash_token(token):
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()


def create_api_token(user_id, label=None):
    import secrets
    token = secrets.token_hex(32)
    hashed = _hash_token(token)
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO api_tokens (user_id, token, label) VALUES (?, ?, ?)",
            (user_id, hashed, label),
        )
        conn.commit()
    return token


def fetch_user_by_api_token(token):
    if not token:
        return None
    hashed = _hash_token(token)
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT u.* FROM users u
            JOIN api_tokens t ON t.user_id = u.id
            WHERE t.token = ?
            """,
            (hashed,),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE api_tokens SET last_used_at = datetime('now') WHERE token = ?",
            (hashed,),
        )
        conn.commit()
    return User(row["id"], row["username"], row["password_hash"], row["is_admin"])


def fetch_api_tokens(user_id):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT id, label, created_at, last_used_at,
                   substr(token, 1, 8) AS token_preview
            FROM api_tokens WHERE user_id = ? ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()


def revoke_api_token(token_id, user_id):
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM api_tokens WHERE id = ? AND user_id = ?",
            (token_id, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0
