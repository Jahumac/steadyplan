import pytest

from app.models.debts import amortisation_schedule, debt_total_interest


def test_debt_total_interest_uses_actual_final_payment():
    balance = 1000
    monthly_payment = 300
    apr = 12

    schedule = amortisation_schedule(balance, apr, monthly_payment)
    expected_interest = round(sum(row["interest"] for row in schedule), 2)

    assert schedule[-1]["payment"] < monthly_payment
    assert debt_total_interest(balance, monthly_payment, apr) == pytest.approx(expected_interest)
