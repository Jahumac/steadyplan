from datetime import date

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
    assert classify_account(_account("ISA", "Stocks & Shares ISA")).access_type == ACCESSIBLE
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
            _account("SIPP", "SIPP", 50000, 200),
            _account("LISA", "Lifetime ISA", 500, 0),
        ]
        summary = build_accessible_security_summary(accounts, assumptions)

    assert summary["accessible_current"] == 9500
    assert summary["locked_current"] == 50000
    assert summary["restricted_current"] == 500
    assert summary["milestones"][0]["target"] == 20000
    assert summary["milestones"][0]["months"] == 11
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
        create_account(_account("ISA", "Stocks & Shares ISA", 10000, 500), uid)
        create_account(_account("Pension", "SIPP", 50000, 100), uid)

    client.post("/login", data={"username": username, "password": password})
    response = client.get("/planning/?desired_income=24000")

    assert response.status_code == 200
    assert b'budget-year-strip month-strip-global month-strip-mobile-hidden' in response.data
    assert b"Accessible vs locked" in response.data
    assert b"Target retirement income/year" in response.data
    assert b"Accessible security milestones" in response.data
    assert b"View account details" in response.data
    assert b"perfect retirement salary" not in response.data
    assert b"Weakest link" in response.data
    assert b"Balanced illustration:" in response.data
    assert b"Illustrative estimate, not guaranteed income." in response.data
    assert b"planning illustrations, not guaranteed safe withdrawal advice." in response.data
    assert b"planning scenarios, not guaranteed safe withdrawal advice." not in response.data
    assert b"Balanced estimate:" not in response.data
    assert b"Scenario estimate, not guaranteed income." not in response.data

    css = open("/opt/data/steadyplan/app/static/css/styles.css").read()
    assert ".planning-hero-strip {" in css
    assert css.count("grid-template-columns: repeat(2, minmax(0, 1fr));") >= 3
    assert "@media (max-width: 520px) {" in css
    assert ".planning-hero-caveat {" in css
    assert "display: none;" in css


def test_planning_page_no_goal_mode_uses_plan_wording(app, client, make_user):
    uid, username, password = make_user()
    with app.app_context():
        create_account(_account("ISA", "Stocks & Shares ISA", 10000, 500), uid)
        create_account(_account("Pension", "SIPP", 50000, 100), uid)

    client.post("/login", data={"username": username, "password": password})
    response = client.get("/planning/")

    assert response.status_code == 200
    html = response.data.decode("utf-8", errors="ignore")
    assert "using the balanced illustration as the income guide" in html
    assert "using the balanced estimate as the income to model" not in html
    assert "with this plan." in html
    assert "in this scenario." not in html
