import json

from app.models import get_connection
from app.services.restore_validation import validate_restore_backup_json


class RestoreError(Exception):
    pass


class RestoreValidationError(RestoreError):
    def __init__(self, validation_result):
        super().__init__("Backup failed validation.")
        self.validation_result = validation_result


def _table_columns(conn, table_name):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _delete_user_data(conn, user_id):
    out = {}

    def _del(sql, params):
        cur = conn.execute(sql, params)
        rc = cur.rowcount
        return int(rc) if isinstance(rc, int) and rc >= 0 else 0

    out["budget_entries"] = _del(
        "DELETE FROM budget_entries WHERE budget_item_id IN (SELECT id FROM budget_items WHERE user_id = ?)",
        (user_id,),
    )
    out["budget_items"] = _del("DELETE FROM budget_items WHERE user_id = ?", (user_id,))
    out["budget_sections"] = _del("DELETE FROM budget_sections WHERE user_id = ?", (user_id,))

    out["monthly_review_items"] = _del(
        "DELETE FROM monthly_review_items WHERE review_id IN (SELECT id FROM monthly_reviews WHERE user_id = ?)",
        (user_id,),
    )
    out["monthly_reviews"] = _del("DELETE FROM monthly_reviews WHERE user_id = ?", (user_id,))

    out["portfolio_daily_snapshots"] = _del("DELETE FROM portfolio_daily_snapshots WHERE user_id = ?", (user_id,))
    out["account_daily_snapshots"] = _del("DELETE FROM account_daily_snapshots WHERE user_id = ?", (user_id,))

    out["cash_flow_events"] = _del("DELETE FROM cash_flow_events WHERE user_id = ?", (user_id,))
    out["isa_contributions"] = _del("DELETE FROM isa_contributions WHERE user_id = ?", (user_id,))
    out["pension_contributions"] = _del("DELETE FROM pension_contributions WHERE user_id = ?", (user_id,))
    out["dividend_records"] = _del("DELETE FROM dividend_records WHERE user_id = ?", (user_id,))
    out["cgt_disposals"] = _del("DELETE FROM cgt_disposals WHERE user_id = ?", (user_id,))
    out["pension_carry_forward"] = _del("DELETE FROM pension_carry_forward WHERE user_id = ?", (user_id,))
    out["allowance_tracking"] = _del("DELETE FROM allowance_tracking WHERE user_id = ?", (user_id,))

    out["premium_bonds_prizes"] = _del("DELETE FROM premium_bonds_prizes WHERE user_id = ?", (user_id,))

    out["contribution_overrides"] = _del(
        "DELETE FROM contribution_overrides WHERE account_id IN (SELECT id FROM accounts WHERE user_id = ?)",
        (user_id,),
    )
    out["monthly_snapshots"] = _del(
        "DELETE FROM monthly_snapshots WHERE account_id IN (SELECT id FROM accounts WHERE user_id = ?)",
        (user_id,),
    )
    out["holdings"] = _del(
        "DELETE FROM holdings WHERE account_id IN (SELECT id FROM accounts WHERE user_id = ?)",
        (user_id,),
    )

    out["accounts"] = _del("DELETE FROM accounts WHERE user_id = ?", (user_id,))
    out["goals"] = _del("DELETE FROM goals WHERE user_id = ?", (user_id,))
    out["debts"] = _del("DELETE FROM debts WHERE user_id = ?", (user_id,))
    out["assumptions"] = _del("DELETE FROM assumptions WHERE user_id = ?", (user_id,))
    out["holding_catalogue"] = _del("DELETE FROM holding_catalogue WHERE user_id = ?", (user_id,))

    return out


def _insert_row(conn, table_name, row, *, overrides=None, ignore_columns=None, remap=None):
    ignore_columns = set(ignore_columns or [])
    overrides = dict(overrides or {})
    remap = dict(remap or {})

    cols = _table_columns(conn, table_name)
    data = {}
    if isinstance(row, dict):
        for k, v in row.items():
            if k in cols and k not in ignore_columns:
                data[k] = v
    for k, v in overrides.items():
        if k in cols and k not in ignore_columns:
            data[k] = v
    for field, mapping in remap.items():
        if field not in cols:
            continue
        if field not in data:
            continue
        if data[field] is None:
            continue
        old_val = data[field]
        if old_val not in mapping:
            raise RestoreError(f"Cannot remap {table_name}.{field}: missing mapping for id {old_val}.")
        data[field] = mapping[old_val]

    if not data:
        cur = conn.execute(f"INSERT INTO {table_name} DEFAULT VALUES")
        return cur.lastrowid

    keys = list(data.keys())
    placeholders = ", ".join(["?"] * len(keys))
    sql = f"INSERT INTO {table_name} ({', '.join(keys)}) VALUES ({placeholders})"
    cur = conn.execute(sql, tuple(data[k] for k in keys))
    return cur.lastrowid


def restore_backup_for_user(user_id, backup_payload, *, conn=None):
    if not isinstance(user_id, int) or user_id <= 0:
        raise RestoreError("user_id must be a positive integer.")
    if not isinstance(backup_payload, dict):
        raise RestoreError("backup_payload must be a dict.")

    validation = validate_restore_backup_json(json.dumps(backup_payload, ensure_ascii=False).encode("utf-8"))
    if not validation.get("valid"):
        raise RestoreValidationError(validation)

    meta = backup_payload.get("meta") or {}
    assumptions = backup_payload.get("assumptions") or {}

    accounts = backup_payload.get("accounts") or []
    holdings = backup_payload.get("holdings") or []
    holding_catalogue = backup_payload.get("holding_catalogue") or []
    goals = backup_payload.get("goals") or []
    debts = backup_payload.get("debts") or []

    budget = backup_payload.get("budget") or {}
    budget_sections = budget.get("sections") or []
    budget_items = budget.get("items") or []
    budget_entries = budget.get("entries") or []

    history = backup_payload.get("history") or {}
    monthly_snapshots = history.get("monthly_snapshots") or []
    portfolio_daily_snapshots = history.get("portfolio_daily_snapshots") or []
    account_daily_snapshots = history.get("account_daily_snapshots") or []
    monthly_reviews = history.get("monthly_reviews") or []
    monthly_review_items = history.get("monthly_review_items") or []

    planning = backup_payload.get("planning") or {}
    contribution_overrides = planning.get("contribution_overrides") or []
    cash_flow_events = planning.get("cash_flow_events") or []
    isa_contributions = planning.get("isa_contributions") or []
    pension_contributions = planning.get("pension_contributions") or []
    dividend_records = planning.get("dividend_records") or []
    cgt_disposals = planning.get("cgt_disposals") or []
    pension_carry_forward = planning.get("pension_carry_forward") or []
    allowance_tracking = planning.get("allowance_tracking") or []
    premium_bonds_prizes = planning.get("premium_bonds_prizes") or []

    if conn is None:
        conn_cm = get_connection()
        conn = conn_cm.__enter__()
        owns_conn = True
    else:
        conn_cm = None
        owns_conn = False

    try:
        deleted = {}
        inserted = {}
        id_maps = {
            "accounts": {},
            "holding_catalogue": {},
            "debts": {},
            "budget_items": {},
            "monthly_reviews": {},
        }
        try:
            conn.execute("BEGIN")

            deleted = _delete_user_data(conn, user_id)

            _insert_row(
                conn,
                "assumptions",
                assumptions,
                overrides={"user_id": user_id},
                ignore_columns={"id"},
            )
            inserted["assumptions"] = 1

            for a in accounts:
                old_id = a.get("id")
                new_id = _insert_row(
                    conn,
                    "accounts",
                    a,
                    overrides={"user_id": user_id},
                    ignore_columns={"id"},
                )
                id_maps["accounts"][old_id] = new_id
            inserted["accounts"] = len(accounts)

            for c in holding_catalogue:
                old_id = c.get("id")
                new_id = _insert_row(
                    conn,
                    "holding_catalogue",
                    c,
                    overrides={"user_id": user_id},
                    ignore_columns={"id"},
                )
                id_maps["holding_catalogue"][old_id] = new_id
            inserted["holding_catalogue"] = len(holding_catalogue)

            for g in goals:
                _insert_row(
                    conn,
                    "goals",
                    g,
                    overrides={"user_id": user_id},
                    ignore_columns={"id"},
                )
            inserted["goals"] = len(goals)

            for d in debts:
                old_id = d.get("id")
                new_id = _insert_row(
                    conn,
                    "debts",
                    d,
                    overrides={"user_id": user_id},
                    ignore_columns={"id"},
                )
                id_maps["debts"][old_id] = new_id
            inserted["debts"] = len(debts)

            for bs in budget_sections:
                _insert_row(
                    conn,
                    "budget_sections",
                    bs,
                    overrides={"user_id": user_id},
                    ignore_columns={"id"},
                )
            inserted["budget_sections"] = len(budget_sections)

            for bi in budget_items:
                old_id = bi.get("id")
                new_id = _insert_row(
                    conn,
                    "budget_items",
                    bi,
                    overrides={"user_id": user_id},
                    ignore_columns={"id"},
                    remap={
                        "linked_account_id": id_maps["accounts"],
                        "linked_debt_id": id_maps["debts"],
                    },
                )
                id_maps["budget_items"][old_id] = new_id
            inserted["budget_items"] = len(budget_items)

            for be in budget_entries:
                _insert_row(
                    conn,
                    "budget_entries",
                    be,
                    ignore_columns={"id"},
                    remap={"budget_item_id": id_maps["budget_items"]},
                )
            inserted["budget_entries"] = len(budget_entries)

            for mr in monthly_reviews:
                old_id = mr.get("id")
                new_id = _insert_row(
                    conn,
                    "monthly_reviews",
                    mr,
                    overrides={"user_id": user_id},
                    ignore_columns={"id"},
                )
                id_maps["monthly_reviews"][old_id] = new_id
            inserted["monthly_reviews"] = len(monthly_reviews)

            for mri in monthly_review_items:
                _insert_row(
                    conn,
                    "monthly_review_items",
                    mri,
                    ignore_columns={"id", "month_key"},
                    remap={
                        "review_id": id_maps["monthly_reviews"],
                        "account_id": id_maps["accounts"],
                    },
                )
            inserted["monthly_review_items"] = len(monthly_review_items)

            for ms in monthly_snapshots:
                _insert_row(
                    conn,
                    "monthly_snapshots",
                    ms,
                    ignore_columns={"id"},
                    remap={"account_id": id_maps["accounts"]},
                )
            inserted["monthly_snapshots"] = len(monthly_snapshots)

            for pds in portfolio_daily_snapshots:
                _insert_row(
                    conn,
                    "portfolio_daily_snapshots",
                    pds,
                    overrides={"user_id": user_id},
                    ignore_columns={"id"},
                )
            inserted["portfolio_daily_snapshots"] = len(portfolio_daily_snapshots)

            for ads in account_daily_snapshots:
                _insert_row(
                    conn,
                    "account_daily_snapshots",
                    ads,
                    overrides={"user_id": user_id},
                    ignore_columns={"id"},
                    remap={"account_id": id_maps["accounts"]},
                )
            inserted["account_daily_snapshots"] = len(account_daily_snapshots)

            for h in holdings:
                _insert_row(
                    conn,
                    "holdings",
                    h,
                    ignore_columns={"id", "account_name"},
                    remap={
                        "account_id": id_maps["accounts"],
                        "holding_catalogue_id": id_maps["holding_catalogue"],
                    },
                )
            inserted["holdings"] = len(holdings)

            for co in contribution_overrides:
                _insert_row(
                    conn,
                    "contribution_overrides",
                    co,
                    ignore_columns={"id"},
                    remap={"account_id": id_maps["accounts"]},
                )
            inserted["contribution_overrides"] = len(contribution_overrides)

            for cfe in cash_flow_events:
                _insert_row(
                    conn,
                    "cash_flow_events",
                    cfe,
                    overrides={"user_id": user_id},
                    ignore_columns={"id"},
                    remap={
                        "account_id": id_maps["accounts"],
                        "counterparty_account_id": id_maps["accounts"],
                    },
                )
            inserted["cash_flow_events"] = len(cash_flow_events)

            for ic in isa_contributions:
                _insert_row(
                    conn,
                    "isa_contributions",
                    ic,
                    overrides={"user_id": user_id},
                    ignore_columns={"id"},
                    remap={"account_id": id_maps["accounts"]},
                )
            inserted["isa_contributions"] = len(isa_contributions)

            for pc in pension_contributions:
                _insert_row(
                    conn,
                    "pension_contributions",
                    pc,
                    overrides={"user_id": user_id},
                    ignore_columns={"id"},
                    remap={"account_id": id_maps["accounts"]},
                )
            inserted["pension_contributions"] = len(pension_contributions)

            for dr in dividend_records:
                _insert_row(
                    conn,
                    "dividend_records",
                    dr,
                    overrides={"user_id": user_id},
                    ignore_columns={"id"},
                    remap={"account_id": id_maps["accounts"]},
                )
            inserted["dividend_records"] = len(dividend_records)

            cgt_cols = _table_columns(conn, "cgt_disposals")
            for cd in cgt_disposals:
                remap = {}
                if "account_id" in cgt_cols:
                    remap["account_id"] = id_maps["accounts"]
                _insert_row(
                    conn,
                    "cgt_disposals",
                    cd,
                    overrides={"user_id": user_id},
                    ignore_columns={"id"},
                    remap=remap,
                )
            inserted["cgt_disposals"] = len(cgt_disposals)

            for pcf in pension_carry_forward:
                _insert_row(
                    conn,
                    "pension_carry_forward",
                    pcf,
                    overrides={"user_id": user_id},
                    ignore_columns={"id"},
                )
            inserted["pension_carry_forward"] = len(pension_carry_forward)

            for at in allowance_tracking:
                _insert_row(
                    conn,
                    "allowance_tracking",
                    at,
                    overrides={"user_id": user_id},
                    ignore_columns={"id"},
                )
            inserted["allowance_tracking"] = len(allowance_tracking)

            for pb in premium_bonds_prizes:
                _insert_row(
                    conn,
                    "premium_bonds_prizes",
                    pb,
                    overrides={"user_id": user_id},
                    ignore_columns={"id"},
                    remap={"account_id": id_maps["accounts"]},
                )
            inserted["premium_bonds_prizes"] = len(premium_bonds_prizes)

            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise

        return {
            "ok": True,
            "meta": {
                "export_schema_version": meta.get("export_schema_version"),
                "exported_at": meta.get("exported_at"),
            },
            "deleted": deleted,
            "inserted": inserted,
            "id_maps": id_maps,
        }
    finally:
        if owns_conn and conn_cm is not None:
            conn_cm.__exit__(None, None, None)
