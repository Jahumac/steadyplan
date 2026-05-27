from datetime import date, datetime

from app.calculations import add_months_to_key, effective_account_value
from app.models import (
    fetch_all_accounts,
    fetch_all_active_overrides,
    fetch_all_debts,
    fetch_budget_entries,
    fetch_budget_items,
    fetch_budget_sections,
    fetch_holding_totals_by_account,
    fetch_prior_month_budget_entries,
)
from app.models.debts import debt_months_remaining
from app.services.planning_insights import classify_account


def _debt_payoff_month_key(debt):
    """Return YYYY-MM when the debt clears (from today), or None if it never does."""
    balance = float(debt["current_balance"] or 0)
    payment = float(debt["monthly_payment"] or 0)
    apr = float(debt["apr"] or 0)
    months = debt_months_remaining(balance, payment, apr)
    if not months:
        return None
    today = date.today()
    return add_months_to_key(f"{today.year}-{today.month:02d}", months)


def _month_label(month_key):
    return datetime.strptime(month_key, "%Y-%m").strftime("%B %Y")


def _build_signals(summary):
    signals = []
    if summary["total_income"] <= 0:
        signals.append(
            {
                "level": "warning",
                "code": "no_income_budgeted",
                "message": "No income is budgeted for this month, so affordability answers will be pessimistic.",
            }
        )
    if summary["available_after_budget"] < 0:
        signals.append(
            {
                "level": "warning",
                "code": "budget_deficit",
                "message": "Planned take-home outgoings are higher than planned income for this month.",
            }
        )
    elif summary["available_after_budget"] == 0 and summary["total_income"] > 0:
        signals.append(
            {
                "level": "info",
                "code": "fully_allocated",
                "message": "All planned take-home income is already allocated in this budget.",
            }
        )
    if summary["pre_salary_total"] > 0:
        signals.append(
            {
                "level": "info",
                "code": "pre_salary_contributions_excluded",
                "message": "Pre-salary contributions are shown for visibility but excluded from take-home affordability.",
            }
        )
    return signals


def build_assistant_portfolio_overview(user_id):
    """Return a read-only portfolio snapshot for assistant reasoning.

    Uses effective account values so holdings-based accounts reflect the live
    holdings total plus uninvested cash, rather than relying on stale
    current_value fields.
    """
    accounts = fetch_all_accounts(user_id)
    holdings_totals = fetch_holding_totals_by_account(user_id)

    account_rows = []
    accessible_total = 0.0
    restricted_total = 0.0
    locked_total = 0.0

    for account in accounts:
        classification = classify_account(account)
        holdings_value = float(holdings_totals.get(account["id"], 0) or 0)
        uninvested_cash = float(account.get("uninvested_cash") or 0)
        effective_value = float(effective_account_value(account, holdings_totals) or 0)
        accessible_value = effective_value if classification.access_type == "accessible" else 0.0

        if classification.access_type == "accessible":
            accessible_total += effective_value
        elif classification.access_type == "restricted":
            restricted_total += effective_value
        else:
            locked_total += effective_value

        account_rows.append(
            {
                "id": account["id"],
                "name": account["name"],
                "provider": account["provider"],
                "wrapper_type": account["wrapper_type"],
                "category": account["category"],
                "owner": account["owner"],
                "valuation_mode": account["valuation_mode"],
                "current_value": float(account.get("current_value") or 0),
                "holdings_value": holdings_value,
                "uninvested_cash": uninvested_cash,
                "effective_value": effective_value,
                "monthly_contribution": float(account.get("monthly_contribution") or 0),
                "accessible_value": accessible_value,
                "access_type": classification.access_type,
                "access_label": classification.label,
                "access_reason": classification.reason,
            }
        )

    total_net_worth = accessible_total + restricted_total + locked_total
    return {
        "summary": {
            "total_net_worth": total_net_worth,
            "accessible_total": accessible_total,
            "restricted_total": restricted_total,
            "locked_total": locked_total,
            "accessible_pct": (accessible_total / total_net_worth * 100.0) if total_net_worth else 0.0,
            "restricted_pct": (restricted_total / total_net_worth * 100.0) if total_net_worth else 0.0,
            "locked_pct": (locked_total / total_net_worth * 100.0) if total_net_worth else 0.0,
            "account_count": len(account_rows),
        },
        "accounts": account_rows,
    }


def _build_affordability_signals(*, purchase_amount, spread_months, monthly_cost, available_after_budget,
                                accessible_total, remaining_budget_after_purchase,
                                accessible_after_purchase):
    signals = []
    if spread_months > 1:
        signals.append(
            {
                "level": "info",
                "code": "spread_applied",
                "message": f"Affordability is being assessed as {spread_months} monthly payments of {monthly_cost:.2f}, not a single upfront hit.",
            }
        )
    if available_after_budget < 0:
        signals.append(
            {
                "level": "warning",
                "code": "budget_already_negative",
                "message": "This month is already budgeted at a deficit before the proposed purchase.",
            }
        )
    if remaining_budget_after_purchase < 0:
        signals.append(
            {
                "level": "warning",
                "code": "purchase_exceeds_budget_headroom",
                "message": "This purchase would push the month beyond planned take-home budget headroom.",
            }
        )
    else:
        signals.append(
            {
                "level": "info",
                "code": "fits_monthly_budget",
                "message": "This purchase fits within the planned monthly budget headroom.",
            }
        )
    if accessible_after_purchase < 0:
        signals.append(
            {
                "level": "warning",
                "code": "purchase_exceeds_accessible_assets",
                "message": "The purchase is larger than assets currently classed as accessible before pension age.",
            }
        )
    elif purchase_amount > max(available_after_budget, 0):
        signals.append(
            {
                "level": "info",
                "code": "would_require_accessible_assets",
                "message": "You could fund this from accessible assets, but not purely from this month's planned budget surplus.",
            }
        )
    if accessible_total > 0:
        signals.append(
            {
                "level": "info",
                "code": "accessible_assets_not_cash",
                "message": "Accessible totals can include ISA/investment assets and should not be treated as the same thing as spare bank cash.",
            }
        )
    return signals


def build_assistant_month_summary(user_id, month_key):
    """Return a read-oriented month summary suitable for assistant reasoning.

    Mirrors the budget page's month roll-up rules so assistant answers use the
    same sources: explicit month entries first, linked account/debt values next,
    then inherited prior-month values, then defaults.
    """
    db_sections = fetch_budget_sections(user_id)
    items = fetch_budget_items(user_id)
    entries = fetch_budget_entries(month_key, user_id)
    entry_map = {e["budget_item_id"]: e for e in entries}
    active_overrides = fetch_all_active_overrides(month_key, user_id)
    accounts = fetch_all_accounts(user_id)
    account_map = {a["id"]: a for a in accounts}
    debts = fetch_all_debts(user_id)
    debt_map = {d["id"]: d for d in debts}
    prior_entries = fetch_prior_month_budget_entries(month_key, user_id)
    prior_entry_map = {e["budget_item_id"]: e for e in prior_entries}

    income_section = next((s for s in db_sections if "income" in s["key"].lower()), None)
    income_key = income_section["key"] if income_section else (db_sections[0]["key"] if db_sections else "income")
    today_key = date.today().strftime("%Y-%m")

    sections = []
    section_totals = {}

    for sec in db_sections:
        section_key = sec["key"]
        section_rows = []
        for item in items:
            if item["section"] != section_key:
                continue

            linked_debt = debt_map.get(item["linked_debt_id"]) if item["linked_debt_id"] else None
            if item["linked_debt_id"] and month_key > today_key:
                payoff_month_key = _debt_payoff_month_key(linked_debt) if linked_debt else None
                if payoff_month_key and month_key > payoff_month_key:
                    continue

            linked_account = account_map.get(item["linked_account_id"]) if item["linked_account_id"] else None
            is_linked_account = linked_account is not None
            is_linked_debt = linked_debt is not None

            if item["id"] in entry_map:
                amount = float(entry_map[item["id"]]["amount"] or 0)
                source = "manual_override"
            elif is_linked_account and linked_account["id"] in active_overrides:
                amount = float(active_overrides[linked_account["id"]]["override_amount"] or 0)
                source = "manual_override"
            elif is_linked_account:
                amount = float(linked_account["monthly_contribution"] or 0)
                source = "linked_account"
            elif is_linked_debt:
                amount = float(linked_debt.get("monthly_payment") or 0)
                source = "linked_debt"
            elif item["id"] in prior_entry_map:
                amount = float(prior_entry_map[item["id"]]["amount"] or 0)
                source = "inherited"
            else:
                amount = float(item["default_amount"] or 0)
                source = "default"

            pre_salary = bool(linked_account.get("pre_salary")) if linked_account else False
            section_rows.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "notes": item["notes"],
                    "amount": amount,
                    "source": source,
                    "linked_account_id": item["linked_account_id"],
                    "linked_account_name": linked_account["name"] if linked_account else None,
                    "linked_debt_id": item["linked_debt_id"],
                    "linked_debt_name": linked_debt["name"] if linked_debt else None,
                    "pre_salary": pre_salary,
                }
            )

        total = sum(row["amount"] for row in section_rows)
        section_totals[section_key] = total
        sections.append(
            {
                "key": section_key,
                "label": sec["label"],
                "rows": section_rows,
                "total": total,
            }
        )

    pre_salary_total = sum(
        row["amount"]
        for section in sections
        for row in section["rows"]
        if row.get("pre_salary")
    )
    total_income = section_totals.get(income_key, 0.0)
    total_expenses = sum(total for key, total in section_totals.items() if key != income_key)
    take_home_outgoings = total_expenses - pre_salary_total
    available_after_budget = total_income - take_home_outgoings

    planned_savings = sum(
        section_totals.get(sec["key"], 0.0)
        for sec in db_sections
        if sec["key"] != income_key and ("invest" in sec["key"].lower() or "saving" in sec["key"].lower())
    )
    planned_debt_payments = sum(
        section_totals.get(sec["key"], 0.0)
        for sec in db_sections
        if "debt" in sec["key"].lower()
    )
    savings_rate = (planned_savings / total_income * 100) if total_income > 0 else 0.0

    summary = {
        "total_income": total_income,
        "total_expenses": total_expenses,
        "pre_salary_total": pre_salary_total,
        "take_home_outgoings": take_home_outgoings,
        "planned_savings": planned_savings,
        "planned_debt_payments": planned_debt_payments,
        "available_after_budget": available_after_budget,
        "savings_rate": savings_rate,
    }

    return {
        "month": month_key,
        "month_label": _month_label(month_key),
        "summary": summary,
        "signals": _build_signals(summary),
        "sections": sections,
    }



def build_assistant_affordability(user_id, month_key, purchase_amount, spread_months=1):
    """Assess a proposed purchase against budget headroom and accessible assets.

    This remains read-only and intentionally conservative:
    - budget affordability uses the month-summary take-home surplus
    - backup funding uses assets classed as accessible before pension age
    - accessible assets are not assumed to be idle cash
    """
    month_data = build_assistant_month_summary(user_id, month_key)
    portfolio_data = build_assistant_portfolio_overview(user_id)

    purchase_amount = float(purchase_amount or 0)
    spread_months = int(spread_months or 1)
    monthly_cost = purchase_amount / spread_months if spread_months > 0 else purchase_amount

    available_after_budget = float(month_data["summary"]["available_after_budget"] or 0)
    accessible_total = float(portfolio_data["summary"]["accessible_total"] or 0)
    restricted_total = float(portfolio_data["summary"]["restricted_total"] or 0)
    locked_total = float(portfolio_data["summary"]["locked_total"] or 0)

    remaining_budget_after_purchase = available_after_budget - monthly_cost
    accessible_after_purchase = accessible_total - purchase_amount

    budget_affordable = remaining_budget_after_purchase >= 0
    accessible_funding_available = accessible_after_purchase >= 0

    if budget_affordable:
        verdict = "yes"
        verdict_reason = "It fits inside the planned monthly budget headroom."
    elif accessible_funding_available:
        verdict = "caution"
        verdict_reason = "It does not fit the planned monthly budget on its own, but it could be covered from assets currently classed as accessible before pension age."
    else:
        verdict = "no"
        verdict_reason = "It does not fit the monthly budget headroom and would also exceed currently accessible pre-pension assets."

    return {
        "month": month_data["month"],
        "month_label": month_data["month_label"],
        "purchase": {
            "amount": purchase_amount,
            "spread_months": spread_months,
            "monthly_cost": monthly_cost,
        },
        "assessment": {
            "verdict": verdict,
            "verdict_reason": verdict_reason,
            "budget_affordable": budget_affordable,
            "accessible_funding_available": accessible_funding_available,
        },
        "budget": {
            "available_after_budget": available_after_budget,
            "remaining_after_purchase": remaining_budget_after_purchase,
        },
        "access": {
            "accessible_total": accessible_total,
            "restricted_total": restricted_total,
            "locked_total": locked_total,
            "accessible_after_purchase": accessible_after_purchase,
        },
        "signals": _build_affordability_signals(
            purchase_amount=purchase_amount,
            spread_months=spread_months,
            monthly_cost=monthly_cost,
            available_after_budget=available_after_budget,
            accessible_total=accessible_total,
            remaining_budget_after_purchase=remaining_budget_after_purchase,
            accessible_after_purchase=accessible_after_purchase,
        ),
    }
