from datetime import date, datetime
import pytest
from app.calculations import (
    age_from_dob,
    calculate_isa_usage,
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
    assert breakdown["method_label"] == "LISA contributions stop at age 50"


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
