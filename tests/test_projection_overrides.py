from datetime import date


def _assumptions():
    return {
        "annual_growth_rate": 0.0,
        "retirement_age": 60,
        "date_of_birth": "1990-01-01",
        "retirement_date_mode": "birthday",
        "salary_day": 28,
        "tax_band": "basic",
    }


def test_projection_uses_current_month_budget_override_then_returns_to_normal():
    from app.calculations import projected_account_value_at_month

    account = {
        "id": 1,
        "name": "Lifetime ISA",
        "wrapper_type": "Lifetime ISA",
        "current_value": 1000,
        "monthly_contribution": 100,
        "employer_contribution": 0,
        "contribution_method": "standard",
        "contribution_fee_pct": 0,
        "growth_mode": "custom",
        "growth_rate_override": 0,
        "annual_fee_pct": 0,
        "platform_fee_pct": 0,
        "platform_fee_flat": 0,
        "platform_fee_cap": 0,
        "fund_fee_pct": 0,
        "_projection_start_month": "2026-04",
        "_contribution_overrides": [
            {"from_month": "2026-04", "to_month": "2026-04", "override_amount": 0},
        ],
    }

    assert projected_account_value_at_month(account, _assumptions(), 2) == 1125


def test_projection_start_month_waits_until_review_ready_date():
    from app.calculations import projection_start_month_key

    assumptions = _assumptions()
    assert projection_start_month_key(assumptions, today=date(2026, 4, 26)) == "2026-04"
    assert projection_start_month_key(assumptions, today=date(2026, 4, 30)) == "2026-05"


def test_projection_prefers_newest_equal_span_override():
    from app.calculations import contribution_override_for_month

    account = {
        "_contribution_overrides": [
            {
                "id": 1,
                "from_month": "2026-06",
                "to_month": "2026-06",
                "override_amount": 100,
            },
            {
                "id": 2,
                "from_month": "2026-06",
                "to_month": "2026-06",
                "override_amount": 250,
            },
        ]
    }

    assert contribution_override_for_month(account, "2026-06") == 250
