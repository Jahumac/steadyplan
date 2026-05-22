from datetime import date, datetime
import pytest
from app.calculations import age_from_dob, to_float, contribution_breakdown

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
