"""One-off contributions in the projection engine.

Before this, a lump sum only touched the allowance counter. The projection engine
saw monthly contributions and nothing else, so:

- a house deposit built from annual LISA top-ups had no monthly contribution at all,
  and `project_goal` returned None — no estimate, no ETA
- the 25% government bonus appeared in no projected value anywhere

These tests pin the dated-inflow model: principal lands on its month, the bonus lands
two months later, and both move the projection.
"""
from datetime import date


def _lisa(monthly=0, value=4000, start_month="2026-11", inflows=None):
    return {
        "id": 1,
        "name": "My Lifetime ISA",
        "wrapper_type": "Lifetime ISA",
        "category": "Investment",
        "current_value": value,
        "monthly_contribution": monthly,
        "monthly_cash_park": 0,
        "growth_mode": "default",
        "growth_rate_override": None,
        "_projection_start_month": start_month,
        "_one_off_inflows": inflows or [],
    }


def _assumptions():
    return {
        "date_of_birth": "1983-05-25",
        "retirement_age": 62,
        "annual_growth_rate": 0.0,
        "salary_day": 25,
    }


def test_goal_projects_lump_sums_when_monthly_contribution_is_zero():
    """The exact blocker: a LISA funded by top-ups could not be projected at all."""
    from app.services.goal_projection import project_goal

    account = _lisa(inflows=[{"month_key": "2026-12", "amount": 5000.0}])
    result = project_goal([account], 9000, _assumptions(), today=date(2026, 11, 1))

    assert result is not None, "a lump-sum funded goal must be projectable"
    assert result["reached"] is False
    assert result["total_months"] == 2      # 4,000 now + 5,000 in December


def test_goal_still_returns_none_when_there_is_no_money_moving():
    """No monthly and no inflows means there is genuinely nothing to project."""
    from app.services.goal_projection import project_goal

    assert project_goal([_lisa()], 9000, _assumptions(), today=date(2026, 11, 1)) is None


def test_goal_already_reached_is_reported_as_reached():
    from app.services.goal_projection import project_goal

    assert project_goal([_lisa()], 1000, _assumptions(), today=date(2026, 11, 1)) == {"reached": True}


def test_projection_includes_the_bonus_at_its_arrival_month():
    """Principal lands in the first projected month, the bonus two months later.

    Note the engine convention: `at_month(0)` is today's value before any
    contribution lands; each iteration grows then adds, so a contribution dated in
    the start month appears at `at_month(1)`. Same rule as monthly contributions.
    """
    from app.calculations import projected_account_value_at_month

    inflows = [
        {"month_key": "2026-11", "amount": 4000.0, "kind": "contribution"},
        {"month_key": "2027-01", "amount": 1000.0, "kind": "bonus"},
    ]
    account = _lisa(value=0, inflows=inflows)
    assumptions = _assumptions()

    assert projected_account_value_at_month(account, assumptions, 0) == 0.0     # nothing yet
    assert projected_account_value_at_month(account, assumptions, 1) == 4000.0  # principal
    assert projected_account_value_at_month(account, assumptions, 2) == 4000.0  # bonus not yet
    assert projected_account_value_at_month(account, assumptions, 3) == 5000.0  # bonus arrives


def test_projection_without_inflows_is_unchanged():
    from app.calculations import projected_account_value_at_month

    account = _lisa(value=4000, inflows=[])
    assert projected_account_value_at_month(account, _assumptions(), 6) == 4000.0


# ── Building the inflows from real contribitions ────────────────────────────

def _account_payload(name, wrapper):
    return {
        "id": None, "name": name, "provider": "Provider", "wrapper_type": wrapper,
        "category": "Investment", "tags": "", "current_value": 0,
        "monthly_contribution": 0, "monthly_cash_park": 0,
        "pension_contribution_day": 0, "goal_value": None, "valuation_mode": "manual",
        "growth_mode": "default", "growth_rate_override": None, "owner": "Janusz",
        "is_active": 1, "notes": "", "last_updated": "2026-05-29",
        "employer_contribution": 0, "contribution_method": "standard",
        "annual_fee_pct": 0, "platform_fee_pct": 0, "platform_fee_flat": 0,
        "platform_fee_cap": 0, "fund_fee_pct": 0, "contribution_fee_pct": 0,
        "uninvested_cash": 0, "cash_interest_rate": 0, "interest_payment_day": 0,
    }


def test_inflows_are_built_with_principal_and_dated_bonus(app, make_user):
    from app.models import create_account, add_isa_contribution, fetch_isa_one_off_inflows

    uid, _, _ = make_user(username="inflow-build", password="password123")
    with app.app_context():
        account_id = create_account(_account_payload("My Lifetime ISA", "Lifetime ISA"), uid)
        add_isa_contribution(uid, account_id, 4000, "2026-06-01")

        inflows = fetch_isa_one_off_inflows(uid)

    principal = [i for i in inflows if i["kind"] == "contribution"]
    bonus = [i for i in inflows if i["kind"] == "bonus"]

    assert len(principal) == 1 and principal[0]["month_key"] == "2026-06"
    assert principal[0]["amount"] == 4000.0

    assert len(bonus) == 1
    assert bonus[0]["month_key"] == "2026-08"      # six weeks later
    assert bonus[0]["amount"] == 1000.0


def test_inflows_cap_the_bonus_per_tax_year_not_across_years(app, make_user):
    """£4,000 in one tax year and £4,000 in the next earns £1,000 twice."""
    from app.models import create_account, add_isa_contribution, fetch_isa_one_off_inflows

    uid, _, _ = make_user(username="inflow-years", password="password123")
    with app.app_context():
        account_id = create_account(_account_payload("My Lifetime ISA", "Lifetime ISA"), uid)
        add_isa_contribution(uid, account_id, 4000, "2026-06-01")   # tax year 2026/27
        add_isa_contribution(uid, account_id, 4000, "2027-06-01")   # tax year 2027/28

        bonus_total = sum(i["amount"] for i in fetch_isa_one_off_inflows(uid) if i["kind"] == "bonus")

    assert bonus_total == 2000.0, "each tax year gets its own £1,000 bonus"


def test_non_lisa_contributions_get_no_bonus_inflow(app, make_user):
    from app.models import create_account, add_isa_contribution, fetch_isa_one_off_inflows

    uid, _, _ = make_user(username="inflow-isa", password="password123")
    with app.app_context():
        account_id = create_account(_account_payload("My S&S ISA", "Stocks & Shares ISA"), uid)
        add_isa_contribution(uid, account_id, 5000, "2026-06-01")

        inflows = fetch_isa_one_off_inflows(uid)

    assert [i["kind"] for i in inflows] == ["contribution"]


def test_ticking_bonus_received_stops_it_being_projected_again(app, make_user):
    """Once the bonus lands it is inside the balance — projecting it again doubles it."""
    from app.models import (
        create_account, add_isa_contribution, fetch_isa_one_off_inflows,
        fetch_isa_contributions, set_isa_bonus_received,
    )

    uid, _, _ = make_user(username="inflow-tick", password="password123")
    with app.app_context():
        account_id = create_account(_account_payload("My Lifetime ISA", "Lifetime ISA"), uid)
        add_isa_contribution(uid, account_id, 4000, "2026-06-01")

        before = fetch_isa_one_off_inflows(uid)
        contribution_id = fetch_isa_contributions(uid, "2026-04-06", "2027-04-05")[0]["id"]
        set_isa_bonus_received(contribution_id, uid, True)
        after = fetch_isa_one_off_inflows(uid)

    assert [i["kind"] for i in before] == ["contribution", "bonus"]
    assert [i["kind"] for i in after] == ["contribution"], "a received bonus must not project again"
