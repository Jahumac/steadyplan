import json
from datetime import datetime


SUPPORTED_EXPORT_SCHEMA_VERSIONS = {1}
STALE_EXPORT_WARNING_DAYS = 90


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


def _non_empty_str(x):
    if not isinstance(x, str):
        return None
    s = x.strip()
    return s if s else None


def _is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def validate_restore_backup_json(json_bytes):
    """Validate a SteadyPlan export payload for dry-run restore.

    Does not perform any database reads/writes.
    Returns a dict with:
      - valid: bool
      - app: str|None
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
        errors.append("Export file must be provided as bytes.")
        return {
            "valid": False,
            "app": None,
            "export_schema_version": None,
            "exported_at": None,
            "counts": {},
            "errors": errors,
            "warnings": warnings,
        }

    try:
        payload = json.loads(json_bytes.decode("utf-8"))
    except Exception:
        errors.append("Invalid JSON: could not parse export file.")
        return {
            "valid": False,
            "app": None,
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
            "app": None,
            "export_schema_version": None,
            "exported_at": None,
            "counts": {},
            "errors": errors,
            "warnings": warnings,
        }

    meta = payload.get("meta")
    if not _is_mapping(meta):
        errors.append("Missing or invalid 'meta' section.")
        app_name = None
        export_schema_version = None
        exported_at = None
    else:
        app_name = _non_empty_str(meta.get("app"))
        export_schema_version = meta.get("export_schema_version")
        exported_at = meta.get("exported_at")

        if app_name and app_name != "SteadyPlan":
            warnings.append(f"Export was created by '{app_name}'. Expected 'SteadyPlan'.")
        elif not app_name:
            warnings.append("Export is missing meta.app (app name).")

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
        else:
            dt = _parse_iso_timestamp(exported_at)
            if dt is not None:
                now = datetime.now(dt.tzinfo) if dt.tzinfo is not None else datetime.now()
                try:
                    age_days = (now - dt).days
                except Exception:
                    age_days = None
                if age_days is not None and age_days >= STALE_EXPORT_WARNING_DAYS:
                    warnings.append(
                        f"Export is {age_days} days old. Restore will work, but any newer changes will be lost."
                    )

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
    for idx, a in enumerate(accounts or []):
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
        if _non_empty_str(a.get("name")) is None:
            errors.append(f"Missing accounts[{idx}].name.")

    catalogue_ids = set()
    seen_catalogue_tickers = set()
    for idx, c in enumerate(holding_catalogue or []):
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
        if _non_empty_str(c.get("holding_name")) is None:
            errors.append(f"Missing holding_catalogue[{idx}].holding_name.")
        ticker = _non_empty_str(c.get("ticker"))
        if ticker:
            if ticker in seen_catalogue_tickers:
                errors.append(f"Duplicate holding_catalogue[].ticker: {ticker}.")
            else:
                seen_catalogue_tickers.add(ticker)

    debt_ids = set()
    for idx, d in enumerate(debts or []):
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
        if _non_empty_str(d.get("name")) is None:
            errors.append(f"Missing debts[{idx}].name.")
        for key in ("current_balance", "monthly_payment"):
            if key in d and d.get(key) is None:
                errors.append(f"Invalid debts[{idx}].{key} (must not be null).")

    budget_item_ids = set()
    for idx, bi in enumerate(budget_items or []):
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
        if _non_empty_str(bi.get("name")) is None:
            errors.append(f"Missing budget.items[{idx}].name.")
        if _non_empty_str(bi.get("section")) is None:
            errors.append(f"Missing budget.items[{idx}].section.")

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

    for idx, h in enumerate(holdings or []):
        if not _is_mapping(h):
            errors.append("Invalid holdings entry (must be an object).")
            continue
        aid = h.get("account_id")
        if not isinstance(aid, int):
            errors.append("Invalid holdings[].account_id (must be an integer).")
            continue
        if aid not in account_ids:
            errors.append("Invalid holdings[].account_id (references missing account).")
        if _non_empty_str(h.get("holding_name")) is None:
            errors.append(f"Missing holdings[{idx}].holding_name.")
        cid = h.get("holding_catalogue_id")
        if cid is not None:
            if not isinstance(cid, int):
                errors.append("Invalid holdings[].holding_catalogue_id (must be integer or null).")
            elif cid not in catalogue_ids:
                errors.append("Invalid holdings[].holding_catalogue_id (references missing holding_catalogue).")

    for idx, be in enumerate(budget_entries or []):
        if not _is_mapping(be):
            errors.append("Invalid budget.entries entry (must be an object).")
            continue
        if _non_empty_str(be.get("month_key")) is None:
            errors.append(f"Missing budget.entries[{idx}].month_key.")
        bid = be.get("budget_item_id")
        if not isinstance(bid, int):
            errors.append("Invalid budget.entries[].budget_item_id (must be an integer).")
            continue
        if bid not in budget_item_ids:
            errors.append("Invalid budget.entries[].budget_item_id (references missing budget item).")

    for idx, ms in enumerate(monthly_snapshots or []):
        if not _is_mapping(ms):
            errors.append("Invalid history.monthly_snapshots entry (must be an object).")
            continue
        if _non_empty_str(ms.get("snapshot_date")) is None:
            errors.append(f"Missing history.monthly_snapshots[{idx}].snapshot_date.")
        aid = ms.get("account_id")
        if not isinstance(aid, int):
            errors.append("Invalid history.monthly_snapshots[].account_id (must be an integer).")
            continue
        if aid not in account_ids:
            errors.append("Invalid history.monthly_snapshots[].account_id (references missing account).")

    for idx, ads in enumerate(account_daily_snapshots or []):
        if not _is_mapping(ads):
            errors.append("Invalid history.account_daily_snapshots entry (must be an object).")
            continue
        if _non_empty_str(ads.get("snapshot_date")) is None:
            errors.append(f"Missing history.account_daily_snapshots[{idx}].snapshot_date.")
        if not _is_number(ads.get("value")):
            errors.append(f"Invalid history.account_daily_snapshots[{idx}].value (must be a number).")
        aid = ads.get("account_id")
        if not isinstance(aid, int):
            errors.append("Invalid history.account_daily_snapshots[].account_id (must be an integer).")
            continue
        if aid not in account_ids:
            errors.append("Invalid history.account_daily_snapshots[].account_id (references missing account).")

    for idx, co in enumerate(contribution_overrides or []):
        if not _is_mapping(co):
            errors.append("Invalid planning.contribution_overrides entry (must be an object).")
            continue
        if _non_empty_str(co.get("from_month")) is None:
            errors.append(f"Missing planning.contribution_overrides[{idx}].from_month.")
        if _non_empty_str(co.get("to_month")) is None:
            errors.append(f"Missing planning.contribution_overrides[{idx}].to_month.")
        if not _is_number(co.get("override_amount")):
            errors.append(f"Invalid planning.contribution_overrides[{idx}].override_amount (must be a number).")
        aid = co.get("account_id")
        if not isinstance(aid, int):
            errors.append("Invalid planning.contribution_overrides[].account_id (must be an integer).")
            continue
        if aid not in account_ids:
            errors.append("Invalid planning.contribution_overrides[].account_id (references missing account).")

    for idx, cfe in enumerate(cash_flow_events or []):
        if not _is_mapping(cfe):
            errors.append("Invalid planning.cash_flow_events entry (must be an object).")
            continue
        if _non_empty_str(cfe.get("event_date")) is None:
            errors.append(f"Missing planning.cash_flow_events[{idx}].event_date.")
        if not _is_number(cfe.get("amount")):
            errors.append(f"Invalid planning.cash_flow_events[{idx}].amount (must be a number).")
        if "kind" in cfe and _non_empty_str(cfe.get("kind")) is None:
            errors.append(f"Invalid planning.cash_flow_events[{idx}].kind (must be a non-empty string).")
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

    monthly_review_ids = set()
    seen_review_month_keys = set()
    for idx, mr in enumerate(monthly_reviews or []):
        if not _is_mapping(mr):
            errors.append("Invalid history.monthly_reviews entry (must be an object).")
            continue
        mrid = mr.get("id")
        if not isinstance(mrid, int):
            errors.append("Invalid history.monthly_reviews[].id (must be an integer).")
            continue
        if mrid in monthly_review_ids:
            errors.append(f"Duplicate history.monthly_reviews[].id: {mrid}.")
            continue
        monthly_review_ids.add(mrid)
        mk = _non_empty_str(mr.get("month_key"))
        if not mk:
            errors.append(f"Missing history.monthly_reviews[{idx}].month_key.")
        elif mk in seen_review_month_keys:
            errors.append(f"Duplicate history.monthly_reviews[].month_key: {mk}.")
        else:
            seen_review_month_keys.add(mk)

    for mri in monthly_review_items or []:
        if not _is_mapping(mri):
            errors.append("Invalid history.monthly_review_items entry (must be an object).")
            continue
        rid = mri.get("review_id")
        if not isinstance(rid, int):
            errors.append("Invalid history.monthly_review_items[].review_id (must be an integer).")
        elif rid not in monthly_review_ids:
            errors.append("Invalid history.monthly_review_items[].review_id (references missing monthly review).")
        aid = mri.get("account_id")
        if not isinstance(aid, int):
            errors.append("Invalid history.monthly_review_items[].account_id (must be an integer).")
        elif aid not in account_ids:
            errors.append("Invalid history.monthly_review_items[].account_id (references missing account).")

    for idx, ic in enumerate(isa_contributions or []):
        if not _is_mapping(ic):
            errors.append("Invalid planning.isa_contributions entry (must be an object).")
            continue
        if _non_empty_str(ic.get("contribution_date")) is None:
            errors.append(f"Missing planning.isa_contributions[{idx}].contribution_date.")
        if not _is_number(ic.get("amount")):
            errors.append(f"Invalid planning.isa_contributions[{idx}].amount (must be a number).")
        aid = ic.get("account_id")
        if not isinstance(aid, int):
            errors.append("Invalid planning.isa_contributions[].account_id (must be an integer).")
        elif aid not in account_ids:
            errors.append("Invalid planning.isa_contributions[].account_id (references missing account).")

    for idx, pc in enumerate(pension_contributions or []):
        if not _is_mapping(pc):
            errors.append("Invalid planning.pension_contributions entry (must be an object).")
            continue
        if _non_empty_str(pc.get("contribution_date")) is None:
            errors.append(f"Missing planning.pension_contributions[{idx}].contribution_date.")
        if not _is_number(pc.get("amount")):
            errors.append(f"Invalid planning.pension_contributions[{idx}].amount (must be a number).")
        if "kind" in pc and _non_empty_str(pc.get("kind")) is None:
            errors.append(f"Invalid planning.pension_contributions[{idx}].kind (must be a non-empty string).")
        aid = pc.get("account_id")
        if not isinstance(aid, int):
            errors.append("Invalid planning.pension_contributions[].account_id (must be an integer).")
        elif aid not in account_ids:
            errors.append("Invalid planning.pension_contributions[].account_id (references missing account).")

    for idx, dr in enumerate(dividend_records or []):
        if not _is_mapping(dr):
            errors.append("Invalid planning.dividend_records entry (must be an object).")
            continue
        if _non_empty_str(dr.get("dividend_date")) is None:
            errors.append(f"Missing planning.dividend_records[{idx}].dividend_date.")
        if not _is_number(dr.get("amount")):
            errors.append(f"Invalid planning.dividend_records[{idx}].amount (must be a number).")
        aid = dr.get("account_id")
        if not isinstance(aid, int):
            errors.append("Invalid planning.dividend_records[].account_id (must be an integer).")
        elif aid not in account_ids:
            errors.append("Invalid planning.dividend_records[].account_id (references missing account).")

    for idx, cd in enumerate(cgt_disposals or []):
        if not _is_mapping(cd):
            errors.append("Invalid planning.cgt_disposals entry (must be an object).")
            continue
        if _non_empty_str(cd.get("disposal_date")) is None:
            errors.append(f"Missing planning.cgt_disposals[{idx}].disposal_date.")
        if _non_empty_str(cd.get("asset_name")) is None:
            errors.append(f"Missing planning.cgt_disposals[{idx}].asset_name.")
        if not _is_number(cd.get("proceeds")):
            errors.append(f"Invalid planning.cgt_disposals[{idx}].proceeds (must be a number).")
        if not _is_number(cd.get("cost_basis")):
            errors.append(f"Invalid planning.cgt_disposals[{idx}].cost_basis (must be a number).")
        if "account_id" in cd:
            aid = cd.get("account_id")
            if aid is not None and not isinstance(aid, int):
                errors.append("Invalid planning.cgt_disposals[].account_id (must be integer or null).")
            elif isinstance(aid, int) and aid not in account_ids:
                errors.append("Invalid planning.cgt_disposals[].account_id (references missing account).")

    seen_carry_forward_tax_years = set()
    for idx, pcf in enumerate(pension_carry_forward or []):
        if not _is_mapping(pcf):
            errors.append("Invalid planning.pension_carry_forward entry (must be an object).")
            continue
        ty = _non_empty_str(pcf.get("tax_year"))
        if not ty:
            errors.append(f"Missing planning.pension_carry_forward[{idx}].tax_year.")
        if not _is_number(pcf.get("unused_allowance")):
            errors.append(f"Invalid planning.pension_carry_forward[{idx}].unused_allowance (must be a number).")
        if ty:
            if ty in seen_carry_forward_tax_years:
                errors.append(f"Duplicate planning.pension_carry_forward[].tax_year: {ty}.")
            else:
                seen_carry_forward_tax_years.add(ty)

    for idx, pb in enumerate(premium_bonds_prizes or []):
        if not _is_mapping(pb):
            errors.append("Invalid planning.premium_bonds_prizes entry (must be an object).")
            continue
        aid = pb.get("account_id")
        if not isinstance(aid, int):
            errors.append("Invalid planning.premium_bonds_prizes[].account_id (must be an integer).")
        elif aid not in account_ids:
            errors.append("Invalid planning.premium_bonds_prizes[].account_id (references missing account).")
        mk = _non_empty_str(pb.get("month_key"))
        if not mk:
            errors.append(f"Missing planning.premium_bonds_prizes[{idx}].month_key.")
        if "prize_amount" in pb and not _is_number(pb.get("prize_amount")):
            errors.append(f"Invalid planning.premium_bonds_prizes[{idx}].prize_amount (must be a number).")

    for idx, at in enumerate(allowance_tracking or []):
        if not _is_mapping(at):
            errors.append("Invalid planning.allowance_tracking entry (must be an object).")
            continue
        if _non_empty_str(at.get("tax_year")) is None:
            errors.append(f"Missing planning.allowance_tracking[{idx}].tax_year.")

    for idx, g in enumerate(goals or []):
        if not _is_mapping(g):
            errors.append("Invalid goals entry (must be an object).")
            continue
        if _non_empty_str(g.get("name")) is None:
            errors.append(f"Missing goals[{idx}].name.")
        if not _is_number(g.get("target_value")):
            errors.append(f"Invalid goals[{idx}].target_value (must be a number).")

    seen_pb_prizes = set()
    for pb in premium_bonds_prizes or []:
        if not _is_mapping(pb):
            continue
        aid = pb.get("account_id")
        mk = _non_empty_str(pb.get("month_key"))
        if isinstance(aid, int) and mk:
            key = (aid, mk)
            if key in seen_pb_prizes:
                errors.append(f"Duplicate planning.premium_bonds_prizes[] for account_id={aid}, month_key={mk}.")
            else:
                seen_pb_prizes.add(key)

    seen_portfolio_snapshot_dates = set()
    for idx, pds in enumerate(portfolio_daily_snapshots or []):
        if not _is_mapping(pds):
            errors.append("Invalid history.portfolio_daily_snapshots entry (must be an object).")
            continue
        sd = _non_empty_str(pds.get("snapshot_date"))
        if not sd:
            errors.append(f"Missing history.portfolio_daily_snapshots[{idx}].snapshot_date.")
            continue
        if "total_value" in pds and not _is_number(pds.get("total_value")):
            errors.append(f"Invalid history.portfolio_daily_snapshots[{idx}].total_value (must be a number).")
        if sd in seen_portfolio_snapshot_dates:
            errors.append(f"Duplicate history.portfolio_daily_snapshots[].snapshot_date: {sd}.")
        else:
            seen_portfolio_snapshot_dates.add(sd)

    seen_account_daily = set()
    for ads in account_daily_snapshots or []:
        if not _is_mapping(ads):
            continue
        aid = ads.get("account_id")
        sd = _non_empty_str(ads.get("snapshot_date"))
        if isinstance(aid, int) and sd:
            key = (aid, sd)
            if key in seen_account_daily:
                errors.append(f"Duplicate history.account_daily_snapshots[] for account_id={aid}, snapshot_date={sd}.")
            else:
                seen_account_daily.add(key)

    seen_budget_entry_keys = set()
    for be in budget_entries or []:
        if not _is_mapping(be):
            continue
        mk = _non_empty_str(be.get("month_key"))
        bid = be.get("budget_item_id")
        if mk and isinstance(bid, int):
            key = (mk, bid)
            if key in seen_budget_entry_keys:
                errors.append(f"Duplicate budget.entries[] for month_key={mk}, budget_item_id={bid}.")
            else:
                seen_budget_entry_keys.add(key)

    seen_budget_section_keys = set()
    for idx, bs in enumerate(budget_sections or []):
        if not _is_mapping(bs):
            errors.append("Invalid budget.sections entry (must be an object).")
            continue
        key = _non_empty_str(bs.get("key"))
        if not key:
            errors.append(f"Missing budget.sections[{idx}].key.")
            continue
        if _non_empty_str(bs.get("label")) is None:
            errors.append(f"Missing budget.sections[{idx}].label.")
        if key in seen_budget_section_keys:
            errors.append(f"Duplicate budget.sections[].key: {key}.")
        else:
            seen_budget_section_keys.add(key)


    counts = {
        "accounts": len(accounts or []),
        "holdings": len(holdings or []),
        "holding_catalogue": len(holding_catalogue or []),
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
        "app": app_name if isinstance(meta, dict) else None,
        "export_schema_version": export_schema_version if isinstance(meta, dict) else None,
        "exported_at": exported_at if isinstance(meta, dict) else None,
        "counts": counts,
        "errors": errors,
        "warnings": warnings,
    }
