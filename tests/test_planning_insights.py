from datetime import date

from tests.path_helpers import STATIC_ROOT

from app.models import create_account, fetch_assumptions, update_assumptions
from app.services.planning_insights import (
    ACCESSIBLE,
    LOCKED,
    RESTRICTED,
    build_accessible_security_summary,
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
