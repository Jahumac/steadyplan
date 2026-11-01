from datetime import date

from app.calculations import (
    _safe_get,
    account_growth_rate,
    add_months_to_key,
    current_age_from_assumptions,
    projection_monthly_contribution,
    projection_start_month_key,
    to_float,
)
from app.models.accounts import PREMIUM_BONDS_MAX_BALANCE, is_premium_bonds_account


def project_goal(included_accounts, target, assumptions, today=None):
    """Estimate how many months until the included accounts reach ``target``.

    Uses the same engine as the Projections page — effective monthly
    contributions (including tax relief, employer match, and LISA bonus)
    and per-account growth rates net of fees. Each account is projected
    independently, then summed.
    """
    target_f = float(target)
    current_total = sum(to_float(a["current_value"]) for a in included_accounts)

    if current_total >= target_f:
        return {"reached": True}

    total_monthly = sum(projection_monthly_contribution(a, assumptions, 0) for a in included_accounts)
    # A goal funded purely by lump sums is still projectable — a house deposit built
    # from annual LISA top-ups has no monthly contribution at all.
    has_one_off = any(_safe_get(a, "_one_off_inflows", None) for a in included_accounts)
    if total_monthly <= 0 and not has_one_off:
        return None

    MAX_MONTHS = 50 * 12
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    current_age = current_age_from_assumptions(assumptions)
    today = today or date.today()
    default_start_month = projection_start_month_key(assumptions, today)
    account_states = [
        {
            "account": account,
            "value": to_float(account["current_value"]),
            "monthly_rate": account_growth_rate(account, assumptions) / 12.0,
            "is_lisa": account["wrapper_type"] == "Lifetime ISA",
            "is_premium_bonds": is_premium_bonds_account(account),
            "start_month": _safe_get(account, "_projection_start_month", None) or default_start_month,
            "inflows": _safe_get(account, "_one_off_inflows", None) or [],
        }
        for account in included_accounts
    ]

    for month in range(1, MAX_MONTHS + 1):
        projected = 0.0
        month_index = month - 1
        for state in account_states:
            state["value"] *= (1 + state["monthly_rate"])
            if not state["is_lisa"] or (current_age + month_index / 12.0) < 50:
                state["value"] += projection_monthly_contribution(state["account"], assumptions, month_index)
            # One-off lump sums and their expected LISA bonus land on set months.
            if state["inflows"] and state["start_month"]:
                month_key = add_months_to_key(state["start_month"], month_index)
                for inflow in state["inflows"]:
                    if _safe_get(inflow, "month_key") == month_key:
                        state["value"] += to_float(_safe_get(inflow, "amount", 0))
            if state["is_premium_bonds"] and state["value"] > PREMIUM_BONDS_MAX_BALANCE:
                state["value"] = PREMIUM_BONDS_MAX_BALANCE
            projected += state["value"]
        if projected >= target_f:
            years, rem_months = divmod(month, 12)
            eta_month_num = today.month + month
            eta_year = today.year + (eta_month_num - 1) // 12
            eta_month_num = (eta_month_num - 1) % 12 + 1
            eta_label = f"{month_names[eta_month_num - 1]} {eta_year}"

            if years == 0:
                duration = f"{rem_months}m"
            elif rem_months == 0:
                duration = f"{years}y"
            else:
                duration = f"{years}y {rem_months}m"

            return {
                "reached": False,
                "total_months": month,
                "duration": duration,
                "eta_label": eta_label,
            }

    return {"reached": False, "total_months": None, "duration": ">50y", "eta_label": None}
