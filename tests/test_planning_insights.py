from datetime import date

from tests.path_helpers import STATIC_ROOT

from app.models import create_account, fetch_assumptions, update_assumptions
from app.services.planning_insights import (
    ACCESSIBLE,
    LOCKED,
    RESTRICTED,
    build_accessible_security_summary,
    build_retirement_income_summary,
    classify_account,
)


def _account(name, wrapper_type, value=0, monthly=0):
    return {
        "id": None,
        "name": name,
        "provider": "Provider",
        "wrapper_type": wrapper_type,
        "category": "Investment",
        "tags": "",
        "current_value": value,
        "monthly_contribution": monthly,
        "pension_contribution_day": 0,
        "goal_value": None,
        "valuation_mode": "manual",
        "growth_mode": "default",
        "growth_rate_override": None,
        "owner": "Janusz",
        "is_active": 1,
        "notes": "",
        "last_updated": "2026-05-25",
        "employer_contribution": 0,
        "contribution_method": "standard",
        "annual_fee_pct": 0,
        "platform_fee_pct": 0,
        "platform_fee_flat": 0,
        "platform_fee_cap": 0,
        "fund_fee_pct": 0,
        "contribution_fee_pct": 0,
        "uninvested_cash": 0,
        "cash_interest_rate": 0,
        "interest_payment_day": 0,
        "_contribution_overrides": [],
        "_projection_start_month": "2026-05",
    }


def test_classify_accounts_by_access_type():
    isa = classify_account(_account("ISA", "Stocks & Shares ISA"))
    cash_isa = classify_account(_account("Cash ISA", "Cash ISA"))

    assert isa.access_type == ACCESSIBLE
    assert isa.label == "Invested accessible"
    assert cash_isa.access_type == ACCESSIBLE
    assert cash_isa.label == "Cash accessible"
    assert classify_account(_account("LISA", "Lifetime ISA")).access_type == RESTRICTED
    assert classify_account(_account("SIPP", "SIPP")).access_type == LOCKED
    assert classify_account(_account("Work", "Workplace Pension")).access_type == LOCKED


def test_accessible_summary_splits_current_money_and_milestones(app, make_user):
    uid, _username, _password = make_user()
    with app.app_context():
        assumptions = fetch_assumptions(uid)
        update_assumptions({
            "annual_growth_rate": 0.0,
            "retirement_age": 60,
            "date_of_birth": "1986-01-01",
            "retirement_goal_value": 500000,
            "isa_allowance": 20000,
            "lisa_allowance": 4000,
            "dividend_allowance": 500,
            "annual_income": 0,
            "pension_annual_allowance": 60000,
            "mpaa_enabled": 0,
            "mpaa_allowance": 10000,
            "target_dev_pct": 0.9,
            "target_em_pct": 0.1,
            "emergency_fund_target": 3000,
            "dashboard_name": "SteadyPlan",
            "salary_day": 0,
            "update_day": 0,
            "retirement_date_mode": "birthday",
            "tax_band": "basic",
            "auto_update_prices": 1,
            "update_time_morning": "08:30",
            "update_time_evening": "18:00",
            "benchmark_rate": None,
            "updated_at": date.today().isoformat(),
        }, uid)
        assumptions = fetch_assumptions(uid)
        accounts = [
            _account("S&S ISA", "Stocks & Shares ISA", 9500, 1000),
            _account("Cash ISA", "Cash ISA", 1500, 0),
            _account("SIPP", "SIPP", 50000, 200),
            _account("LISA", "Lifetime ISA", 500, 0),
        ]
        summary = build_accessible_security_summary(accounts, assumptions)

    assert summary["accessible_current"] == 11000
    assert summary["locked_current"] == 50000
    assert summary["restricted_current"] == 500
    assert summary["accessible_cash_current"] == 1500
    assert summary["accessible_invested_current"] == 9500
    assert summary["milestones"][0]["target"] == 20000
    assert summary["milestones"][0]["months"] == 9
    assert summary["next_milestone"]["target"] == 20000


def test_retirement_income_summary_has_withdrawal_ranges_and_bridge_signal(app, make_user):
    uid, _username, _password = make_user()
    with app.app_context():
        assumptions = fetch_assumptions(uid)
        accounts = [
            _account("ISA", "Stocks & Shares ISA", 20000, 0),
            _account("Pension", "SIPP", 180000, 0),
        ]
        access = build_accessible_security_summary(accounts, assumptions)
        income = build_retirement_income_summary(
            access,
            assumptions,
            desired_income=24000,
            state_pension_annual=12000,
            pension_access_age=58,
            state_pension_age=68,
        )

    balanced = next(row for row in income["withdrawal_ranges"] if row["key"] == "balanced")
    assert balanced["annual_income"] > 7000
    assert round(balanced["annual_income"]) == round(income["private_pot_at_retirement"] * 0.035)
    assert income["private_after_state_needed"] == 12000
    assert income["required_private_after_state_pot"] > 300000


def test_planning_page_renders_for_logged_in_user(app, client, make_user):
    uid, username, password = make_user()
    with app.app_context():
        assumptions = fetch_assumptions(uid)
        update_assumptions({
            **dict(assumptions),
            "retirement_age": 55,
            "date_of_birth": "1990-01-01",
        }, uid)
        create_account(_account("ISA", "Stocks & Shares ISA", 10000, 500), uid)
        create_account(_account("Pension", "SIPP", 50000, 100), uid)

    client.post("/login", data={"username": username, "password": password})
    response = client.get("/planning/?desired_income=24000&pension_access_age=60")

    assert response.status_code == 200
    assert b'budget-year-strip month-strip-global month-strip-mobile-hidden' in response.data
    assert b"Cash-accessible, invested-accessible, restricted, and locked-for-later money" in response.data
    assert b"Accessible now, restricted, and locked" not in response.data
    assert b"Accessible vs locked" not in response.data
    assert b"See what is cash-accessible now, what invested money is still reachable, what comes with conditions, what stays locked for later, and what your current plan might support." in response.data
    assert b"See what you can usually reach now, what comes with conditions, what stays locked for later, and what your current plan might support." not in response.data
    assert b"Target retirement income/year" in response.data
    assert b"Accessible now milestones" in response.data
    assert b"Accessible security milestones" not in response.data
    assert b">Accessible now</h2>" in response.data
    assert b"Money normally usable before pension age: ISA, cash, taxable accounts, Premium Bonds and similar accounts." in response.data
    assert b"Money normally usable before pension age: ISA, cash, GIA, Premium Bonds and similar accounts." not in response.data
    assert b"Cash accessible:" in response.data
    assert b"Invested accessible:" in response.data
    assert b"Cash accessible</span><strong>0 accounts" in response.data
    assert b"Invested accessible</span><strong>1 accounts" in response.data
    assert b"Locked for later</span><strong>1 accounts" in response.data
    assert b"<span>Locked</span><strong>1 accounts" not in response.data
    assert b"Timing estimate:" in response.data
    assert b"Estimated:" not in response.data
    assert b"View account details" in response.data
    assert b"perfect retirement salary" not in response.data
    assert b"Weakest link" in response.data
    assert b"Balanced illustration:" in response.data
    assert b" per month. For planning only, not guaranteed income." in response.data
    assert b"/mo. For planning only, not guaranteed income." not in response.data
    assert b"For planning only, not guaranteed income." in response.data
    assert b"Illustration only, not guaranteed income." not in response.data
    assert b"Illustrative estimate, not guaranteed income." not in response.data
    assert b"This page is for planning, not guaranteed safe withdrawal advice." in response.data
    assert b"planning illustrations, not guaranteed safe withdrawal advice." not in response.data
    assert b"planning scenarios, not guaranteed safe withdrawal advice." not in response.data
    assert b"Balanced estimate:" not in response.data
    assert b"Scenario estimate, not guaranteed income." not in response.data
    assert response.data.count(b"State Pension/year (illustrative)") == 2
    assert b"State Pension/year estimate" not in response.data
    assert b"State Pension assumption" in response.data
    assert response.data.count(b"Edit scenario estimate assumptions") == 2
    assert response.data.count(b'/settings/?mode=edit&amp;focus=scenario_estimate_assumptions') == 2
    assert b'href="/settings/?mode=edit"' not in response.data
    assert b"Edit growth/retirement age" not in response.data
    assert b"Adjust scenario estimate assumptions" in response.data
    assert b"Adjust assumptions" not in response.data
    assert b"Private pot scenario estimate at retirement" in response.data
    assert b"Private pot estimate at retirement" not in response.data
    assert b"Projected private pot" not in response.data
    assert b"Current totals use saved balances. Scenario estimates use your assumptions and are not guarantees." in response.data
    assert b"Scenario estimate at age 55 under current balances, contributions and growth assumptions. For planning only, not a guarantee." not in response.data
    assert b"Estimate at age 55 under current balances, contributions and growth assumptions." not in response.data
    assert b"Projected at age 55 under current balances, contributions and growth assumptions." not in response.data
    assert b"Private pot scenario estimate at age 55:" in response.data
    assert b"Private pot estimate at age 55:" not in response.data
    assert b"Projected private pot at age 55:" not in response.data
    assert response.data.count(b"Scenario estimate at 55:") >= 2
    assert b"Estimate at 55:" not in response.data
    assert b"Projected at 55:" not in response.data

    css = STATIC_ROOT.joinpath("css/styles.css").read_text()
    assert ".planning-hero-strip {" in css
    assert css.count("grid-template-columns: repeat(2, minmax(0, 1fr));") >= 3
    assert "@media (max-width: 520px) {" in css
    assert ".planning-hero-caveat {" in css
    assert "display: none;" in css


def test_planning_page_no_goal_mode_uses_plan_wording(app, client, make_user):
    uid, username, password = make_user()
    with app.app_context():
        assumptions = fetch_assumptions(uid)
        update_assumptions({
            **dict(assumptions),
            "retirement_age": 55,
            "date_of_birth": "1990-01-01",
        }, uid)
        create_account(_account("ISA", "Stocks & Shares ISA", 10000, 500), uid)
        create_account(_account("Pension", "SIPP", 50000, 100), uid)

    client.post("/login", data={"username": username, "password": password})
    response = client.get("/planning/?pension_access_age=60")

    assert response.status_code == 200
    html = response.data.decode("utf-8", errors="ignore")
    assert "using the balanced illustration as the income guide" in html
    assert "Private pot scenario estimate at retirement" in html
    assert "Private pot estimate at retirement" not in html
    assert "Projected private pot" not in html
    assert "Current totals use saved balances. Scenario estimates use your assumptions and are not guarantees." in html
    assert "Scenario estimate at age 55 under current balances, contributions and growth assumptions. For planning only, not a guarantee." not in html
    assert "Estimate at age 55 under current balances, contributions and growth assumptions." not in html
    assert "Projected at age 55 under current balances, contributions and growth assumptions." not in html
    assert "Private pot scenario estimate at age 55:" in html
    assert "Private pot estimate at age 55:" not in html
    assert "Projected private pot at age 55:" not in html
    assert html.count("Scenario estimate at 55:") >= 2
    assert "Estimate at 55:" not in html
    assert "Projected at 55:" not in html
    assert html.count("Accessible pot scenario estimate at retirement") == 2
    assert "Accessible pot estimate at retirement" not in html
    assert "State Pension assumption" in html
    assert "illustrative State Pension" not in html
    assert "From age 55 to 60." in html
    assert "in this scenario." not in html
