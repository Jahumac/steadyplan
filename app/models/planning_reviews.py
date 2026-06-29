"""Monthly reviews: fetch, create, update, review items, contribution flags."""
from app.calculations import (
    to_decimal,
    select_best_matching_override,
)
from ._conn import get_connection
from .accounts import fetch_all_accounts


def _fetch_all_overrides_for_user(conn, user_id, month_key):
    rows = conn.execute(
        """
        SELECT o.*
        FROM contribution_overrides o
        JOIN accounts a ON a.id = o.account_id
        WHERE a.user_id = ?
          AND o.from_month <= ?
          AND o.to_month >= ?
        ORDER BY o.account_id, o.id DESC
        """,
        (user_id, month_key, month_key)
    ).fetchall()
    overrides_by_acc = {}
    for r in rows:
        overrides_by_acc.setdefault(int(r["account_id"]), []).append(dict(r))
    return overrides_by_acc

def _expected_contribution_from_bulk(account_id, overrides_by_acc, month_key, fallback_val):
    overrides = overrides_by_acc.get(int(account_id), [])
    selected = select_best_matching_override(overrides, month_key)
    if selected is not None:
        return to_decimal(selected["override_amount"])
    return to_decimal(fallback_val)


def fetch_or_create_monthly_review(month_key, user_id):
    with get_connection() as conn:
        review = conn.execute(
            "SELECT * FROM monthly_reviews WHERE month_key = ? AND user_id = ?",
            (month_key, user_id),
        ).fetchone()

        if review is None:
            conn.execute(
                """
                INSERT INTO monthly_reviews (user_id, month_key, status, created_at, updated_at)
                VALUES (?, ?, 'not_started', datetime('now'), datetime('now'))
                """,
                (user_id, month_key),
            )
            conn.commit()
            review = conn.execute(
                "SELECT * FROM monthly_reviews WHERE month_key = ? AND user_id = ?",
                (month_key, user_id),
            ).fetchone()

        return review


def fetch_monthly_review(month_key, user_id):
    """Read-only fetch — returns None if no review exists (never creates one)."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM monthly_reviews WHERE month_key = ? AND user_id = ?",
            (month_key, user_id),
        ).fetchone()


def fetch_monthly_review_items(review_id):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT mri.*, a.name AS account_name, a.provider, a.wrapper_type, a.valuation_mode,
                   a.monthly_contribution AS account_monthly_contribution, a.current_value
            FROM monthly_review_items mri
            JOIN accounts a ON a.id = mri.account_id
            WHERE mri.review_id = ?
            ORDER BY a.id ASC
            """,
            (review_id,),
        ).fetchall()


def ensure_monthly_review_items(review_id, user_id):
    accounts = fetch_all_accounts(user_id)
    with get_connection() as conn:
        review = conn.execute(
            "SELECT month_key, status FROM monthly_reviews WHERE id = ? AND user_id = ?",
            (review_id, user_id),
        ).fetchone()
        if not review:
            return
        month_key = review["month_key"]
        is_complete = review["status"] == "complete"

        existing_rows = conn.execute(
            "SELECT account_id, expected_contribution FROM monthly_review_items WHERE review_id = ?",
            (review_id,),
        ).fetchall()
        existing_map = {row["account_id"]: to_decimal(row["expected_contribution"]) for row in existing_rows}

        overrides_by_acc = _fetch_all_overrides_for_user(conn, user_id, month_key)

        for account in accounts:
            expected = _expected_contribution_from_bulk(
                account["id"],
                overrides_by_acc,
                month_key,
                account["monthly_contribution"],
            )

            if account["id"] not in existing_map:
                conn.execute(
                    """
                    INSERT INTO monthly_review_items (
                        review_id, account_id, expected_contribution,
                        contribution_confirmed, holdings_updated, balance_updated, notes
                    )
                    VALUES (?, ?, ?, 0, 0, 0, '')
                    """,
                    (review_id, account["id"], expected),
                )
            elif not is_complete and existing_map[account["id"]] != expected:
                # Sync when account contribution changed and review isn't locked
                conn.execute(
                    """
                    UPDATE monthly_review_items
                    SET expected_contribution = ?
                    WHERE review_id = ? AND account_id = ?
                    """,
                    (expected, review_id, account["id"]),
                )
        conn.commit()


def preview_monthly_review_items(review, user_id):
    """Build the monthly review rows without writing anything to the database."""
    accounts = fetch_all_accounts(user_id)
    month_key = review["month_key"]
    is_complete = review["status"] == "complete"

    with get_connection() as conn:
        existing_rows = []
        if review.get("id") is not None:
            existing_rows = conn.execute(
                "SELECT * FROM monthly_review_items WHERE review_id = ? ORDER BY account_id ASC",
                (review["id"],),
            ).fetchall()
        existing_map = {row["account_id"]: row for row in existing_rows}
        preview = []

        overrides_by_acc = _fetch_all_overrides_for_user(conn, user_id, month_key)

        for account in accounts:
            expected = _expected_contribution_from_bulk(
                account["id"],
                overrides_by_acc,
                month_key,
                account_monthly_personal_total(account),
            )
            existing = existing_map.get(account["id"], {})
            preview.append({
                "id": existing.get("id"),
                "review_id": review.get("id"),
                "account_id": account["id"],
                "expected_contribution": existing.get("expected_contribution") if (is_complete and existing) else expected,
                "contribution_confirmed": existing.get("contribution_confirmed", 0),
                "holdings_updated": existing.get("holdings_updated", 0),
                "balance_updated": existing.get("balance_updated", 0),
                "notes": existing.get("notes", ""),
                "account_name": account["name"],
                "provider": account.get("provider"),
                "wrapper_type": account.get("wrapper_type"),
                "valuation_mode": account.get("valuation_mode"),
                "account_monthly_contribution": account_monthly_personal_total(account),
                "current_value": account.get("current_value"),
            })

        return preview


def update_monthly_review(review_id, status, notes, user_id=None):
    user_clause = " AND user_id = ?" if user_id is not None else ""
    with get_connection() as conn:
        if status == "complete":
            conn.execute(
                f"""
                UPDATE monthly_reviews
                SET status = ?, notes = ?, completed_at = datetime('now'), updated_at = datetime('now')
                WHERE id = ?{user_clause}
                """,
                (status, notes, review_id) if user_id is None else (status, notes, review_id, user_id),
            )
        else:
            conn.execute(
                f"""
                UPDATE monthly_reviews
                SET status = ?, notes = ?, completed_at = NULL, updated_at = datetime('now')
                WHERE id = ?{user_clause}
                """,
                (status, notes, review_id) if user_id is None else (status, notes, review_id, user_id),
            )
        conn.commit()


def update_monthly_review_notes(review_id, notes, user_id):
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE monthly_reviews
            SET notes = ?, updated_at = datetime('now')
            WHERE id = ? AND user_id = ?
            """,
            (notes, review_id, user_id),
        )
        conn.commit()


def update_monthly_review_item(payload):
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE monthly_review_items
            SET expected_contribution = ?,
                contribution_confirmed = ?,
                holdings_updated = ?,
                balance_updated = ?,
                notes = ?
            WHERE id = ?
            """,
            (
                payload["expected_contribution"],
                payload["contribution_confirmed"],
                payload["holdings_updated"],
                payload["balance_updated"],
                payload["notes"],
                payload["id"],
            ),
        )
        conn.commit()


def set_contribution_confirmed(item_id, review_id, confirmed):
    """Toggle contribution_confirmed for a single review item."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE monthly_review_items SET contribution_confirmed = ? WHERE id = ? AND review_id = ?",
            (1 if confirmed else 0, item_id, review_id),
        )
        conn.commit()


def fetch_tax_year_contributions(user_id, from_month, to_month):
    """Return per-account contribution data for months in a tax year range.

    from_month / to_month: 'YYYY-MM' strings (inclusive).
    Returns a list of dicts: {account_id, account_name, wrapper_type, month_key,
                               expected_contribution, contribution_confirmed}
    """
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT
                a.id AS account_id,
                a.name AS account_name,
                a.wrapper_type,
                mr.month_key,
                mri.expected_contribution,
                mri.contribution_confirmed,
                CASE WHEN co.id IS NOT NULL THEN 1 ELSE 0 END AS is_skipped
            FROM monthly_review_items mri
            JOIN monthly_reviews mr ON mr.id = mri.review_id
            JOIN accounts a ON a.id = mri.account_id
            LEFT JOIN contribution_overrides co
                   ON co.account_id = mri.account_id
                  AND mr.month_key >= co.from_month
                  AND mr.month_key <= co.to_month
                  AND co.override_amount = 0
            WHERE mr.user_id = ?
              AND mr.month_key >= ?
              AND mr.month_key <= ?
            ORDER BY a.name ASC, mr.month_key ASC
            """,
            (user_id, from_month, to_month),
        ).fetchall()


def fetch_completed_tax_year_contributions(user_id, from_month, to_month):
    """Return per-account contribution data for completed monthly reviews only.

    Draft reviews (not_started / in_progress) are excluded so they cannot affect
    allowance/performance truth. Unconfirmed rows are excluded unless the month
    was explicitly skipped (override_amount = 0).
    """
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT
                a.id AS account_id,
                a.name AS account_name,
                a.wrapper_type,
                mr.month_key,
                mri.expected_contribution,
                mri.contribution_confirmed,
                CASE WHEN co.id IS NOT NULL THEN 1 ELSE 0 END AS is_skipped
            FROM monthly_review_items mri
            JOIN monthly_reviews mr ON mr.id = mri.review_id
            JOIN accounts a ON a.id = mri.account_id
            LEFT JOIN contribution_overrides co
                   ON co.account_id = mri.account_id
                  AND mr.month_key >= co.from_month
                  AND mr.month_key <= co.to_month
                  AND co.override_amount = 0
            WHERE mr.user_id = ?
              AND mr.status = 'complete'
              AND mr.month_key >= ?
              AND mr.month_key <= ?
              AND (mri.contribution_confirmed = 1 OR co.id IS NOT NULL)
            ORDER BY a.name ASC, mr.month_key ASC
            """,
            (user_id, from_month, to_month),
        ).fetchall()


def mark_review_item_updated(review_id, account_id, field):
    """Mark holdings_updated or balance_updated = 1 for a review item."""
    if field == "holdings_updated":
        col = "holdings_updated"
    elif field == "balance_updated":
        col = "balance_updated"
    else:
        return
    with get_connection() as conn:
        conn.execute(
            f"UPDATE monthly_review_items SET {col} = 1 WHERE review_id = ? AND account_id = ?",
            (review_id, account_id),
        )
        conn.commit()
