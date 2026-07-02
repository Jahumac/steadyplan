"""Allowance tracking: ISA, pension, dividend, CGT, carry-forward, overrides."""
from collections import defaultdict
from datetime import datetime, timezone
from app.calculations import (
    to_decimal,
    add_months_to_key,
    select_best_matching_override,
)
from ._conn import get_connection


# ── Allowance tracking row ────────────────────────────────────────────────────

def fetch_allowance_tracking(user_id=None):
    """Return the most recent allowance_tracking row for a user."""
    with get_connection() as conn:
        if not user_id:
            return None
        return conn.execute(
            "SELECT * FROM allowance_tracking WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()


def upsert_allowance_tracking(user_id, tax_year, isa_used=0.0, lisa_used=0.0, notes=None):
    """Insert or update a user's allowance tracking row for a tax year."""
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM allowance_tracking WHERE user_id = ? AND tax_year = ?",
            (user_id, tax_year),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE allowance_tracking
                SET isa_used = ?, lisa_used = ?, notes = ?
                WHERE id = ? AND user_id = ?
                """,
                (isa_used, lisa_used, notes, existing["id"], user_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO allowance_tracking (user_id, tax_year, isa_used, lisa_used, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, tax_year, isa_used, lisa_used, notes),
            )
        conn.commit()
        return True


# ── ISA contributions ─────────────────────────────────────────────────────────

def _account_belongs_to_user(conn, account_id, user_id):
    return conn.execute(
        "SELECT 1 FROM accounts WHERE id = ? AND user_id = ?",
        (account_id, user_id),
    ).fetchone() is not None


TEMPORARY_PLAN_PREFIX = "temporary_plan:"


def _temporary_plan_reason(plan_name):
    plan_name = (plan_name or "").strip()
    return f"{TEMPORARY_PLAN_PREFIX}{plan_name}" if plan_name else ""


def _plan_name_from_reason(reason):
    reason = (reason or "").strip()
    if reason.startswith(TEMPORARY_PLAN_PREFIX):
        return reason[len(TEMPORARY_PLAN_PREFIX):]
    return reason





def add_isa_contribution(user_id, account_id, amount, contribution_date, note=None):
    with get_connection() as conn:
        if not _account_belongs_to_user(conn, account_id, user_id):
            return False
        conn.execute(
            """
            INSERT INTO isa_contributions (user_id, account_id, amount, contribution_date, note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, account_id, amount, contribution_date, note),
        )
        conn.commit()
        return True


def fetch_isa_contributions(user_id, tax_year_start, tax_year_end):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT c.*, a.name AS account_name, a.wrapper_type
            FROM isa_contributions c
            JOIN accounts a ON a.id = c.account_id
            WHERE c.user_id = ?
              AND a.user_id = c.user_id
              AND c.contribution_date >= ?
              AND c.contribution_date <= ?
            ORDER BY c.contribution_date DESC
            """,
            (user_id, tax_year_start, tax_year_end),
        ).fetchall()


def delete_isa_contribution(contribution_id, user_id):
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM isa_contributions WHERE id = ? AND user_id = ?",
            (contribution_id, user_id),
        )
        conn.commit()


# ── Pension contributions ─────────────────────────────────────────────────────

def add_pension_contribution(user_id, account_id, amount, kind, contribution_date, note=None):
    with get_connection() as conn:
        if not _account_belongs_to_user(conn, account_id, user_id):
            return False
        conn.execute(
            """
            INSERT INTO pension_contributions (user_id, account_id, amount, kind, contribution_date, note)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, account_id, amount, kind, contribution_date, note),
        )
        conn.commit()
        return True


def fetch_pension_contributions(user_id, tax_year_start, tax_year_end):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT c.*, a.name AS account_name, a.wrapper_type
            FROM pension_contributions c
            JOIN accounts a ON a.id = c.account_id
            WHERE c.user_id = ?
              AND a.user_id = c.user_id
              AND c.contribution_date >= ?
              AND c.contribution_date <= ?
            ORDER BY c.contribution_date DESC
            """,
            (user_id, tax_year_start, tax_year_end),
        ).fetchall()


def delete_pension_contribution(contribution_id, user_id):
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM pension_contributions WHERE id = ? AND user_id = ?",
            (contribution_id, user_id),
        )
        conn.commit()


# ── Dividend records ──────────────────────────────────────────────────────────

def add_dividend_record(user_id, account_id, amount, dividend_date, note=None):
    with get_connection() as conn:
        if not _account_belongs_to_user(conn, account_id, user_id):
            return False
        conn.execute(
            """
            INSERT INTO dividend_records (user_id, account_id, amount, dividend_date, note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, account_id, amount, dividend_date, note),
        )
        conn.commit()
        return True


def fetch_dividend_records(user_id, tax_year_start, tax_year_end):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT d.*, a.name AS account_name, a.wrapper_type
            FROM dividend_records d
            JOIN accounts a ON a.id = d.account_id
            WHERE d.user_id = ?
              AND a.user_id = d.user_id
              AND d.dividend_date >= ?
              AND d.dividend_date <= ?
            ORDER BY d.dividend_date DESC
            """,
            (user_id, tax_year_start, tax_year_end),
        ).fetchall()


def delete_dividend_record(record_id, user_id):
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM dividend_records WHERE id = ? AND user_id = ?",
            (record_id, user_id),
        )
        conn.commit()


# ── CGT disposals ─────────────────────────────────────────────────────────────

def add_cgt_disposal(user_id, disposal_date, asset_name, proceeds, cost_basis, note=None, account_id=None):
    with get_connection() as conn:
        if account_id is not None and not _account_belongs_to_user(conn, account_id, user_id):
            return False
        conn.execute(
            """
            INSERT INTO cgt_disposals (user_id, disposal_date, asset_name, proceeds, cost_basis, note, account_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, disposal_date, asset_name, proceeds, cost_basis, note, account_id),
        )
        conn.commit()
        return True


def fetch_cgt_disposals(user_id, tax_year_start, tax_year_end):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT c.*, a.name AS account_name
            FROM cgt_disposals c
            LEFT JOIN accounts a ON a.id = c.account_id AND a.user_id = c.user_id
            WHERE c.user_id = ?
              AND c.disposal_date >= ?
              AND c.disposal_date <= ?
            ORDER BY c.disposal_date DESC
            """,
            (user_id, tax_year_start, tax_year_end),
        ).fetchall()


def delete_cgt_disposal(disposal_id, user_id):
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM cgt_disposals WHERE id = ? AND user_id = ?",
            (disposal_id, user_id),
        )
        conn.commit()


# ── Pension carry-forward ─────────────────────────────────────────────────────

def fetch_pension_carry_forward(user_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM pension_carry_forward WHERE user_id = ? ORDER BY tax_year DESC",
            (user_id,),
        ).fetchall()


def upsert_pension_carry_forward(user_id, tax_year, unused_allowance):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO pension_carry_forward (user_id, tax_year, unused_allowance)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, tax_year) DO UPDATE SET unused_allowance = excluded.unused_allowance
            """,
            (user_id, tax_year, unused_allowance),
        )
        conn.commit()


def delete_pension_carry_forward(entry_id, user_id):
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM pension_carry_forward WHERE id = ? AND user_id = ?",
            (entry_id, user_id),
        )
        conn.commit()


# ── Contribution overrides ────────────────────────────────────────────────────

def fetch_contribution_overrides(account_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM contribution_overrides WHERE account_id = ? ORDER BY from_month ASC",
            (account_id,),
        ).fetchall()


def fetch_contribution_overrides_for_accounts(account_ids):
    account_ids = [int(account_id) for account_id in account_ids or []]
    if not account_ids:
        return {}

    placeholders = ", ".join("?" for _ in account_ids)
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM contribution_overrides WHERE account_id IN ({placeholders}) ORDER BY account_id ASC, from_month ASC",
            tuple(account_ids),
        ).fetchall()

    grouped = {account_id: [] for account_id in account_ids}
    for row in rows:
        grouped.setdefault(row["account_id"], []).append(row)
    return grouped


def fetch_contribution_overrides_for_reason(account_id, user_id, reason):
    with get_connection() as conn:
        if not _account_belongs_to_user(conn, account_id, user_id):
            return []
        return conn.execute(
            """
            SELECT * FROM contribution_overrides
            WHERE account_id = ? AND reason = ?
            ORDER BY from_month ASC
            """,
            (account_id, reason),
        ).fetchall()


def delete_contribution_overrides_for_reason(account_id, user_id, reason):
    with get_connection() as conn:
        deleted = _delete_overrides_for_reason(conn, account_id, user_id, reason)
        conn.commit()
        return deleted


def create_temporary_contribution_plan(user_id, plan_name, rows):
    reason = _temporary_plan_reason(plan_name)
    if not reason:
        return {"ok": False, "reason": None, "created_count": 0}

    prepared_rows = []
    touched_ranges = {}
    for row in rows or []:
        try:
            account_id = int(row["account_id"])
            override_amount = to_decimal(row["override_amount"])
        except (KeyError, TypeError, ValueError):
            continue
        component = "total"
        from_month = str(row.get("from_month") or "").strip()
        to_month = str(row.get("to_month") or "").strip()
        if not from_month or not to_month:
            continue
        if _month_key_to_index(from_month) is None or _month_key_to_index(to_month) is None:
            continue
        if _month_key_to_index(from_month) > _month_key_to_index(to_month):
            continue
        prepared_rows.append({
            "account_id": account_id,
            "component": component,
            "from_month": from_month,
            "to_month": to_month,
            "override_amount": override_amount,
            "reason": reason,
        })
        existing = touched_ranges.get(account_id)
        if existing is None:
            touched_ranges[account_id] = {"from_month": from_month, "to_month": to_month}
        else:
            existing["from_month"] = min(existing["from_month"], from_month)
            existing["to_month"] = max(existing["to_month"], to_month)

    with get_connection() as conn:
        account_ids = {row["account_id"] for row in prepared_rows}
        if account_ids:
            placeholders = ", ".join("?" for _ in account_ids)
            owned_ids = {
                row["id"]
                for row in conn.execute(
                    f"SELECT id FROM accounts WHERE user_id = ? AND id IN ({placeholders})",
                    (user_id, *sorted(account_ids)),
                ).fetchall()
            }
            prepared_rows = [row for row in prepared_rows if row["account_id"] in owned_ids]
            touched_ranges = {
                account_id: bounds
                for account_id, bounds in touched_ranges.items()
                if account_id in owned_ids
            }

        existing_rows = conn.execute(
            """
            SELECT co.account_id, co.from_month, co.to_month
            FROM contribution_overrides co
            JOIN accounts a ON a.id = co.account_id
            WHERE a.user_id = ? AND co.reason = ?
            """,
            (user_id, reason),
        ).fetchall()
        if existing_rows:
            for row in existing_rows:
                bounds = touched_ranges.setdefault(
                    row["account_id"],
                    {"from_month": row["from_month"], "to_month": row["to_month"]},
                )
                bounds["from_month"] = min(bounds["from_month"], row["from_month"])
                bounds["to_month"] = max(bounds["to_month"], row["to_month"])
            conn.execute(
                """
                DELETE FROM contribution_overrides
                WHERE reason = ?
                  AND account_id IN (SELECT id FROM accounts WHERE user_id = ?)
                """,
                (reason, user_id),
            )

        created_at = datetime.now(timezone.utc).isoformat()
        for row in prepared_rows:
            conn.execute(
                """
                INSERT INTO contribution_overrides (account_id, from_month, to_month, override_amount, component, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["account_id"],
                    row["from_month"],
                    row["to_month"],
                    row["override_amount"],
                    row["component"],
                    reason,
                    created_at,
                ),
            )

        for account_id, bounds in touched_ranges.items():
            _recalculate_review_items_for_account_month_range(
                conn,
                account_id,
                user_id,
                bounds["from_month"],
                bounds["to_month"],
            )

        conn.commit()
        return {
            "ok": True,
            "reason": reason,
            "plan_name": _plan_name_from_reason(reason),
            "created_count": len(prepared_rows),
        }


def fetch_temporary_contribution_plans(user_id):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                co.*,
                a.name AS account_name,
                a.wrapper_type,
                a.user_id
            FROM contribution_overrides co
            JOIN accounts a ON a.id = co.account_id
            WHERE a.user_id = ?
              AND co.reason LIKE ?
            ORDER BY co.created_at DESC, co.reason ASC, a.name ASC, co.from_month ASC, co.id ASC
            """,
            (user_id, f"{TEMPORARY_PLAN_PREFIX}%"),
        ).fetchall()

    grouped = {}
    for row in rows:
        reason = row["reason"]
        plan = grouped.setdefault(reason, {
            "reason": reason,
            "plan_name": _plan_name_from_reason(reason),
            "created_at": row["created_at"],
            "from_month": row["from_month"],
            "to_month": row["to_month"],
            "rows": [],
        })
        plan["created_at"] = max(plan["created_at"] or "", row["created_at"] or "")
        plan["from_month"] = min(plan["from_month"], row["from_month"])
        plan["to_month"] = max(plan["to_month"], row["to_month"])
        plan["rows"].append({
            "id": row["id"],
            "account_id": row["account_id"],
            "account_name": row["account_name"],
            "component": row["component"] or "invested",
            "wrapper_type": row["wrapper_type"],
            "from_month": row["from_month"],
            "to_month": row["to_month"],
            "override_amount": to_decimal(row["override_amount"]),
            "created_at": row["created_at"],
        })

    return sorted(
        grouped.values(),
        key=lambda row: (row["created_at"] or "", row["plan_name"].lower()),
        reverse=True,
    )


def delete_temporary_contribution_plan(user_id, plan_name_or_reason):
    raw_reason = (plan_name_or_reason or "").strip()
    reason = (
        raw_reason
        if raw_reason.startswith(TEMPORARY_PLAN_PREFIX)
        else _temporary_plan_reason(raw_reason)
    )
    if not reason:
        return 0

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT co.account_id, co.from_month, co.to_month
            FROM contribution_overrides co
            JOIN accounts a ON a.id = co.account_id
            WHERE a.user_id = ?
              AND co.reason = ?
            ORDER BY co.account_id ASC, co.from_month ASC
            """,
            (user_id, reason),
        ).fetchall()
        if not rows:
            return 0

        by_account = defaultdict(lambda: {"from_month": None, "to_month": None})
        for row in rows:
            bounds = by_account[row["account_id"]]
            bounds["from_month"] = row["from_month"] if bounds["from_month"] is None else min(bounds["from_month"], row["from_month"])
            bounds["to_month"] = row["to_month"] if bounds["to_month"] is None else max(bounds["to_month"], row["to_month"])

        cur = conn.execute(
            """
            DELETE FROM contribution_overrides
            WHERE reason = ?
              AND account_id IN (SELECT id FROM accounts WHERE user_id = ?)
            """,
            (reason, user_id),
        )
        for account_id, bounds in by_account.items():
            _recalculate_review_items_for_account_month_range(
                conn,
                account_id,
                user_id,
                bounds["from_month"],
                bounds["to_month"],
            )
        conn.commit()
        return cur.rowcount or 0


def fetch_contribution_calendar(user_id, from_month, to_month):
    month_keys = _month_keys_between(from_month, to_month)
    if not month_keys:
        return {"months": [], "accounts": [], "overlap_count": 0}

    with get_connection() as conn:
        accounts = conn.execute(
            """
            SELECT id, name, wrapper_type, category, monthly_contribution, employer_contribution, contribution_method, current_value, valuation_mode
            FROM accounts
            WHERE user_id = ?
              AND is_active = 1
              AND (
                    COALESCE(monthly_contribution, 0) > 0
                 OR LOWER(COALESCE(wrapper_type, '')) LIKE '%isa%'
                 OR LOWER(COALESCE(wrapper_type, '')) LIKE '%lisa%'
                 OR LOWER(COALESCE(wrapper_type, '')) LIKE '%sipp%'
                 OR LOWER(COALESCE(wrapper_type, '')) LIKE '%pension%'
                 OR LOWER(COALESCE(wrapper_type, '')) LIKE '%cash%'
                 OR LOWER(COALESCE(wrapper_type, '')) LIKE '%premium bond%'
                 OR COALESCE(valuation_mode, '') = 'premium_bonds'
                 OR LOWER(COALESCE(category, '')) = 'cash'
              )
            ORDER BY
              CASE
                WHEN LOWER(COALESCE(wrapper_type, '')) LIKE '%cash isa%' THEN 0
                WHEN LOWER(COALESCE(wrapper_type, '')) LIKE '%lifetime isa%' THEN 1
                WHEN LOWER(COALESCE(wrapper_type, '')) LIKE '%isa%' THEN 2
                WHEN LOWER(COALESCE(wrapper_type, '')) LIKE '%sipp%' THEN 3
                WHEN LOWER(COALESCE(wrapper_type, '')) LIKE '%pension%' THEN 4
                ELSE 5
              END,
              name COLLATE NOCASE ASC
            """,
            (user_id,),
        ).fetchall()
        account_ids = [int(row["id"]) for row in accounts]
        overrides_by_account = defaultdict(list)
        if account_ids:
            placeholders = ", ".join("?" for _ in account_ids)
            override_rows = conn.execute(
                f"""
                SELECT co.*, a.name AS account_name
                FROM contribution_overrides co
                JOIN accounts a ON a.id = co.account_id
                WHERE a.user_id = ?
                  AND co.account_id IN ({placeholders})
                  AND co.from_month <= ?
                  AND co.to_month >= ?
                ORDER BY co.account_id ASC, co.id DESC
                """,
                (user_id, *account_ids, to_month, from_month),
            ).fetchall()
            for row in override_rows:
                overrides_by_account[int(row["account_id"])].append(dict(row))

    overlap_count = 0
    calendar_accounts = []
    for account in accounts:
        account_id = int(account["id"])
        default_amount = to_decimal(account["monthly_contribution"])
        month_cells = []
        for month_key in month_keys:
            active_rows = [
                row
                for row in overrides_by_account.get(account_id, [])
                if row["from_month"] <= month_key <= row["to_month"]
            ]
            selected = select_best_matching_override(active_rows, month_key)
            if len(active_rows) > 1:
                overlap_count += 1
            selected_reason = selected["reason"] if selected is not None else ""
            month_cells.append({
                "month_key": month_key,
                "default_amount": default_amount,
                "has_override": selected is not None,
                "override_amount": to_decimal(selected["override_amount"]) if selected is not None else None,
                "reason": selected_reason,
                "plan_name": _plan_name_from_reason(selected_reason) if selected_reason.startswith(TEMPORARY_PLAN_PREFIX) else "",
                "source_label": (
                    "Temporary override"
                    if selected_reason.startswith(TEMPORARY_PLAN_PREFIX)
                    else (selected_reason or "Override")
                ) if selected is not None else "Default",
                "is_temporary": bool(selected_reason.startswith(TEMPORARY_PLAN_PREFIX)),
                "active_override_count": len(active_rows),
                "overlap": len(active_rows) > 1,
                "overlap_reasons": [row["reason"] or "Override" for row in active_rows],
                "overlap_amounts": [to_decimal(row["override_amount"]) for row in active_rows],
            })

        calendar_accounts.append({
            "id": account_id,
            "calendar_entry_key": str(account_id),
            "component": "invested",
            "name": account["name"],
            "base_account_name": account["name"],
            "wrapper_type": account["wrapper_type"],
            "category": account["category"],
            "current_value": to_decimal(account["current_value"]),
            "monthly_contribution": default_amount,
            "employer_contribution": to_decimal(account["employer_contribution"]),
            "contribution_method": account["contribution_method"] or "standard",
            "valuation_mode": account["valuation_mode"] or "manual",
            "months": month_cells,
        })

    return {
        "months": month_keys,
        "accounts": calendar_accounts,
        "overlap_count": overlap_count,
    }


def _month_key_to_index(month_key):
    try:
        year, month = str(month_key).split("-")
        return int(year) * 12 + int(month)
    except (AttributeError, TypeError, ValueError):
        return None


def _override_span_months(row):
    start = _month_key_to_index(row["from_month"])
    end = _month_key_to_index(row["to_month"])
    if start is None or end is None:
        return None
    return max(end - start, 0)


def _month_keys_between(from_month, to_month):
    start = _month_key_to_index(from_month)
    end = _month_key_to_index(to_month)
    if start is None or end is None or start > end:
        return []
    return [add_months_to_key(from_month, idx) for idx in range(end - start + 1)]


def _effective_override_amount_for_month(conn, account_id, month_key, fallback_amount):
    rows = conn.execute(
        """
        SELECT *
        FROM contribution_overrides
        WHERE account_id = ?
          AND from_month <= ?
          AND to_month >= ?
        ORDER BY id DESC
        """,
        (account_id, month_key, month_key),
    ).fetchall()
    selected = select_best_matching_override(rows, month_key)
    if selected is not None:
        return to_decimal(selected["override_amount"])
    return to_decimal(fallback_amount)


def _recalculate_review_items_for_account_month_range(conn, account_id, user_id, from_month, to_month):
    account = conn.execute(
        "SELECT monthly_contribution FROM accounts WHERE id = ? AND user_id = ?",
        (account_id, user_id),
    ).fetchone()
    if not account:
        return

    review_rows = conn.execute(
        """
        SELECT mr.id, mr.month_key
        FROM monthly_reviews mr
        JOIN monthly_review_items mri ON mri.review_id = mr.id
        WHERE mr.user_id = ?
          AND mri.account_id = ?
          AND mr.month_key >= ?
          AND mr.month_key <= ?
        """,
        (user_id, account_id, from_month, to_month),
    ).fetchall()
    fallback_amount = to_decimal(account["monthly_contribution"])
    for review in review_rows:
        expected = _effective_override_amount_for_month(
            conn,
            account_id,
            review["month_key"],
            fallback_amount,
        )
        conn.execute(
            """
            UPDATE monthly_review_items
            SET expected_contribution = ?
            WHERE review_id = ? AND account_id = ?
            """,
            (expected, review["id"], account_id),
        )


def _delete_overrides_for_reason(conn, account_id, user_id, reason):
    if not _account_belongs_to_user(conn, account_id, user_id):
        return 0
    rows = conn.execute(
        """
        SELECT from_month, to_month
        FROM contribution_overrides
        WHERE account_id = ? AND reason = ?
        ORDER BY from_month ASC, id ASC
        """,
        (account_id, reason),
    ).fetchall()
    if not rows:
        return 0
    cur = conn.execute(
        "DELETE FROM contribution_overrides WHERE account_id = ? AND reason = ?",
        (account_id, reason),
    )
    from_month = min(row["from_month"] for row in rows)
    to_month = max(row["to_month"] for row in rows)
    _recalculate_review_items_for_account_month_range(conn, account_id, user_id, from_month, to_month)
    return cur.rowcount or 0


def fetch_all_active_overrides(month_key, user_id):
    """Return overrides active for a given month, keyed by account_id.

    When multiple overrides overlap for the same account/month, prefer the
    narrowest matching span. For ties, prefer the newest record.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT co.* FROM contribution_overrides co
            JOIN accounts a ON a.id = co.account_id
            WHERE co.from_month <= ? AND co.to_month >= ? AND a.user_id = ?
            ORDER BY co.account_id ASC, co.id DESC
            """,
            (month_key, month_key, user_id),
        ).fetchall()

    rows_by_account = {}
    for row in rows:
        rows_by_account.setdefault(row["account_id"], []).append(row)

    aggregated = {}
    for account_id, account_rows in rows_by_account.items():
        selected = select_best_matching_override(account_rows, month_key)
        if selected is not None:
            aggregated[account_id] = {
                **dict(selected),
                "override_amount": to_decimal(selected["override_amount"]),
                "component": "total",
            }
    return aggregated


def fetch_isa_overrides_for_tax_year(user_id, ty_start, ty_end):
    """Return all contribution overrides that overlap the tax year, for ISA accounts only.

    Returns list of rows with account_id, from_month, to_month, override_amount.
    """
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT co.account_id, co.from_month, co.to_month, SUM(co.override_amount) AS override_amount
            FROM contribution_overrides co
            JOIN accounts a ON a.id = co.account_id
            WHERE a.user_id = ?
              AND co.from_month <= ?
              AND co.to_month >= ?
              AND a.wrapper_type IN (
                  'Stocks & Shares ISA', 'Cash ISA', 'Lifetime ISA',
                  'Stocks and Shares ISA'
              )
            GROUP BY co.account_id, co.from_month, co.to_month
            ORDER BY co.account_id, co.from_month
            """,
            (user_id, ty_end[:7], ty_start[:7]),
        ).fetchall()


def fetch_isa_allowance_cash_flow_events(user_id, ty_start, ty_end):
    """Return ISA cash-flow events explicitly marked to affect tracked allowance usage."""
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT c.*, a.name AS account_name, a.wrapper_type
            FROM cash_flow_events c
            JOIN accounts a ON a.id = c.account_id
            WHERE c.user_id = ?
              AND a.user_id = c.user_id
              AND c.event_date >= ?
              AND c.event_date <= ?
              AND a.wrapper_type IN (
                  'Stocks & Shares ISA', 'Cash ISA', 'Lifetime ISA',
                  'Stocks and Shares ISA'
              )
              AND c.allowance_effect IN (
                  'subscription', 'flexible_withdrawal', 'flexible_replacement'
              )
            ORDER BY c.event_date DESC, c.id DESC
            """,
            (user_id, ty_start, ty_end),
        ).fetchall()


def fetch_pension_overrides_for_tax_year(user_id, ty_start, ty_end):
    """Return all contribution overrides that overlap the tax year, for pension accounts only.

    Returns list of rows with account_id, from_month, to_month, override_amount.
    """
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT co.account_id, co.from_month, co.to_month, SUM(co.override_amount) AS override_amount
            FROM contribution_overrides co
            JOIN accounts a ON a.id = co.account_id
            WHERE a.user_id = ?
              AND co.from_month <= ?
              AND co.to_month >= ?
              AND (
                    LOWER(COALESCE(a.category, '')) = 'pension'
                 OR LOWER(COALESCE(a.wrapper_type, '')) LIKE '%pension%'
                 OR LOWER(COALESCE(a.wrapper_type, '')) LIKE '%sipp%'
              )
            GROUP BY co.account_id, co.from_month, co.to_month
            ORDER BY co.account_id, co.from_month
            """,
            (user_id, ty_end[:7], ty_start[:7]),
        ).fetchall()


def create_contribution_override(payload, user_id=None):
    with get_connection() as conn:
        if user_id is not None and not _account_belongs_to_user(conn, payload["account_id"], user_id):
            return None
        component = str(payload.get("component") or "total").strip().lower()
        if component not in {"total", "invested", "cash_park"}:
            component = "total"
        cursor = conn.execute(
            """
            INSERT INTO contribution_overrides (account_id, from_month, to_month, override_amount, component, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["account_id"],
                payload["from_month"],
                payload["to_month"],
                payload["override_amount"],
                component,
                payload.get("reason", ""),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        if user_id is not None:
            _recalculate_review_items_for_account_month_range(
                conn,
                payload["account_id"],
                user_id,
                payload["from_month"],
                payload["to_month"],
            )
        conn.commit()
        return cursor.lastrowid


def remove_contribution_override_for_month(account_id, month_key, user_id):
    """Delete a single-month skip override (from_month == to_month == month_key)."""
    with get_connection() as conn:
        if not _account_belongs_to_user(conn, account_id, user_id):
            return
        conn.execute(
            """DELETE FROM contribution_overrides
               WHERE account_id = ? AND from_month = ? AND to_month = ?
               AND account_id IN (SELECT id FROM accounts WHERE user_id = ?)""",
            (account_id, month_key, month_key, user_id),
        )
        _recalculate_review_items_for_account_month_range(
            conn,
            account_id,
            user_id,
            month_key,
            month_key,
        )
        conn.commit()


def upsert_single_month_contribution_override(account_id, month_key, amount, user_id, reason="from budget"):
    """Upsert a single-month contribution override for an account.

    Replaces any existing single-month override (from_month == to_month == month_key)
    for this account. Used by the budget page to reflect per-month edits on linked
    items straight through to projections without creating duplicates.

    Verifies the account belongs to user_id — silently no-ops if not.
    """
    with get_connection() as conn:
        owned = conn.execute(
            "SELECT 1 FROM accounts WHERE id = ? AND user_id = ?",
            (account_id, user_id),
        ).fetchone()
        if not owned:
            return
        conn.execute(
            """DELETE FROM contribution_overrides
               WHERE account_id = ? AND from_month = ? AND to_month = ?""",
            (account_id, month_key, month_key),
        )
        conn.execute(
            """INSERT INTO contribution_overrides
               (account_id, from_month, to_month, override_amount, component, reason, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
             (account_id, month_key, month_key, amount, "total", reason, datetime.now(timezone.utc).isoformat()),
        )
        _recalculate_review_items_for_account_month_range(
            conn,
            account_id,
            user_id,
            month_key,
            month_key,
        )
        conn.commit()


def delete_single_month_contribution_override(account_id, month_key, user_id):
    """Delete a single-month contribution override (e.g. when an input is cleared)."""
    with get_connection() as conn:
        owned = conn.execute(
            "SELECT 1 FROM accounts WHERE id = ? AND user_id = ?",
            (account_id, user_id),
        ).fetchone()
        if not owned:
            return
        conn.execute(
            """DELETE FROM contribution_overrides
               WHERE account_id = ? AND from_month = ? AND to_month = ?""",
            (account_id, month_key, month_key),
        )
        _recalculate_review_items_for_account_month_range(
            conn,
            account_id,
            user_id,
            month_key,
            month_key,
        )
        conn.commit()


def delete_contribution_override(override_id, user_id=None):
    with get_connection() as conn:
        if user_id is not None:
            row = conn.execute(
                """
                SELECT co.account_id, co.from_month, co.to_month
                FROM contribution_overrides co
                JOIN accounts a ON a.id = co.account_id
                WHERE co.id = ? AND a.user_id = ?
                """,
                (override_id, user_id),
            ).fetchone()
            conn.execute(
                """DELETE FROM contribution_overrides
                   WHERE id = ? AND account_id IN (SELECT id FROM accounts WHERE user_id = ?)""",
                (override_id, user_id),
            )
            if row:
                _recalculate_review_items_for_account_month_range(
                    conn,
                    row["account_id"],
                    user_id,
                    row["from_month"],
                    row["to_month"],
                )
        else:
            conn.execute("DELETE FROM contribution_overrides WHERE id = ?", (override_id,))
        conn.commit()


# ── Cash flow events (transfers/withdrawals) ──────────────────────────────────

def add_cash_flow_event(payload, user_id):
    """Insert a cash flow event for an account.

    payload:
      account_id (int)
      event_date (YYYY-MM-DD)
      amount (signed float, + deposit, - withdrawal/transfer out)
      kind (text)
      counterparty_account_id (optional int)
      note (optional text)
    """
    account_id = int(payload["account_id"])
    with get_connection() as conn:
        if not _account_belongs_to_user(conn, account_id, user_id):
            return None
        counterparty = payload.get("counterparty_account_id")
        if counterparty:
            try:
                counterparty = int(counterparty)
            except (TypeError, ValueError):
                counterparty = None
        if counterparty and not _account_belongs_to_user(conn, counterparty, user_id):
            counterparty = None
        cursor = conn.execute(
            """
            INSERT INTO cash_flow_events
              (user_id, account_id, event_date, amount, kind, counterparty_account_id, note, allowance_effect, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                account_id,
                payload["event_date"],
                to_decimal(payload["amount"]),
                payload.get("kind") or "transfer",
                counterparty,
                payload.get("note") or "",
                payload.get("allowance_effect") or "none",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        return cursor.lastrowid


def add_account_transfer_events(payload, user_id):
    from_account_id = int(payload.get("from_account_id") or 0)
    to_account_id = int(payload.get("to_account_id") or 0)
    if from_account_id == to_account_id:
        return None
    amount = abs(to_decimal(payload.get("amount")))
    if amount <= 0:
        return None
    event_date = payload.get("event_date")
    note = payload.get("note") or "Account transfer"
    created_at = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        if not _account_belongs_to_user(conn, from_account_id, user_id):
            return None
        if not _account_belongs_to_user(conn, to_account_id, user_id):
            return None
        from_cursor = conn.execute(
            """
            INSERT INTO cash_flow_events
              (user_id, account_id, event_date, amount, kind, counterparty_account_id, note, allowance_effect, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                from_account_id,
                event_date,
                -amount,
                "transfer_out",
                to_account_id,
                note,
                "transfer_neutral",
                created_at,
            ),
        )
        to_cursor = conn.execute(
            """
            INSERT INTO cash_flow_events
              (user_id, account_id, event_date, amount, kind, counterparty_account_id, note, allowance_effect, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                to_account_id,
                event_date,
                amount,
                "transfer_in",
                from_account_id,
                note,
                "transfer_neutral",
                created_at,
            ),
        )
        conn.commit()
        return {"from_event_id": from_cursor.lastrowid, "to_event_id": to_cursor.lastrowid}


def fetch_cash_flow_events_for_account(account_id, user_id, from_date=None, to_date=None, limit=200):
    with get_connection() as conn:
        if not _account_belongs_to_user(conn, account_id, user_id):
            return []
        params = [user_id, account_id]
        where = "WHERE user_id = ? AND account_id = ?"
        if from_date:
            where += " AND event_date >= ?"
            params.append(from_date)
        if to_date:
            where += " AND event_date <= ?"
            params.append(to_date)
        params.append(int(limit))
        return conn.execute(
            f"""
            SELECT * FROM cash_flow_events
            {where}
            ORDER BY event_date DESC, id DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()


def delete_cash_flow_event(event_id, user_id, allowance_effect=None):
    with get_connection() as conn:
        params = [event_id, user_id]
        where = "id = ? AND user_id = ?"
        if allowance_effect is not None:
            where += " AND allowance_effect = ?"
            params.append(allowance_effect)
        cursor = conn.execute(
            f"DELETE FROM cash_flow_events WHERE {where}",
            tuple(params),
        )
        conn.commit()
        return cursor.rowcount
