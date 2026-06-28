from datetime import date, datetime
import pytest
from app.calculations import (
    _retirement_target_date,
    age_from_dob,
    calculate_isa_usage,
    calculate_pension_usage,
    contribution_breakdown,
    full_year_contribution_months,
    months_in_tax_year,
    to_float,
)

def test_age_from_dob():
    # Test cases: (dob_str, today, expected_age)
    cases = [
        ("1980-01-01", date(2024, 1, 1), 44.0),
        ("1980-07-01", date(2024, 1, 1), 43.5),
        ("1980-01-01", date(2024, 1, 15), 44.0),
        ("2000-01-01", date(2024, 1, 1), 24.0),
        ("", date(2024, 1, 1), 0.0),
        (None, date(2024, 1, 1), 0.0),
        ("invalid", date(2024, 1, 1), 0.0),
    ]
    for dob, today, expected in cases:
        assert age_from_dob(dob, today) == pytest.approx(expected, rel=1e-3)

def test_to_float():
    assert to_float("123.45") == 123.45
    assert to_float(123.45) == 123.45
    assert to_float(None) == 0.0
    assert to_float("abc") == 0.0


def test_retirement_target_date_handles_leap_day_birthdays_in_non_leap_years():
    assert _retirement_target_date("1988-02-29", 65, "birthday") == date(2053, 2, 28)

def test_contribution_breakdown_sipp():
    account = {
        "monthly_contribution": 800,
        "wrapper_type": "SIPP",
        "contribution_method": "standard"
    }
    assumptions = {"tax_band": "basic"}
    breakdown = contribution_breakdown(account, assumptions)
    assert breakdown["personal"] == 800
    assert breakdown["tax_relief"] == 200 # 800 * 0.25
    assert breakdown["total_into_pot"] == 1000
    assert breakdown["self_assessment"] == 0

def test_contribution_breakdown_sipp_higher_rate():
    account = {
        "monthly_contribution": 800,
        "wrapper_type": "SIPP",
        "contribution_method": "standard"
    }
    assumptions = {"tax_band": "higher"}
    breakdown = contribution_breakdown(account, assumptions)
    assert breakdown["personal"] == 800
    assert breakdown["tax_relief"] == 200
    assert breakdown["total_into_pot"] == 1000
    assert breakdown["self_assessment"] == 200 # 1000 * (0.40 - 0.20)

def test_contribution_breakdown_salary_sacrifice():
    account = {
        "monthly_contribution": 1000,
        "employer_contribution": 500,
        "wrapper_type": "Workplace Pension",
        "contribution_method": "salary_sacrifice"
    }
    breakdown = contribution_breakdown(account)
    assert breakdown["personal"] == 1000
    assert breakdown["employer"] == 500
    assert breakdown["tax_relief"] == 0
    assert breakdown["total_into_pot"] == 1500


def test_contribution_breakdown_lisa_bonus_before_age_50():
    account = {
        "monthly_contribution": 100,
        "wrapper_type": "Lifetime ISA",
        "contribution_method": "standard",
    }
    assumptions = {"current_age": 40}

    breakdown = contribution_breakdown(account, assumptions)

    assert breakdown["personal"] == 100
    assert breakdown["government_bonus"] == 25
    assert breakdown["total_into_pot"] == 125
    assert breakdown["method_label"] == "Lifetime ISA bonus (25%)"


def test_contribution_breakdown_lisa_stops_from_age_50():
    account = {
        "monthly_contribution": 100,
        "wrapper_type": "Lifetime ISA",
        "contribution_method": "standard",
    }
    assumptions = {"current_age": 50}

    breakdown = contribution_breakdown(account, assumptions)

    assert breakdown["personal"] == 0
    assert breakdown["government_bonus"] == 0
    assert breakdown["total_into_pot"] == 0
    assert breakdown["method_label"] == "Lifetime ISA contributions stop at age 50"


def test_full_tax_year_has_12_contribution_months_for_early_month_salary_day():
    assert months_in_tax_year(date(2027, 4, 4), salary_day=1) == 12
    assert full_year_contribution_months(salary_day=1) == 12


def test_isa_projection_includes_next_april_for_early_month_salary_day():
    accounts = [
        {
            "id": 1,
            "name": "ISA",
            "wrapper_type": "Stocks & Shares ISA",
            "monthly_contribution": 100,
        }
    ]

    usage = calculate_isa_usage(
        accounts,
        ad_hoc_contributions=[],
        today=date(2026, 4, 6),
        salary_day=1,
    )

    assert usage["months"] == 0
    assert usage["total_months"] == 12
    assert usage["projected_isa"] == 1200


def test_isa_usage_accepts_stocks_and_shares_label_variant():
    accounts = [
        {
            "id": 1,
            "name": "ISA",
            "wrapper_type": "Stocks and Shares ISA",
            "monthly_contribution": 100,
        }
    ]

    usage = calculate_isa_usage(
        accounts,
        ad_hoc_contributions=[],
        today=date(2026, 6, 30),
        salary_day=28,
    )

    assert usage["monthly_isa"] == 300
    assert usage["projected_isa"] == 1200
    assert usage["breakdown"][0]["wrapper_type"] == "Stocks and Shares ISA"


def test_isa_usage_counts_monthly_cash_park_toward_subscription_totals():
    accounts = [
        {
            "id": 1,
            "name": "ISA",
            "wrapper_type": "Stocks & Shares ISA",
            "monthly_contribution": 100,
            "monthly_cash_park": 25,
        }
    ]

    usage = calculate_isa_usage(
        accounts,
        ad_hoc_contributions=[],
        today=date(2026, 6, 30),
        salary_day=28,
    )

    assert usage["monthly_isa"] == 375
    assert usage["projected_isa"] == 1500
    assert usage["breakdown"][0]["monthly_contribution"] == 125


def test_isa_usage_excludes_regular_lisa_contributions_after_age_50():
    accounts = [
        {
            "id": 1,
            "name": "LISA",
            "wrapper_type": "Lifetime ISA",
            "monthly_contribution": 100,
        }
    ]

    usage = calculate_isa_usage(
        accounts,
        ad_hoc_contributions=[],
        today=date(2026, 10, 1),
        salary_day=28,
        lisa_contributions_allowed=False,
    )

    assert usage["lisa_used"] == 0
    assert usage["projected_lisa"] == 0
    assert usage["isa_used"] == 0
    assert usage["projected_isa"] == 0


def test_isa_usage_keeps_recorded_lisa_contributions_after_age_50():
    accounts = [
        {
            "id": 1,
            "name": "LISA",
            "wrapper_type": "Lifetime ISA",
            "monthly_contribution": 100,
        }
    ]
    ad_hoc = [
        {
            "account_id": 1,
            "wrapper_type": "Lifetime ISA",
            "amount": 250,
        }
    ]

    usage = calculate_isa_usage(
        accounts,
        ad_hoc_contributions=ad_hoc,
        today=date(2026, 10, 1),
        salary_day=28,
        lisa_contributions_allowed=False,
    )

    assert usage["lisa_used"] == 250
    assert usage["projected_lisa"] == 250
    assert usage["isa_used"] == 250
    assert usage["projected_isa"] == 250


def test_isa_projection_respects_reviewed_skip_in_year_end_projection():
    accounts = [
        {
            "id": 1,
            "name": "ISA",
            "wrapper_type": "Stocks & Shares ISA",
            "monthly_contribution": 100,
        }
    ]

    usage = calculate_isa_usage(
        accounts,
        ad_hoc_contributions=[],
        today=date(2026, 6, 30),
        salary_day=28,
        review_contributions=[
            {
                "account_id": 1,
                "month_key": "2026-05",
                "expected_contribution": 100,
                "is_skipped": 1,
            }
        ],
    )

    assert usage["monthly_isa"] == 200
    assert usage["projected_isa"] == 1100
    assert usage["breakdown"][0]["projected_total"] == 1100


def test_isa_usage_applies_explicit_cash_flow_allowance_adjustments():
    accounts = [
        {
            "id": 1,
            "name": "Cash ISA",
            "wrapper_type": "Cash ISA",
            "monthly_contribution": 100,
        }
    ]
    allowance_events = [
        {"account_id": 1, "amount": 200, "allowance_effect": "subscription"},
        {"account_id": 1, "amount": -150, "allowance_effect": "flexible_withdrawal"},
        {"account_id": 1, "amount": 50, "allowance_effect": "flexible_replacement"},
    ]

    usage = calculate_isa_usage(
        accounts,
        ad_hoc_contributions=[],
        today=date(2026, 6, 30),
        salary_day=28,
        allowance_events=allowance_events,
    )

    assert usage["monthly_isa"] == 300
    assert usage["allowance_adjustment_isa"] == 100
    assert usage["isa_used"] == 400
    assert usage["projected_isa"] == 1300
    assert usage["breakdown"][0]["allowance_adjustment"] == 100
    assert usage["breakdown"][0]["projected_total"] == 1200


def test_pension_projection_respects_reviewed_skip_in_year_end_projection():
    accounts = [
        {
            "id": 1,
            "name": "SIPP",
            "wrapper_type": "SIPP",
            "category": "Pension",
            "monthly_contribution": 80,
            "employer_contribution": 0,
            "contribution_method": "standard",
            "pension_contribution_day": 28,
        }
    ]

    usage = calculate_pension_usage(
        accounts,
        ad_hoc_contributions=[],
        assumptions={"tax_band": "basic"},
        today=date(2026, 6, 30),
        salary_day=28,
        review_contributions=[
            {
                "account_id": 1,
                "month_key": "2026-05",
                "expected_contribution": 80,
                "is_skipped": 1,
            }
        ],
    )

    assert usage["pension_used"] == 200
    assert usage["projected_total"] == 1100
