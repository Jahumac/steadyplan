"""Premium Bonds prize tracking model."""
from datetime import datetime, timezone

from ._conn import get_connection
from .accounts import PREMIUM_BONDS_MAX_BALANCE


def _adjust_account_balance(conn, account_id, delta):
    """Add `delta` to the account's current_value, clamped to [0, £50k].

    NS&I credits prize winnings to the bond holding when there's room
    under the £50,000 cap; anything that would push the balance over the
    cap is paid out as cash (and is therefore not added here).
    """
    row = conn.execute(
        "SELECT current_value FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    if not row:
        return
    current = float(row["current_value"] or 0)
    new = max(0.0, min(current + delta, PREMIUM_BONDS_MAX_BALANCE))
    conn.execute(
        "UPDATE accounts SET current_value = ? WHERE id = ?", (new, account_id)
    )


def log_prize(account_id, user_id, month_key, prize_amount):
    """Upsert a prize win for a given (account, month). Zero = no win that month.

    Re-logging the same month replaces the previous amount (the difference
    is what flows through to the account balance, so editing a prize from
    £25 to £100 nets +£75 onto the balance, not +£100).
    """
    with get_connection() as conn:
        previous = conn.execute(
            "SELECT prize_amount FROM premium_bonds_prizes "
            "WHERE account_id = ? AND month_key = ?",
            (account_id, month_key),
        ).fetchone()
        previous_amount = float(previous["prize_amount"]) if previous else 0.0

        conn.execute(
            """
            INSERT INTO premium_bonds_prizes (user_id, account_id, month_key, prize_amount, logged_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(account_id, month_key) DO UPDATE SET
                prize_amount = excluded.prize_amount,
                logged_at = excluded.logged_at
            """,
            (user_id, account_id, month_key, prize_amount,
             datetime.now(timezone.utc).isoformat()),
        )
        _adjust_account_balance(conn, account_id, float(prize_amount) - previous_amount)
        conn.commit()


def fetch_prizes(account_id, user_id):
    """Return all prize rows for an account, newest first."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, month_key, prize_amount, logged_at
            FROM premium_bonds_prizes
            WHERE account_id = ? AND user_id = ?
            ORDER BY month_key DESC
            """,
            (account_id, user_id),
        ).fetchall()
    return [dict(r) for r in rows]


def fetch_prize_for_month(account_id, month_key):
    """Return the prize row for a specific month, or None."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, month_key, prize_amount, logged_at
            FROM premium_bonds_prizes
            WHERE account_id = ? AND month_key = ?
            """,
            (account_id, month_key),
        ).fetchone()
    return dict(row) if row else None


def fetch_prizes_tax_year(account_id, user_id, ty_start_month, ty_end_month):
    """Return total prize winnings between two month_keys (inclusive)."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(prize_amount), 0) AS total
            FROM premium_bonds_prizes
            WHERE account_id = ? AND user_id = ?
              AND month_key >= ? AND month_key <= ?
            """,
            (account_id, user_id, ty_start_month, ty_end_month),
        ).fetchone()
    return float(row["total"]) if row else 0.0


def delete_prize(prize_id, user_id):
    """Remove a prize entry (ownership-checked via user_id).

    Also removes the prize amount from the account balance so deleting a
    win mistakenly logged earlier reverts the balance change it made.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT account_id, prize_amount FROM premium_bonds_prizes "
            "WHERE id = ? AND user_id = ?",
            (prize_id, user_id),
        ).fetchone()
        if not row:
            return
        conn.execute(
            "DELETE FROM premium_bonds_prizes WHERE id = ? AND user_id = ?",
            (prize_id, user_id),
        )
        _adjust_account_balance(
            conn, row["account_id"], -float(row["prize_amount"] or 0)
        )
        conn.commit()
