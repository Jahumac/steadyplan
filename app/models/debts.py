"""Debt tracker model — CRUD and calculations for the debts table."""
import calendar
import math
from datetime import date, datetime

from ._conn import get_connection


# ── CRUD ─────────────────────────────────────────────────────────────────────

def fetch_all_debts(user_id):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM debts WHERE user_id = ? AND is_active = 1 ORDER BY created_at",
            (user_id,),
        ).fetchall()
    return rows


def fetch_debt(debt_id, user_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM debts WHERE id = ? AND user_id = ?",
            (debt_id, user_id),
        ).fetchone()


def create_debt(payload, user_id):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO debts (user_id, name, original_amount, current_balance,
                               monthly_payment, apr, notes, start_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                payload["name"],
                payload.get("original_amount", 0),
                payload.get("current_balance", 0),
                payload["monthly_payment"],
                payload.get("apr", 0),
                payload.get("notes", ""),
                payload.get("start_date") or None,
            ),
        )
        conn.commit()


def update_debt(debt_id, payload, user_id):
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE debts
            SET name = ?, original_amount = ?, current_balance = ?,
                monthly_payment = ?, apr = ?, notes = ?, start_date = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                payload["name"],
                payload.get("original_amount", 0),
                payload.get("current_balance", 0),
                payload["monthly_payment"],
                payload.get("apr", 0),
                payload.get("notes", ""),
                payload.get("start_date") or None,
                debt_id,
                user_id,
            ),
        )
        conn.commit()


def delete_debt(debt_id, user_id):
    with get_connection() as conn:
        conn.execute(
            "UPDATE debts SET is_active = 0 WHERE id = ? AND user_id = ?",
            (debt_id, user_id),
        )
        conn.commit()


# ── Calculations ─────────────────────────────────────────────────────────────

def debt_months_remaining(balance, monthly_payment, apr):
    """Number of months to pay off the debt. Returns None if payment can't cover interest."""
    if balance <= 0:
        return 0
    if monthly_payment <= 0:
        return None
    r = apr / 100.0 / 12.0
    if r == 0:
        return math.ceil(balance / monthly_payment)
    monthly_interest = balance * r
    if monthly_payment <= monthly_interest:
        return None  # payment too low to ever pay off
    return math.ceil(-math.log(1 - balance * r / monthly_payment) / math.log(1 + r))


def debt_total_interest(balance, monthly_payment, apr, months=None):
    """Total interest paid over the life of the debt.

    Uses the amortisation schedule rather than ``monthly_payment * months`` so
    the final partial payment is handled accurately.
    """
    if balance <= 0:
        return 0.0
    if monthly_payment <= 0:
        return None
    if apr == 0:
        return 0.0
    if months is None:
        months = debt_months_remaining(balance, monthly_payment, apr)
    if months is None:
        return None
    schedule = amortisation_schedule(balance, apr, monthly_payment, max_months=months)
    return round(sum(row["interest"] for row in schedule), 2)


def debt_payoff_date(months):
    """Calendar date when the debt will be cleared (from today)."""
    if months is None:
        return None
    today = date.today()
    total_months = today.month - 1 + months
    year = today.year + total_months // 12
    month = total_months % 12 + 1
    return date(year, month, 1)


def debt_overpayment_scenario(
    balance,
    monthly_payment,
    apr,
    extra_monthly=0,
    one_off_overpayment=0,
):
    """Compare the current debt plan with an overpayment scenario.

    ``extra_monthly`` increases every future regular payment. ``one_off`` is
    applied immediately to principal before the new schedule is calculated.
    Interest is calculated from amortisation schedules so final partial payments
    are handled accurately.
    """
    balance = float(balance or 0)
    monthly_payment = float(monthly_payment or 0)
    apr = float(apr or 0)
    extra_monthly = max(float(extra_monthly or 0), 0.0)
    one_off_overpayment = max(float(one_off_overpayment or 0), 0.0)

    baseline_months = debt_months_remaining(balance, monthly_payment, apr)
    baseline_interest = debt_total_interest(balance, monthly_payment, apr, baseline_months)

    scenario_balance = max(balance - one_off_overpayment, 0.0)
    new_monthly_payment = monthly_payment + extra_monthly
    new_months = debt_months_remaining(scenario_balance, new_monthly_payment, apr)
    new_interest = debt_total_interest(scenario_balance, new_monthly_payment, apr, new_months)

    if baseline_months is None or new_months is None or baseline_interest is None or new_interest is None:
        months_saved = None
        interest_saved = None
    else:
        months_saved = max(baseline_months - new_months, 0)
        interest_saved = max(round(baseline_interest - new_interest, 2), 0.0)

    return {
        "balance": round(balance, 2),
        "scenario_balance": round(scenario_balance, 2),
        "baseline_months": baseline_months,
        "new_months": new_months,
        "months_saved": months_saved,
        "baseline_interest": baseline_interest,
        "new_interest": new_interest,
        "interest_saved": interest_saved,
        "monthly_payment": round(monthly_payment, 2),
        "extra_monthly": round(extra_monthly, 2),
        "new_monthly_payment": round(new_monthly_payment, 2),
        "one_off_overpayment": round(min(one_off_overpayment, balance), 2),
        "baseline_payoff_date": debt_payoff_date(baseline_months),
        "new_payoff_date": debt_payoff_date(new_months),
    }


def debt_guidance_exclusion_reason(debt):
    """Return a user-facing reason why a debt should be excluded from payoff guidance."""
    balance = float(debt.get("current_balance") or 0)
    monthly_payment = float(debt.get("monthly_payment") or 0)
    apr = debt.get("apr")

    if balance <= 0:
        return "Balance already cleared"
    if monthly_payment <= 0:
        return "No monthly payment set"
    if apr is None:
        return "APR is missing"

    apr = float(apr)
    if apr < 0:
        return "APR must be zero or higher"

    monthly_interest = balance * (apr / 100.0 / 12.0)
    if monthly_payment <= monthly_interest and balance > 0:
        return "Current payment does not cover interest"
    return None



def debt_is_payoff_guidance_eligible(debt):
    return debt_guidance_exclusion_reason(debt) is None



def _debt_sort_order(debt):
    return debt.get("created_order", debt.get("id", 0))



def rank_debts_avalanche(debts):
    return sorted(
        debts,
        key=lambda debt: (-float(debt.get("apr") or 0), -float(debt.get("current_balance") or 0), _debt_sort_order(debt)),
    )



def rank_debts_snowball(debts):
    return sorted(
        debts,
        key=lambda debt: (float(debt.get("current_balance") or 0), -float(debt.get("apr") or 0), _debt_sort_order(debt)),
    )



def _split_guidance_debts(debts):
    eligible = []
    excluded = []
    for debt in debts:
        reason = debt_guidance_exclusion_reason(debt)
        if reason:
            excluded.append({"id": debt.get("id"), "name": debt.get("name"), "reason": reason})
        else:
            eligible.append(debt)
    return eligible, excluded



def _rank_debts_for_strategy(debts, strategy):
    if strategy == "avalanche":
        return rank_debts_avalanche(debts)
    if strategy == "snowball":
        return rank_debts_snowball(debts)
    raise ValueError(f"Unknown debt payoff strategy: {strategy}")



def simulate_debt_payoff_strategy(debts, extra_monthly=0, strategy="avalanche"):
    extra_monthly = max(float(extra_monthly or 0), 0.0)
    eligible, excluded = _split_guidance_debts(debts)
    ranked = _rank_debts_for_strategy(eligible, strategy)

    if not ranked:
        return {
            "strategy": strategy,
            "extra_monthly": round(extra_monthly, 2),
            "debt_order": [],
            "payoff_steps": [],
            "total_months": None,
            "total_interest": None,
            "included_debt_count": 0,
            "excluded_debt_count": len(excluded),
            "excluded_debts": excluded,
        }

    working = []
    rolling_extra = extra_monthly
    payoff_steps = []
    for debt in ranked:
        minimum_payment = round(float(debt.get("monthly_payment") or 0), 2)
        working.append(
            {
                "id": debt.get("id"),
                "name": debt.get("name"),
                "balance": round(float(debt.get("current_balance") or 0), 2),
                "apr": float(debt.get("apr") or 0),
                "minimum_payment": minimum_payment,
            }
        )
        payoff_steps.append(
            {
                "id": debt.get("id"),
                "name": debt.get("name"),
                "minimum_payment": minimum_payment,
                "rolled_monthly_payment": round(minimum_payment + rolling_extra, 2),
            }
        )
        rolling_extra += minimum_payment

    total_interest = 0.0
    total_months = 0
    active_ids = {debt["id"] for debt in working}
    target_ids = [debt["id"] for debt in ranked]
    rolling_extra = extra_monthly
    target_index = 0

    while active_ids:
        total_months += 1
        for debt in working:
            if debt["id"] not in active_ids:
                continue
            interest = round(debt["balance"] * (debt["apr"] / 100.0 / 12.0), 2)
            debt["balance"] = round(debt["balance"] + interest, 2)
            total_interest = round(total_interest + interest, 2)

        while target_index < len(target_ids) and target_ids[target_index] not in active_ids:
            target_index += 1
        current_target_id = target_ids[target_index] if target_index < len(target_ids) else None

        for debt in working:
            if debt["id"] not in active_ids:
                continue
            payment = debt["minimum_payment"]
            if debt["id"] == current_target_id:
                payment += rolling_extra
            payment = min(round(payment, 2), debt["balance"])
            debt["balance"] = round(max(debt["balance"] - payment, 0.0), 2)

        cleared_this_month = []
        for debt in working:
            if debt["id"] in active_ids and debt["balance"] <= 0:
                active_ids.remove(debt["id"])
                cleared_this_month.append(debt)

        for debt in cleared_this_month:
            if debt["id"] == current_target_id:
                rolling_extra += debt["minimum_payment"]

        if total_months > 1200:
            raise RuntimeError("Debt payoff simulation exceeded 1200 months")

    return {
        "strategy": strategy,
        "extra_monthly": round(extra_monthly, 2),
        "debt_order": [debt["name"] for debt in ranked],
        "payoff_steps": payoff_steps,
        "total_months": total_months,
        "total_interest": round(total_interest, 2),
        "included_debt_count": len(ranked),
        "excluded_debt_count": len(excluded),
        "excluded_debts": excluded,
    }



def compare_debt_payoff_strategies(debts, extra_monthly=0):
    avalanche = simulate_debt_payoff_strategy(debts, extra_monthly=extra_monthly, strategy="avalanche")
    snowball = simulate_debt_payoff_strategy(debts, extra_monthly=extra_monthly, strategy="snowball")
    return {
        "extra_monthly": round(max(float(extra_monthly or 0), 0.0), 2),
        "included_debt_count": avalanche["included_debt_count"],
        "excluded_debt_count": avalanche["excluded_debt_count"],
        "excluded_debts": avalanche["excluded_debts"],
        "avalanche": avalanche,
        "snowball": snowball,
    }



def _add_months(d, n):
    """Add n months to a date, clamping to the last day of the target month."""
    month = d.month - 1 + n
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def schedule_anchor(start_date_str, offset_months=0):
    """Calendar date for the first row of an amortisation schedule.

    Parses an ISO start_date and optionally shifts forward by N months (used to
    skip past payments already made). Returns None if start_date_str is missing
    or malformed.
    """
    if not start_date_str:
        return None
    try:
        start = date.fromisoformat(start_date_str)
    except (ValueError, TypeError):
        return None
    return _add_months(start, offset_months) if offset_months else start


def amortisation_schedule(balance, apr, monthly_payment, max_months=360, start_date=None):
    """Return a list of monthly rows: month, payment, interest, principal, balance.

    If start_date (a date object) is provided, each row also gets a 'date' field
    with the actual calendar date of that payment.
    """
    r = apr / 100.0 / 12.0
    rows = []
    for i in range(1, max_months + 1):
        if balance <= 0:
            break
        interest = round(balance * r, 2)
        # Final payment may be smaller
        payment = min(monthly_payment, balance + interest)
        principal = round(payment - interest, 2)
        balance = max(round(balance - principal, 2), 0)
        row = {
            "month": i,
            "payment": payment,
            "interest": interest,
            "principal": principal,
            "balance": balance,
        }
        if start_date:
            row["date"] = _add_months(start_date, i - 1)
        rows.append(row)
        if monthly_payment <= interest and i > 1:
            break  # can't pay off
    return rows


def _auto_balance_from_schedule(original_amount, apr, monthly_payment, start_date_str):
    """Calculate current balance from amortisation schedule based on first payment date.
    Returns (balance, payments_made) or (None, 0) if start_date not set.

    Payment count logic: a payment is counted for a given month only if today's
    date has reached or passed the payment day of that month. This prevents
    counting next month's payment as already made when it hasn't gone out yet.
    For example, start_date=2026-03-31, today=2026-04-19 → 1 payment made
    (April's payment is due on the 30th, not yet reached).
    """
    if not start_date_str or not original_amount:
        return None, 0
    try:
        start = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        today = date.today()
        if today < start:
            return float(original_amount), 0
        # Whole months elapsed since start
        months_elapsed = (today.year - start.year) * 12 + (today.month - start.month)
        # Check whether today has reached the payment day in the current month.
        # Handle end-of-month: if start_date is the 31st and current month only
        # has 30 days, the payment falls on the last day of that month.
        days_in_current_month = calendar.monthrange(today.year, today.month)[1]
        payment_day_this_month = min(start.day, days_in_current_month)
        if today.day >= payment_day_this_month:
            n = months_elapsed + 1
        else:
            n = months_elapsed
        if n <= 0:
            return float(original_amount), 0
        r = apr / 100.0 / 12.0
        balance = float(original_amount)
        for _ in range(n):
            if balance <= 0:
                break
            interest = balance * r
            principal = monthly_payment - interest
            if principal <= 0:
                break
            balance = max(balance - principal, 0)
        return round(balance, 2), n
    except (ValueError, TypeError):
        return None, 0


def build_debt_card(debt):
    """Attach calculated fields to a debt row dict."""
    original = float(debt["original_amount"] or 0)
    payment = float(debt["monthly_payment"] or 0)
    apr = float(debt["apr"] or 0)
    start_date = debt["start_date"] if "start_date" in debt.keys() else None

    # Auto-calculate balance from schedule if start_date is set
    auto_balance, payments_made = _auto_balance_from_schedule(original, apr, payment, start_date)
    if auto_balance is not None:
        balance = auto_balance
        auto_tracked = True
    else:
        balance = float(debt["current_balance"] or 0)
        payments_made = 0
        auto_tracked = False

    months = debt_months_remaining(balance, payment, apr)
    interest = debt_total_interest(balance, payment, apr, months)
    payoff = debt_payoff_date(months)
    paid_off_pct = ((original - balance) / original * 100) if original > 0 else 0
    overpayment_examples = []
    if balance > 0 and payment > 0 and months is not None:
        for extra in (50, 100, 200):
            scenario = debt_overpayment_scenario(balance, payment, apr, extra_monthly=extra)
            if scenario["months_saved"] and scenario["interest_saved"]:
                overpayment_examples.append(scenario)

    return {
        "id": debt["id"],
        "name": debt["name"],
        "original_amount": original,
        "current_balance": balance,
        "stored_balance": float(debt["current_balance"] or 0),
        "monthly_payment": payment,
        "apr": apr,
        "notes": debt["notes"] or "",
        "start_date": start_date,
        "auto_tracked": auto_tracked,
        "payments_made": payments_made,
        "months_remaining": months,
        "total_interest": interest,
        "payoff_date": payoff,
        "paid_off_pct": max(0, min(100, paid_off_pct)),
        "total_cost": (balance + interest) if interest is not None else None,
        "monthly_interest": balance * (apr / 100 / 12) if apr > 0 else 0,
        "overpayment_examples": overpayment_examples,
    }
