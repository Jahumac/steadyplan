"""Portfolio snapshots: monthly, daily, and performance history."""
from datetime import datetime
from ._conn import get_connection
from app.calculations import effective_monthly_contribution, select_best_matching_override


# ── Monthly snapshots ─────────────────────────────────────────────────────────

def upsert_monthly_snapshot(account_id, month_key, balance):
    """Write or overwrite a snapshot for one account for a given month."""
    snapshot_date = month_key + "-01"
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM monthly_snapshots WHERE account_id = ? AND month_key = ?",
            (account_id, month_key),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE monthly_snapshots SET balance = ?, snapshot_date = ? WHERE id = ?",
                (balance, snapshot_date, existing["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key)
                VALUES (?, ?, ?, ?)
                """,
                (snapshot_date, account_id, balance, month_key),
            )
        conn.commit()


def fetch_net_worth_history(user_id, limit=24):
    """Return (month_key, total_balance) pairs for the last `limit` months."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT ms.month_key, SUM(ms.balance) AS total
            FROM monthly_snapshots ms
            JOIN accounts a ON a.id = ms.account_id
            WHERE ms.month_key IS NOT NULL AND a.user_id = ?
            GROUP BY ms.month_key
            ORDER BY ms.month_key ASC
            """,
            (user_id,),
        ).fetchall()
    return [(r["month_key"], r["total"]) for r in rows[-limit:]]


def fetch_account_snapshot_history(account_id, limit=24):
    """Return (month_key, balance) pairs for one account."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT month_key, balance
            FROM monthly_snapshots
            WHERE account_id = ?
              AND month_key IS NOT NULL
            ORDER BY month_key ASC
            """,
            (account_id,),
        ).fetchall()
    return [(r["month_key"], r["balance"]) for r in rows[-limit:]]


def fetch_monthly_performance_data(user_id):
    """Return monthly performance rows ordered by month.

    For each account, use that month's snapshot when present; otherwise carry
    forward the last known snapshot before that month. This prevents a partial
    month (for example, updating only a new Cash ISA) from making every other
    account look like it fell to zero.
    """
    with get_connection() as conn:
        months = conn.execute(
            """
            SELECT DISTINCT ms.month_key
            FROM monthly_snapshots ms
            JOIN accounts a ON a.id = ms.account_id
            WHERE ms.month_key IS NOT NULL
              AND a.user_id = ?
              AND a.is_active = 1
            ORDER BY ms.month_key ASC
            """,
            (user_id,),
        ).fetchall()
        accounts = conn.execute(
            "SELECT * FROM accounts WHERE user_id = ? AND is_active = 1 ORDER BY id ASC",
            (user_id,),
        ).fetchall()
        assumptions_row = conn.execute(
            "SELECT * FROM assumptions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        assumptions = dict(assumptions_row) if assumptions_row else {}

        overrides = conn.execute(
            """
            SELECT co.*
            FROM contribution_overrides co
            JOIN accounts a ON a.id = co.account_id
            WHERE a.user_id = ?
            ORDER BY co.account_id ASC, co.id DESC
            """,
            (user_id,),
        ).fetchall()
        overrides_by_account = {}
        for ov in overrides:
            overrides_by_account.setdefault(int(ov["account_id"]), []).append(ov)

        review_map = {}
        cash_flow_map = {}
        if months:
            min_mk = months[0]["month_key"]
            max_mk = months[-1]["month_key"]
            review_rows = conn.execute(
                """
                SELECT mr.month_key, mri.account_id, mri.expected_contribution
                FROM monthly_reviews mr
                JOIN monthly_review_items mri ON mri.review_id = mr.id
                WHERE mr.user_id = ?
                  AND mr.status = 'complete'
                  AND mri.contribution_confirmed = 1
                  AND mr.month_key >= ?
                  AND mr.month_key <= ?
                """,
                (user_id, min_mk, max_mk),
            ).fetchall()
            for rr in review_rows:
                review_map[(int(rr["account_id"]), rr["month_key"])] = float(rr["expected_contribution"] or 0)

            cash_flow_rows = conn.execute(
                """
                SELECT c.account_id, substr(c.event_date, 1, 7) AS month_key,
                       c.amount, c.kind, c.counterparty_account_id
                FROM cash_flow_events c
                JOIN accounts a ON a.id = c.account_id
                WHERE c.user_id = ?
                  AND a.user_id = c.user_id
                  AND a.is_active = 1
                  AND substr(c.event_date, 1, 7) >= ?
                  AND substr(c.event_date, 1, 7) <= ?
                """,
                (user_id, min_mk, max_mk),
            ).fetchall()
            for cr in cash_flow_rows:
                key = (int(cr["account_id"]), cr["month_key"])
                amount = float(cr["amount"] or 0)
                cash_flow_map[key] = cash_flow_map.get(key, 0.0) + amount
        rows = []
        for month in months:
            month_key = month["month_key"]
            total_balance = 0.0
            carried_forward = 0
            accounts_with_value = 0
            valued_account_ids = set()
            first_value_by_account = {}
            first_balance_by_account = {}

            for account in accounts:
                snap = conn.execute(
                    """
                    SELECT balance, month_key
                    FROM monthly_snapshots
                    WHERE account_id = ?
                      AND month_key <= ?
                    ORDER BY month_key DESC
                    LIMIT 1
                    """,
                    (account["id"], month_key),
                ).fetchone()
                if not snap:
                    continue
                aid = int(account["id"])
                valued_account_ids.add(aid)
                accounts_with_value += 1
                total_balance += float(snap["balance"] or 0)
                first_value_by_account[aid] = False
                first_balance_by_account[aid] = float(snap["balance"] or 0)
                if snap["month_key"] != month_key:
                    carried_forward += 1
                else:
                    prior_snap = conn.execute(
                        """
                        SELECT 1
                        FROM monthly_snapshots
                        WHERE account_id = ?
                          AND month_key < ?
                        LIMIT 1
                        """,
                        (account["id"], month_key),
                    ).fetchone()
                    first_value_by_account[aid] = prior_snap is None

            if accounts_with_value == 0:
                continue

            total_contribution = 0.0
            for account in accounts:
                aid = int(account["id"])
                if aid not in valued_account_ids:
                    continue

                cash_flow_key = (aid, month_key)
                has_cash_flow = cash_flow_key in cash_flow_map
                if first_value_by_account.get(aid) and month_key != months[0]["month_key"]:
                    total_contribution += (
                        float(cash_flow_map.get(cash_flow_key, 0.0) or 0.0)
                        if has_cash_flow
                        else float(first_balance_by_account.get(aid, 0.0) or 0.0)
                    )
                    continue

                default_personal = float(account.get("monthly_contribution") or 0)

                override = select_best_matching_override(overrides_by_account.get(aid, []), month_key)
                personal = float(override["override_amount"] or 0) if override is not None else None

                planned_contribution = 0.0
                if personal != 0.0:
                    rkey = (aid, month_key)
                    if rkey in review_map:
                        personal = float(review_map[rkey] or 0)

                    if personal is None:
                        personal = default_personal

                    if personal > 0:
                        adjusted = dict(account)
                        adjusted["monthly_contribution"] = personal
                        planned_contribution = float(effective_monthly_contribution(adjusted, assumptions) or 0)

                total_contribution += planned_contribution + float(cash_flow_map.get(cash_flow_key, 0.0) or 0.0)
            rows.append({
                "month_key": month_key,
                "total_balance": total_balance,
                "total_contribution": total_contribution,
                "carried_forward_count": carried_forward,
            })
    return [
        (r["month_key"], r["total_balance"], r["total_contribution"], r["carried_forward_count"])
        for r in rows
    ]

def fetch_monthly_performance_data_by_account(user_id):
    """Return per-account monthly performance data keyed by account_id."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                a.id AS account_id,
                a.name AS account_name,
                a.monthly_contribution,
                a.wrapper_type,
                a.category,
                a.employer_contribution,
                a.contribution_method,
                a.contribution_fee_pct,
                a.pre_salary,
                ms.month_key,
                ms.balance AS balance
            FROM monthly_snapshots ms
            JOIN accounts a ON a.id = ms.account_id
            WHERE ms.month_key IS NOT NULL
              AND a.user_id = ?
              AND a.is_active = 1
            ORDER BY a.name ASC, ms.month_key ASC
            """,
            (user_id,),
        ).fetchall()

        assumptions_row = conn.execute(
            "SELECT * FROM assumptions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        assumptions = dict(assumptions_row) if assumptions_row else {}

        overrides = conn.execute(
            """
            SELECT co.*
            FROM contribution_overrides co
            JOIN accounts a ON a.id = co.account_id
            WHERE a.user_id = ?
            ORDER BY co.account_id ASC, co.id DESC
            """,
            (user_id,),
        ).fetchall()
        overrides_by_account = {}
        for ov in overrides:
            overrides_by_account.setdefault(int(ov["account_id"]), []).append(ov)

        review_rows = conn.execute(
            """
            SELECT mr.month_key, mri.account_id, mri.expected_contribution
            FROM monthly_reviews mr
            JOIN monthly_review_items mri ON mri.review_id = mr.id
            WHERE mr.user_id = ?
              AND mr.status = 'complete'
              AND mri.contribution_confirmed = 1
            """,
            (user_id,),
        ).fetchall()
        review_map = {}
        for rr in review_rows:
            review_map[(int(rr["account_id"]), rr["month_key"])] = float(rr["expected_contribution"] or 0)

        cash_flow_rows = conn.execute(
            """
            SELECT c.account_id, substr(c.event_date, 1, 7) AS month_key, SUM(c.amount) AS amount
            FROM cash_flow_events c
            JOIN accounts a ON a.id = c.account_id
            WHERE c.user_id = ?
              AND a.user_id = c.user_id
              AND a.is_active = 1
            GROUP BY c.account_id, substr(c.event_date, 1, 7)
            """,
            (user_id,),
        ).fetchall()
        cash_flow_map = {}
        for cr in cash_flow_rows:
            cash_flow_map[(int(cr["account_id"]), cr["month_key"])] = float(cr["amount"] or 0)

    out = {}
    seen_account_ids = set()
    for r in rows:
        aid = int(r["account_id"])
        if aid not in out:
            out[aid] = {"account_name": r["account_name"], "rows": []}

        month_key = r["month_key"]
        cash_flow_key = (aid, month_key)
        has_cash_flow = cash_flow_key in cash_flow_map
        cash_flow_total = float(cash_flow_map.get(cash_flow_key, 0.0) or 0.0)
        is_first_account_snapshot = aid not in seen_account_ids
        seen_account_ids.add(aid)
        default_personal = float(r.get("monthly_contribution") or 0)
        override = select_best_matching_override(overrides_by_account.get(aid, []), month_key)
        personal = float(override["override_amount"] or 0) if override is not None else None
        planned_contrib = 0.0
        if personal != 0.0:
            rk = (aid, month_key)
            if rk in review_map:
                personal = float(review_map[rk] or 0)
            if personal is None:
                personal = default_personal
            if personal > 0:
                adjusted = dict(r)
                adjusted["monthly_contribution"] = personal
                planned_contrib = float(effective_monthly_contribution(adjusted, assumptions) or 0)
        contrib = planned_contrib + (0.0 if is_first_account_snapshot else cash_flow_total)

        out[aid]["rows"].append((month_key, float(r["balance"] or 0), float(contrib or 0)))
    return out


# ── Daily snapshots ───────────────────────────────────────────────────────────

def save_daily_snapshot(user_id, total_value, snapshot_date=None):
    """Save or update a portfolio snapshot for a given user and date."""
    if snapshot_date is None:
        snapshot_date = datetime.now().strftime("%Y-%m-%d")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO portfolio_daily_snapshots (user_id, snapshot_date, total_value, created_at)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (user_id, snapshot_date, total_value),
        )
        conn.commit()


def fetch_daily_snapshots(user_id, limit=365):
    """Return (snapshot_date, total_value) tuples ordered ASC, last N days."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT snapshot_date, total_value FROM (
                SELECT snapshot_date, total_value FROM portfolio_daily_snapshots
                WHERE user_id = ?
                ORDER BY snapshot_date DESC
                LIMIT ?
            )
            ORDER BY snapshot_date ASC
            """,
            (user_id, limit),
        ).fetchall()
    return [(r["snapshot_date"], float(r["total_value"])) for r in rows]


def save_account_daily_snapshots(user_id, account_values, snapshot_date=None):
    """Save per-account daily snapshots.

    account_values: list of (account_id, value) tuples.
    """
    if snapshot_date is None:
        snapshot_date = datetime.now().strftime("%Y-%m-%d")

    with get_connection() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO account_daily_snapshots (user_id, account_id, snapshot_date, value)
            VALUES (?, ?, ?, ?)
            """,
            [(user_id, acct_id, snapshot_date, value) for acct_id, value in account_values],
        )
        conn.commit()


def fetch_account_daily_snapshots(account_id, limit=365):
    """Return (snapshot_date, value) pairs for one account, ordered ASC, last N days."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT snapshot_date, value FROM account_daily_snapshots
            WHERE account_id = ?
            ORDER BY snapshot_date DESC
            LIMIT ?
            """,
            (account_id, limit),
        ).fetchall()
    return [(r["snapshot_date"], float(r["value"])) for r in reversed(rows)]


def fetch_account_daily_snapshot_values_for_date(user_id, snapshot_date):
    """Return {account_id: value} for a user's per-account snapshots on one date."""
    if not snapshot_date:
        return {}
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT account_id, value
            FROM account_daily_snapshots
            WHERE user_id = ? AND snapshot_date = ?
            """,
            (user_id, snapshot_date),
        ).fetchall()
    return {int(r["account_id"]): float(r["value"] or 0) for r in rows}


def fetch_account_daily_snapshot_points_on_or_before_date(user_id, snapshot_date):
    """Return {account_id: {snapshot_date, value}} for latest snapshots on/before date."""
    if not snapshot_date:
        return {}
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT account_id, snapshot_date, value
            FROM account_daily_snapshots
            WHERE user_id = ? AND snapshot_date <= ?
            ORDER BY account_id ASC, snapshot_date DESC
            """,
            (user_id, snapshot_date),
        ).fetchall()
    out = {}
    for r in rows:
        aid = int(r["account_id"])
        if aid in out:
            continue
        out[aid] = {"snapshot_date": r["snapshot_date"], "value": float(r["value"] or 0)}
    return out


def fetch_account_daily_snapshot_points_on_or_after_date(user_id, snapshot_date):
    """Return {account_id: {snapshot_date, value}} for earliest snapshots on/after date."""
    if not snapshot_date:
        return {}
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT account_id, snapshot_date, value
            FROM account_daily_snapshots
            WHERE user_id = ? AND snapshot_date >= ?
            ORDER BY account_id ASC, snapshot_date ASC
            """,
            (user_id, snapshot_date),
        ).fetchall()
    out = {}
    for r in rows:
        aid = int(r["account_id"])
        if aid in out:
            continue
        out[aid] = {"snapshot_date": r["snapshot_date"], "value": float(r["value"] or 0)}
    return out
