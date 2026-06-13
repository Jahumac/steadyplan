import pytest

from app.models.debts import (
    amortisation_schedule,
    compare_debt_payoff_strategies,
    debt_is_payoff_guidance_eligible,
    debt_overpayment_scenario,
    debt_total_interest,
    rank_debts_avalanche,
    rank_debts_snowball,
    simulate_debt_payoff_strategy,
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


def _debt_card(*, debt_id, name, balance, payment, apr, created_order=None):
    return {
        "id": debt_id,
        "name": name,
        "current_balance": float(balance),
        "monthly_payment": float(payment),
        "apr": float(apr),
        "created_order": debt_id if created_order is None else created_order,
    }


def test_rank_debts_avalanche_orders_by_highest_apr_then_balance():
    debts = [
        _debt_card(debt_id=1, name="Loan", balance=8000, payment=220, apr=12.9),
        _debt_card(debt_id=2, name="Card", balance=2500, payment=120, apr=29.9),
        _debt_card(debt_id=3, name="Store", balance=4000, payment=110, apr=29.9),
    ]

    ranked = rank_debts_avalanche(debts)

    assert [debt["name"] for debt in ranked] == ["Store", "Card", "Loan"]


def test_rank_debts_snowball_orders_by_smallest_balance_then_apr():
    debts = [
        _debt_card(debt_id=1, name="Loan", balance=8000, payment=220, apr=12.9),
        _debt_card(debt_id=2, name="Card", balance=2500, payment=120, apr=29.9),
        _debt_card(debt_id=3, name="Store", balance=2500, payment=110, apr=24.9),
    ]

    ranked = rank_debts_snowball(debts)

    assert [debt["name"] for debt in ranked] == ["Card", "Store", "Loan"]


def test_simulate_debt_payoff_strategy_rolls_freed_payments_forward():
    debts = [
        _debt_card(debt_id=1, name="Card A", balance=1200, payment=100, apr=18),
        _debt_card(debt_id=2, name="Loan B", balance=2000, payment=75, apr=8),
    ]

    baseline = simulate_debt_payoff_strategy(debts, extra_monthly=0, strategy="avalanche")
    accelerated = simulate_debt_payoff_strategy(debts, extra_monthly=50, strategy="avalanche")

    assert baseline["debt_order"] == ["Card A", "Loan B"]
    assert accelerated["debt_order"] == ["Card A", "Loan B"]
    assert accelerated["total_months"] < baseline["total_months"]
    assert accelerated["total_interest"] < baseline["total_interest"]
    assert accelerated["payoff_steps"][1]["rolled_monthly_payment"] > accelerated["payoff_steps"][1]["minimum_payment"]


def test_simulate_debt_payoff_strategy_with_zero_extra_returns_coherent_baseline():
    debts = [
        _debt_card(debt_id=1, name="Card", balance=600, payment=60, apr=15),
        _debt_card(debt_id=2, name="Loan", balance=900, payment=50, apr=6),
    ]

    scenario = simulate_debt_payoff_strategy(debts, extra_monthly=0, strategy="snowball")

    assert scenario["extra_monthly"] == 0
    assert scenario["included_debt_count"] == 2
    assert scenario["excluded_debt_count"] == 0
    assert scenario["total_months"] > 0
    assert scenario["total_interest"] > 0


def test_debt_payoff_guidance_excludes_unsustainable_debts():
    debt = _debt_card(debt_id=1, name="Problem debt", balance=1000, payment=5, apr=30)

    assert debt_is_payoff_guidance_eligible(debt) is False

    scenario = simulate_debt_payoff_strategy([debt], extra_monthly=50, strategy="avalanche")

    assert scenario["included_debt_count"] == 0
    assert scenario["excluded_debt_count"] == 1
    assert scenario["excluded_debts"][0]["reason"] == "Current payment does not cover interest"


def test_compare_debt_payoff_strategies_skips_zero_balance_debts_and_shows_interest_tradeoff():
    debts = [
        _debt_card(debt_id=1, name="Card", balance=1200, payment=90, apr=24),
        _debt_card(debt_id=2, name="Loan", balance=4000, payment=180, apr=7),
        _debt_card(debt_id=3, name="Cleared", balance=0, payment=50, apr=0),
    ]

    comparison = compare_debt_payoff_strategies(debts, extra_monthly=75)

    assert comparison["included_debt_count"] == 2
    assert comparison["excluded_debt_count"] == 1
    assert comparison["excluded_debts"][0]["name"] == "Cleared"
    assert comparison["avalanche"]["total_interest"] <= comparison["snowball"]["total_interest"]
