import pytest

from app.models.debts import (
    amortisation_schedule,
    debt_overpayment_scenario,
    debt_total_interest,
)


def test_debt_total_interest_uses_actual_final_payment():
    balance = 1000
    monthly_payment = 300
    apr = 12

    schedule = amortisation_schedule(balance, apr, monthly_payment)
    expected_interest = round(sum(row["interest"] for row in schedule), 2)

    assert schedule[-1]["payment"] < monthly_payment
    assert debt_total_interest(balance, monthly_payment, apr) == pytest.approx(expected_interest)


def test_debt_overpayment_scenario_models_recurring_extra_payment():
    scenario = debt_overpayment_scenario(
        balance=15000,
        monthly_payment=454.36,
        apr=30.5,
        extra_monthly=100,
    )

    assert scenario["baseline_months"] == 73
    assert scenario["new_months"] < scenario["baseline_months"]
    assert scenario["months_saved"] == 26
    assert scenario["baseline_interest"] == pytest.approx(18073.17)
    assert scenario["new_interest"] == pytest.approx(10708.31)
    assert scenario["interest_saved"] == pytest.approx(7364.86)
    assert scenario["new_monthly_payment"] == pytest.approx(554.36)
    assert scenario["one_off_overpayment"] == 0


def test_debt_overpayment_scenario_models_one_off_overpayment():
    scenario = debt_overpayment_scenario(
        balance=15000,
        monthly_payment=454.36,
        apr=30.5,
        one_off_overpayment=1000,
    )

    assert scenario["baseline_months"] == 73
    assert scenario["new_months"] == 61
    assert scenario["months_saved"] == 12
    assert scenario["new_interest"] == pytest.approx(13671.58)
    assert scenario["interest_saved"] == pytest.approx(4401.59)
    assert scenario["one_off_overpayment"] == 1000


def test_debt_overpayment_scenario_combines_one_off_and_recurring_overpayments():
    scenario = debt_overpayment_scenario(
        balance=15000,
        monthly_payment=454.36,
        apr=30.5,
        extra_monthly=100,
        one_off_overpayment=1000,
    )

    assert scenario["new_months"] == 41
    assert scenario["months_saved"] == 32
    assert scenario["new_interest"] == pytest.approx(8681.40)
    assert scenario["interest_saved"] == pytest.approx(9391.77)


def test_debt_overpayment_scenario_refuses_unsustainable_baseline_payment():
    scenario = debt_overpayment_scenario(
        balance=15000,
        monthly_payment=100,
        apr=30.5,
        extra_monthly=0,
        one_off_overpayment=0,
    )

    assert scenario["baseline_months"] is None
    assert scenario["new_months"] is None
    assert scenario["interest_saved"] is None
