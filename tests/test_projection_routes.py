from app.models import (
    create_account,
    create_contribution_override,
    fetch_assumptions,
    fetch_contribution_overrides_for_reason,
    update_assumptions,
)


def _account(name, wrapper_type, value=0, monthly=0, **overrides):
    payload = {
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
        "last_updated": "2026-05-29",
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
    }
    payload.update(overrides)
    return payload


def _login(client, username, password):
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)


def test_schedule_api_rejects_invalid_rules_without_deleting_existing_schedule(app, client, make_user):
    uid, username, password = make_user(username="proj-schedule", password="password123")
    with app.app_context():
        assumptions = dict(fetch_assumptions(uid))
        assumptions.update({
            "annual_growth_rate": 0.05,
            "retirement_age": 62,
            "date_of_birth": "1983-05-25",
            "salary_day": 25,
        })
        update_assumptions(assumptions, uid)
        account_id = create_account(_account("SIPP", "SIPP", 50000, 500), uid)
        create_contribution_override({
            "account_id": account_id,
            "from_month": "2028-11",
            "to_month": "9999-12",
            "override_amount": 750,
            "reason": "schedule",
        }, uid)
        original = fetch_contribution_overrides_for_reason(account_id, uid, "schedule")
        assert len(original) == 1

    _login(client, username, password)
    resp = client.post(
        "/projections/api/account-schedule",
        json={
            "account_id": account_id,
            "rules": [{"start_age": "", "amount": 900}],
        },
    )

    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False

    with app.app_context():
        remaining = fetch_contribution_overrides_for_reason(account_id, uid, "schedule")
        assert len(remaining) == 1
        assert remaining[0]["from_month"] == "2028-11"
        assert remaining[0]["to_month"] == "9999-12"
        assert float(remaining[0]["override_amount"]) == 750.0


def test_schedule_api_allows_intentional_clear_with_empty_rules(app, client, make_user):
    uid, username, password = make_user(username="proj-schedule-clear", password="password123")
    with app.app_context():
        assumptions = dict(fetch_assumptions(uid))
        assumptions.update({
            "annual_growth_rate": 0.05,
            "retirement_age": 62,
            "date_of_birth": "1983-05-25",
            "salary_day": 25,
        })
        update_assumptions(assumptions, uid)
        account_id = create_account(_account("ISA", "Stocks & Shares ISA", 10000, 300), uid)
        create_contribution_override({
            "account_id": account_id,
            "from_month": "2028-11",
            "to_month": "9999-12",
            "override_amount": 450,
            "reason": "schedule",
        }, uid)

    _login(client, username, password)
    resp = client.post(
        "/projections/api/account-schedule",
        json={"account_id": account_id, "rules": []},
    )

    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}

    with app.app_context():
        remaining = fetch_contribution_overrides_for_reason(account_id, uid, "schedule")
        assert remaining == []
