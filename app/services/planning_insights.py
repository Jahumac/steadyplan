"""Planning insights: accessible security and retirement income estimates.

This module deliberately keeps the first Planning tab small and explainable:
- classify accounts by access (accessible / restricted / locked)
- estimate time to accessible security milestones
- turn projected pots into illustrative retirement income ranges

It is not tax advice and does not promise a safe withdrawal amount.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.calculations import (
    current_age_from_assumptions,
    projected_account_value,
    projected_account_value_at_month,
    projection_monthly_contribution,
    to_float,
    years_to_retirement,
)

ACCESSIBLE = "accessible"
RESTRICTED = "restricted"
LOCKED = "locked"
ACCESSIBLE_CASH = "cash_accessible"
ACCESSIBLE_INVESTED = "invested_accessible"

DEFAULT_ACCESSIBLE_MILESTONES = (20_000, 50_000, 100_000)
WITHDRAWAL_RATES = (
    {"key": "conservative", "label": "Conservative", "rate": 0.030, "note": "Lower income, more margin."},
    {"key": "balanced", "label": "Balanced", "rate": 0.035, "note": "Middle planning estimate."},
    {"key": "higher", "label": "Higher", "rate": 0.040, "note": "More income, less margin."},
)


@dataclass(frozen=True)
class AccessClassification:
    access_type: str
    label: str
    reason: str


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    return any(n in text for n in needles)


def _accessible_subtype(account) -> tuple[str, str, str]:
    wrapper = (account.get("wrapper_type") or "").strip().lower()
    category = (account.get("category") or "").strip().lower()
    combined = f"{wrapper} {category}"

    if _contains_any(
        combined,
        (
            "cash isa",
            "premium bonds",
            "savings",
            "current account",
            "checking",
            "easy access",
            "instant access",
            "cash",
        ),
    ):
        return (
            ACCESSIBLE_CASH,
            "Cash accessible",
            "Usually reachable without needing to sell investments first.",
        )

    return (
        ACCESSIBLE_INVESTED,
        "Invested accessible",
        "Usually reachable before pension age, but still invested so values can move and access may mean selling holdings.",
    )


def classify_account(account) -> AccessClassification:
    """Classify an account by when the money is normally usable.

    Wrapper labels are user-controlled, so this is intentionally conservative
    and transparent rather than magic. Unknown non-pension accounts are treated
    as accessible with a review note; users still see the classification.
    """
    wrapper = (account.get("wrapper_type") or "").strip().lower()
    category = (account.get("category") or "").strip().lower()
    combined = f"{wrapper} {category}"

    if _contains_any(combined, ("sipp", "workplace pension", "pension", "avc")):
        return AccessClassification(LOCKED, "Locked for later", "Pension-style account; normally unavailable until pension access age.")

    if _contains_any(combined, ("lifetime isa", "lisa")):
        return AccessClassification(RESTRICTED, "Restricted / conditional", "Lifetime ISA has age/purpose rules, so it is not treated as simple accessible cash.")

    if _contains_any(combined, ("fixed", "notice")):
        return AccessClassification(RESTRICTED, "Restricted / conditional", "Account label suggests notice/fixed access rather than instant access.")

    if _contains_any(
        combined,
        (
            "stocks & shares isa",
            "stocks and shares isa",
            "cash isa",
            "general investment",
            "gia",
            "premium bonds",
            "savings",
            "current account",
            "checking",
            "cash",
            "investment",
        ),
    ):
        _subtype_key, subtype_label, subtype_reason = _accessible_subtype(account)
        return AccessClassification(ACCESSIBLE, subtype_label, subtype_reason)

    _subtype_key, subtype_label, subtype_reason = _accessible_subtype(account)
    return AccessClassification(ACCESSIBLE, subtype_label, subtype_reason)


def _years_months_label(months: int | None) -> str:
    if months is None:
        return "Not projected"
    years, rem = divmod(int(months), 12)
    if years <= 0:
        return f"{rem}m"
    if rem == 0:
        return f"{years}y"
    return f"{years}y {rem}m"


def _months_to_target(accounts, assumptions, target: float, current_total: float) -> int | None:
    if current_total >= target:
        return 0
    monthly = sum(projection_monthly_contribution(a, assumptions, 0) for a in accounts)
    if monthly <= 0:
        return None

    max_months = 50 * 12
    for month in range(1, max_months + 1):
        projected = sum(projected_account_value_at_month(a, assumptions, month) for a in accounts)
        if projected >= target:
            return month
    return None


def build_accessible_security_summary(accounts, assumptions):
    """Return current/projection totals split by access category."""
    groups = {
        ACCESSIBLE: {"key": ACCESSIBLE, "label": "Accessible", "current": 0.0, "projected": 0.0, "monthly": 0.0, "accounts": []},
        RESTRICTED: {"key": RESTRICTED, "label": "Restricted", "current": 0.0, "projected": 0.0, "monthly": 0.0, "accounts": []},
        LOCKED: {"key": LOCKED, "label": "Locked", "current": 0.0, "projected": 0.0, "monthly": 0.0, "accounts": []},
    }
    accessible_breakdown = {
        ACCESSIBLE_CASH: {"key": ACCESSIBLE_CASH, "label": "Cash accessible", "current": 0.0, "projected": 0.0, "monthly": 0.0, "accounts": []},
        ACCESSIBLE_INVESTED: {"key": ACCESSIBLE_INVESTED, "label": "Invested accessible", "current": 0.0, "projected": 0.0, "monthly": 0.0, "accounts": []},
    }

    for account in accounts:
        classification = classify_account(account)
        key = classification.access_type
        current = to_float(account.get("current_value", 0))
        projected = projected_account_value(account, assumptions) if assumptions else current
        monthly = projection_monthly_contribution(account, assumptions, 0) if assumptions else to_float(account.get("monthly_contribution", 0))
        groups[key]["current"] += current
        groups[key]["projected"] += projected
        groups[key]["monthly"] += monthly
        account_summary = {
            "id": account.get("id"),
            "name": account.get("name") or "Account",
            "wrapper_type": account.get("wrapper_type") or "",
            "current": current,
            "projected": projected,
            "monthly": monthly,
            "access_type": key,
            "access_label": classification.label,
            "access_reason": classification.reason,
        }
        groups[key]["accounts"].append(account_summary)
        if key == ACCESSIBLE:
            subtype_key, subtype_label, _subtype_reason = _accessible_subtype(account)
            accessible_breakdown[subtype_key]["current"] += current
            accessible_breakdown[subtype_key]["projected"] += projected
            accessible_breakdown[subtype_key]["monthly"] += monthly
            accessible_breakdown[subtype_key]["accounts"].append({
                **account_summary,
                "accessible_subtype": subtype_key,
                "accessible_subtype_label": subtype_label,
            })

    total_current = sum(g["current"] for g in groups.values())
    total_projected = sum(g["projected"] for g in groups.values())
    accessible_current = groups[ACCESSIBLE]["current"]
    accessible_accounts = groups[ACCESSIBLE]["accounts"]

    # Calculate overall cash yield metrics
    total_earning_cash = 0.0
    total_annual_interest = 0.0
    for account in accounts:
        category = (account.get("category") or "").strip().lower()
        current_val = to_float(account.get("current_value", 0))
        uninvested_cash = to_float(account.get("uninvested_cash", 0))
        
        # Cash value is either the entire value (for cash accounts) or uninvested_cash (for others)
        if category == "cash":
            cash_val = current_val
        else:
            cash_val = uninvested_cash
            
        rate = account.get("cash_interest_rate")
        if rate is not None:
            rate = to_float(rate)
        else:
            rate = 0.0
            
        if cash_val > 0 and rate > 0:
            total_earning_cash += cash_val
            total_annual_interest += cash_val * rate

    weighted_rate = (total_annual_interest / total_earning_cash) if total_earning_cash > 0 else 0.0
    monthly_interest = total_annual_interest / 12.0

    milestones = []
    for target in DEFAULT_ACCESSIBLE_MILESTONES:
        months = _months_to_target(
            [a for a in accounts if classify_account(a).access_type == ACCESSIBLE],
            assumptions,
            float(target),
            accessible_current,
        )
        milestones.append({
            "target": float(target),
            "remaining": max(float(target) - accessible_current, 0.0),
            "progress": min((accessible_current / float(target)) * 100, 100.0) if target else 0,
            "months": months,
            "duration": _years_months_label(months),
        })
    next_milestone = next((m for m in milestones if m["remaining"] > 0), milestones[-1] if milestones else None)

    return {
        "groups": groups,
        "total_current": total_current,
        "total_projected": total_projected,
        "accessible_current": accessible_current,
        "accessible_projected": groups[ACCESSIBLE]["projected"],
        "locked_current": groups[LOCKED]["current"],
        "restricted_current": groups[RESTRICTED]["current"],
        "accessible_pct": (accessible_current / total_current * 100.0) if total_current else 0.0,
        "locked_pct": (groups[LOCKED]["current"] / total_current * 100.0) if total_current else 0.0,
        "restricted_pct": (groups[RESTRICTED]["current"] / total_current * 100.0) if total_current else 0.0,
        "milestones": milestones,
        "next_milestone": next_milestone,
        "accessible_accounts": accessible_accounts,
        "accessible_breakdown": accessible_breakdown,
        "accessible_cash_current": accessible_breakdown[ACCESSIBLE_CASH]["current"],
        "accessible_invested_current": accessible_breakdown[ACCESSIBLE_INVESTED]["current"],
        "cash_yield_total_earning": total_earning_cash,
        "cash_yield_weighted_rate": weighted_rate * 100.0,
        "cash_yield_annual_interest": total_annual_interest,
        "cash_yield_monthly_interest": monthly_interest,
        "accessible_cash_projected": accessible_breakdown[ACCESSIBLE_CASH]["projected"],
        "accessible_invested_projected": accessible_breakdown[ACCESSIBLE_INVESTED]["projected"],
    }


def build_retirement_income_summary(
    access_summary,
    assumptions,
    *,
    desired_income: float = 0.0,
    state_pension_annual: float = 12_000.0,
    pension_access_age: float = 58.0,
    state_pension_age: float = 68.0,
):
    """Build an optional retirement income analyser from projected pots.

    All figures are deliberately illustrative and before detailed tax modelling.
    ISA-style withdrawals are normally tax-free; pension/State Pension income may
    be taxable, but that deeper modelling is a later slice.
    """
    desired_income = max(to_float(desired_income), 0.0)
    state_pension_annual = max(to_float(state_pension_annual), 0.0)
    pension_access_age = max(to_float(pension_access_age), 0.0)
    state_pension_age = max(to_float(state_pension_age), 0.0)

    current_age = current_age_from_assumptions(assumptions) if assumptions else 0.0
    retirement_age = to_float(assumptions.get("retirement_age", 0)) if assumptions else 0.0
    years_remaining = years_to_retirement(current_age, retirement_age, assumptions) if assumptions else 0.0

    groups = access_summary["groups"]
    accessible_at_retirement = groups[ACCESSIBLE]["projected"]
    restricted_at_retirement = groups[RESTRICTED]["projected"]
    locked_at_retirement = groups[LOCKED]["projected"]
    private_pot_at_retirement = accessible_at_retirement + restricted_at_retirement + locked_at_retirement

    withdrawal_ranges = []
    for item in WITHDRAWAL_RATES:
        annual = private_pot_at_retirement * item["rate"]
        withdrawal_ranges.append({**item, "annual_income": annual, "monthly_income": annual / 12.0})

    balanced_income = next(r["annual_income"] for r in withdrawal_ranges if r["key"] == "balanced")
    income_to_model = desired_income or balanced_income

    bridge_years = max(min(pension_access_age, state_pension_age) - retirement_age, 0.0)
    bridge_need = income_to_model * bridge_years
    bridge_surplus = accessible_at_retirement - bridge_need
    bridge_income_capacity = accessible_at_retirement / bridge_years if bridge_years > 0 else accessible_at_retirement

    private_after_state_needed = max(income_to_model - state_pension_annual, 0.0)
    balanced_rate = 0.035
    required_private_pot_for_desired = (desired_income / balanced_rate) if desired_income else 0.0
    required_private_after_state_pot = (private_after_state_needed / balanced_rate) if desired_income else 0.0

    if bridge_years > 0 and bridge_surplus < 0:
        limiting_factor = "Accessible bridge before pension access"
    elif desired_income and private_pot_at_retirement < required_private_pot_for_desired:
        limiting_factor = "Overall retirement pot"
    else:
        limiting_factor = "No obvious shortfall under these assumptions"

    return {
        "current_age": current_age,
        "retirement_age": retirement_age,
        "years_remaining": years_remaining,
        "pension_access_age": pension_access_age,
        "state_pension_age": state_pension_age,
        "state_pension_annual": state_pension_annual,
        "desired_income": desired_income,
        "private_pot_at_retirement": private_pot_at_retirement,
        "accessible_at_retirement": accessible_at_retirement,
        "restricted_at_retirement": restricted_at_retirement,
        "locked_at_retirement": locked_at_retirement,
        "withdrawal_ranges": withdrawal_ranges,
        "balanced_income": balanced_income,
        "income_to_model": income_to_model,
        "bridge_years": bridge_years,
        "bridge_need": bridge_need,
        "bridge_surplus": bridge_surplus,
        "bridge_income_capacity": bridge_income_capacity,
        "private_after_state_needed": private_after_state_needed,
        "required_private_pot_for_desired": required_private_pot_for_desired,
        "required_private_after_state_pot": required_private_after_state_pot,
        "limiting_factor": limiting_factor,
        "uses_goal_mode": desired_income > 0,
    }
