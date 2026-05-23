import json
from datetime import datetime


SUPPORTED_EXPORT_SCHEMA_VERSIONS = {1}


def _is_mapping(x):
    return isinstance(x, dict)


def _is_list(x):
    return isinstance(x, list)


def _parse_iso_timestamp(raw):
    if not isinstance(raw, str) or not raw.strip():
        return None
    s = raw.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def validate_restore_backup_json(json_bytes):
    """Validate a Shelly Finance export payload for dry-run restore.

    Does not perform any database reads/writes.
    Returns a dict with:
      - valid: bool
      - export_schema_version: int|None
      - exported_at: str|None
      - counts: dict
      - errors: list[str]
      - warnings: list[str]
    """
    errors = []
    warnings = []
    payload = None

    if not isinstance(json_bytes, (bytes, bytearray)):
        errors.append("Backup must be provided as bytes.")
        return {
            "valid": False,
            "export_schema_version": None,
            "exported_at": None,
            "counts": {},
            "errors": errors,
            "warnings": warnings,
        }

    try:
        payload = json.loads(json_bytes.decode("utf-8"))
    except Exception:
        errors.append("Invalid JSON: could not parse backup file.")
        return {
            "valid": False,
            "export_schema_version": None,
            "exported_at": None,
            "counts": {},
            "errors": errors,
            "warnings": warnings,
        }

    if not _is_mapping(payload):
        errors.append("Invalid JSON: top-level value must be an object.")
        return {
            "valid": False,
            "export_schema_version": None,
            "exported_at": None,
            "counts": {},
            "errors": errors,
            "warnings": warnings,
        }

    meta = payload.get("meta")
    if not _is_mapping(meta):
        errors.append("Missing or invalid 'meta' section.")
        export_schema_version = None
        exported_at = None
    else:
        export_schema_version = meta.get("export_schema_version")
        exported_at = meta.get("exported_at")

        if export_schema_version is None:
            errors.append("Missing meta.export_schema_version.")
        elif not isinstance(export_schema_version, int):
            errors.append("Invalid meta.export_schema_version (must be an integer).")
        elif export_schema_version not in SUPPORTED_EXPORT_SCHEMA_VERSIONS:
            errors.append(f"Unsupported export_schema_version: {export_schema_version}.")

        if exported_at is None:
            errors.append("Missing meta.exported_at.")
        elif _parse_iso_timestamp(exported_at) is None:
            errors.append("Invalid meta.exported_at (must be ISO-8601 timestamp).")

    required_top = [
        "assumptions",
        "accounts",
        "holdings",
        "holding_catalogue",
        "goals",
        "debts",
        "budget",
        "history",
        "planning",
    ]
    for k in required_top:
        if k not in payload:
            errors.append(f"Missing required top-level section: '{k}'.")

    assumptions = payload.get("assumptions")
    if "assumptions" in payload and not _is_mapping(assumptions):
        errors.append("Invalid 'assumptions' (must be an object).")

    accounts = payload.get("accounts")
    if "accounts" in payload and not _is_list(accounts):
        errors.append("Invalid 'accounts' (must be an array).")
        accounts = []

    holdings = payload.get("holdings")
    if "holdings" in payload and not _is_list(holdings):
        errors.append("Invalid 'holdings' (must be an array).")
        holdings = []

    holding_catalogue = payload.get("holding_catalogue")
    if "holding_catalogue" in payload and not _is_list(holding_catalogue):
        errors.append("Invalid 'holding_catalogue' (must be an array).")
        holding_catalogue = []

    goals = payload.get("goals")
    if "goals" in payload and not _is_list(goals):
        errors.append("Invalid 'goals' (must be an array).")
        goals = []

    debts = payload.get("debts")
    if "debts" in payload and not _is_list(debts):
        errors.append("Invalid 'debts' (must be an array).")
        debts = []

    budget = payload.get("budget")
    if "budget" in payload and not _is_mapping(budget):
        errors.append("Invalid 'budget' (must be an object).")
        budget = {}

    history = payload.get("history")
    if "history" in payload and not _is_mapping(history):
        errors.append("Invalid 'history' (must be an object).")
        history = {}

    planning = payload.get("planning")
    if "planning" in payload and not _is_mapping(planning):
        errors.append("Invalid 'planning' (must be an object).")
        planning = {}

    budget_sections = (budget or {}).get("sections")
    budget_items = (budget or {}).get("items")
    budget_entries = (budget or {}).get("entries")
    if "budget" in payload:
        if not _is_list(budget_sections):
            errors.append("Invalid budget.sections (must be an array).")
            budget_sections = []
        if not _is_list(budget_items):
            errors.append("Invalid budget.items (must be an array).")
            budget_items = []
        if not _is_list(budget_entries):
            errors.append("Invalid budget.entries (must be an array).")
            budget_entries = []

    required_history = [
        "monthly_snapshots",
        "portfolio_daily_snapshots",
        "account_daily_snapshots",
        "monthly_reviews",
        "monthly_review_items",
    ]
    for k in required_history:
        if "history" in payload and k not in (history or {}):
            errors.append(f"Missing history.{k}.")

    monthly_snapshots = (history or {}).get("monthly_snapshots") or []
    portfolio_daily_snapshots = (history or {}).get("portfolio_daily_snapshots") or []
    account_daily_snapshots = (history or {}).get("account_daily_snapshots") or []
    monthly_reviews = (history or {}).get("monthly_reviews") or []
    monthly_review_items = (history or {}).get("monthly_review_items") or []

    if "history" in payload:
        if not _is_list(monthly_snapshots):
            errors.append("Invalid history.monthly_snapshots (must be an array).")
            monthly_snapshots = []
        if not _is_list(portfolio_daily_snapshots):
            errors.append("Invalid history.portfolio_daily_snapshots (must be an array).")
            portfolio_daily_snapshots = []
        if not _is_list(account_daily_snapshots):
            errors.append("Invalid history.account_daily_snapshots (must be an array).")
            account_daily_snapshots = []
        if not _is_list(monthly_reviews):
            errors.append("Invalid history.monthly_reviews (must be an array).")
            monthly_reviews = []
        if not _is_list(monthly_review_items):
            errors.append("Invalid history.monthly_review_items (must be an array).")
            monthly_review_items = []

    required_planning = [
        "contribution_overrides",
        "cash_flow_events",
        "isa_contributions",
        "pension_contributions",
        "dividend_records",
        "cgt_disposals",
        "pension_carry_forward",
        "allowance_tracking",
        "premium_bonds_prizes",
    ]
    for k in required_planning:
        if "planning" in payload and k not in (planning or {}):
            errors.append(f"Missing planning.{k}.")

    contribution_overrides = (planning or {}).get("contribution_overrides") or []
    cash_flow_events = (planning or {}).get("cash_flow_events") or []
    isa_contributions = (planning or {}).get("isa_contributions") or []
    pension_contributions = (planning or {}).get("pension_contributions") or []
    dividend_records = (planning or {}).get("dividend_records") or []
    cgt_disposals = (planning or {}).get("cgt_disposals") or []
    pension_carry_forward = (planning or {}).get("pension_carry_forward") or []
    allowance_tracking = (planning or {}).get("allowance_tracking") or []
    premium_bonds_prizes = (planning or {}).get("premium_bonds_prizes") or []

    if "planning" in payload:
        for key, val in [
            ("planning.contribution_overrides", contribution_overrides),
            ("planning.cash_flow_events", cash_flow_events),
            ("planning.isa_contributions", isa_contributions),
            ("planning.pension_contributions", pension_contributions),
            ("planning.dividend_records", dividend_records),
            ("planning.cgt_disposals", cgt_disposals),
            ("planning.pension_carry_forward", pension_carry_forward),
            ("planning.allowance_tracking", allowance_tracking),
            ("planning.premium_bonds_prizes", premium_bonds_prizes),
        ]:
            if not _is_list(val):
                errors.append(f"Invalid {key} (must be an array).")

    account_ids = set()
    for a in accounts or []:
        if not _is_mapping(a):
            errors.append("Invalid accounts entry (must be an object).")
            continue
        aid = a.get("id")
        if not isinstance(aid, int):
            errors.append("Invalid accounts[].id (must be an integer).")
            continue
        if aid in account_ids:
            errors.append(f"Duplicate accounts[].id: {aid}.")
            continue
        account_ids.add(aid)

    catalogue_ids = set()
    for c in holding_catalogue or []:
        if not _is_mapping(c):
            errors.append("Invalid holding_catalogue entry (must be an object).")
            continue
        cid = c.get("id")
        if not isinstance(cid, int):
            errors.append("Invalid holding_catalogue[].id (must be an integer).")
            continue
        if cid in catalogue_ids:
            errors.append(f"Duplicate holding_catalogue[].id: {cid}.")
            continue
        catalogue_ids.add(cid)

    debt_ids = set()
    for d in debts or []:
        if not _is_mapping(d):
            errors.append("Invalid debts entry (must be an object).")
            continue
        did = d.get("id")
        if not isinstance(did, int):
            errors.append("Invalid debts[].id (must be an integer).")
            continue
        if did in debt_ids:
            errors.append(f"Duplicate debts[].id: {did}.")
            continue
        debt_ids.add(did)

    budget_item_ids = set()
    for bi in budget_items or []:
        if not _is_mapping(bi):
            errors.append("Invalid budget.items entry (must be an object).")
            continue
        bid = bi.get("id")
        if not isinstance(bid, int):
            errors.append("Invalid budget.items[].id (must be an integer).")
            continue
        if bid in budget_item_ids:
            errors.append(f"Duplicate budget.items[].id: {bid}.")
            continue
        budget_item_ids.add(bid)

        linked_account_id = bi.get("linked_account_id")
        if linked_account_id is not None:
            if not isinstance(linked_account_id, int):
                errors.append("Invalid budget.items[].linked_account_id (must be integer or null).")
            elif linked_account_id not in account_ids:
                errors.append("Invalid budget.items[].linked_account_id (references missing account).")

        linked_debt_id = bi.get("linked_debt_id")
        if linked_debt_id is not None:
            if not isinstance(linked_debt_id, int):
                errors.append("Invalid budget.items[].linked_debt_id (must be integer or null).")
            elif linked_debt_id not in debt_ids:
                errors.append("Invalid budget.items[].linked_debt_id (references missing debt).")

    for h in holdings or []:
        if not _is_mapping(h):
            errors.append("Invalid holdings entry (must be an object).")
            continue
        aid = h.get("account_id")
        if not isinstance(aid, int):
            errors.append("Invalid holdings[].account_id (must be an integer).")
            continue
        if aid not in account_ids:
            errors.append("Invalid holdings[].account_id (references missing account).")
        cid = h.get("holding_catalogue_id")
        if cid is not None:
            if not isinstance(cid, int):
                errors.append("Invalid holdings[].holding_catalogue_id (must be integer or null).")
            elif cid not in catalogue_ids:
                errors.append("Invalid holdings[].holding_catalogue_id (references missing holding_catalogue).")

    for be in budget_entries or []:
        if not _is_mapping(be):
            errors.append("Invalid budget.entries entry (must be an object).")
            continue
        bid = be.get("budget_item_id")
        if not isinstance(bid, int):
            errors.append("Invalid budget.entries[].budget_item_id (must be an integer).")
            continue
        if bid not in budget_item_ids:
            errors.append("Invalid budget.entries[].budget_item_id (references missing budget item).")

    for ms in monthly_snapshots or []:
        if not _is_mapping(ms):
            errors.append("Invalid history.monthly_snapshots entry (must be an object).")
            continue
        aid = ms.get("account_id")
        if not isinstance(aid, int):
            errors.append("Invalid history.monthly_snapshots[].account_id (must be an integer).")
            continue
        if aid not in account_ids:
            errors.append("Invalid history.monthly_snapshots[].account_id (references missing account).")

    for ads in account_daily_snapshots or []:
        if not _is_mapping(ads):
            errors.append("Invalid history.account_daily_snapshots entry (must be an object).")
            continue
        aid = ads.get("account_id")
        if not isinstance(aid, int):
            errors.append("Invalid history.account_daily_snapshots[].account_id (must be an integer).")
            continue
        if aid not in account_ids:
            errors.append("Invalid history.account_daily_snapshots[].account_id (references missing account).")

    for co in contribution_overrides or []:
        if not _is_mapping(co):
            errors.append("Invalid planning.contribution_overrides entry (must be an object).")
            continue
        aid = co.get("account_id")
        if not isinstance(aid, int):
            errors.append("Invalid planning.contribution_overrides[].account_id (must be an integer).")
            continue
        if aid not in account_ids:
            errors.append("Invalid planning.contribution_overrides[].account_id (references missing account).")

    for cfe in cash_flow_events or []:
        if not _is_mapping(cfe):
            errors.append("Invalid planning.cash_flow_events entry (must be an object).")
            continue
        aid = cfe.get("account_id")
        if not isinstance(aid, int):
            errors.append("Invalid planning.cash_flow_events[].account_id (must be an integer).")
            continue
        if aid not in account_ids:
            errors.append("Invalid planning.cash_flow_events[].account_id (references missing account).")
        cpid = cfe.get("counterparty_account_id")
        if cpid is not None:
            if not isinstance(cpid, int):
                errors.append("Invalid planning.cash_flow_events[].counterparty_account_id (must be integer or null).")
            elif cpid not in account_ids:
                errors.append("Invalid planning.cash_flow_events[].counterparty_account_id (references missing account).")

    counts = {
        "accounts": len(accounts or []),
        "holdings": len(holdings or []),
        "holding_catalogue": len(holding_catalogue or []),
        "goals": len(goals or []),
        "debts": len(debts or []),
        "budget": {
            "sections": len(budget_sections or []),
            "items": len(budget_items or []),
            "entries": len(budget_entries or []),
        },
        "history": {
            "monthly_snapshots": len(monthly_snapshots or []),
            "portfolio_daily_snapshots": len(portfolio_daily_snapshots or []),
            "account_daily_snapshots": len(account_daily_snapshots or []),
            "monthly_reviews": len(monthly_reviews or []),
            "monthly_review_items": len(monthly_review_items or []),
        },
        "planning": {
            "contribution_overrides": len(contribution_overrides or []),
            "cash_flow_events": len(cash_flow_events or []),
            "isa_contributions": len(isa_contributions or []),
            "pension_contributions": len(pension_contributions or []),
            "dividend_records": len(dividend_records or []),
            "cgt_disposals": len(cgt_disposals or []),
            "pension_carry_forward": len(pension_carry_forward or []),
            "allowance_tracking": len(allowance_tracking or []),
            "premium_bonds_prizes": len(premium_bonds_prizes or []),
        },
    }

    return {
        "valid": len(errors) == 0,
        "export_schema_version": export_schema_version if isinstance(meta, dict) else None,
        "exported_at": exported_at if isinstance(meta, dict) else None,
        "counts": counts,
        "errors": errors,
        "warnings": warnings,
    }

