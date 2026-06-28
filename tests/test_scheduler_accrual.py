from datetime import datetime, timezone


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        fixed = cls(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
        if tz is None:
            return fixed.replace(tzinfo=None)
        return fixed.astimezone(tz)


def _cash_isa_payload(**overrides):
    payload = {
        "name": "Trading 212 Cash ISA",
        "provider": "Trading 212",
        "wrapper_type": "Cash ISA",
        "category": "ISA",
        "tags": "ISA,Cash",
        "current_value": 1600.0,
        "monthly_contribution": 450.0,
        "goal_value": None,
        "valuation_mode": "manual",
        "growth_mode": "custom",
        "growth_rate_override": 0.036,
        "owner": "Janusz",
        "is_active": 1,
        "notes": "Cash ISA with a planned monthly contribution.",
        "last_updated": "2026-06-15T12:00:00+00:00",
        "employer_contribution": 0,
        "contribution_method": "standard",
        "annual_fee_pct": 0,
        "platform_fee_pct": 0,
        "platform_fee_flat": 0,
        "platform_fee_cap": 0,
        "fund_fee_pct": 0,
        "contribution_fee_pct": 0,
        "uninvested_cash": 0,
        "cash_interest_rate": 0.036,
        "interest_payment_day": 0,
    }
    payload.update(overrides)
    return payload


def test_cash_isa_scheduler_accrues_interest_without_adding_planned_contribution(
    app, make_user, monkeypatch
):
    """Cash ISA auto-accrual should not invent deposits from the contribution plan.

    A £1,600 cash balance at 3.6% should earn roughly 47p over three days;
    a £450 planned monthly contribution would incorrectly add about £44.
    """
    from app.models import create_account, fetch_all_accounts
    from app.services import scheduler
    from app.services.scheduler import _accrue_manual_accounts

    monkeypatch.setattr(scheduler, "datetime", FrozenDateTime)

    with app.app_context():
        user_id, _, _ = make_user()
        create_account(_cash_isa_payload(), user_id)
        accounts = [dict(row) for row in fetch_all_accounts(user_id)]

        _accrue_manual_accounts(user_id, accounts)

        updated = dict(fetch_all_accounts(user_id)[0])

    assert updated["current_value"] == 1600.47
