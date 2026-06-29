from datetime import date as real_date

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
        "monthly_cash_park": 0,
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


def test_schedule_api_rejects_missing_rules_without_deleting_existing_schedule(app, client, make_user):
    uid, username, password = make_user(username="proj-schedule-missing-rules", password="password123")
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
        json={"account_id": account_id},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"ok": False, "error": "rules must be a list"}

    with app.app_context():
        remaining = fetch_contribution_overrides_for_reason(account_id, uid, "schedule")
        assert len(remaining) == 1
        assert remaining[0]["from_month"] == "2028-11"
        assert remaining[0]["to_month"] == "9999-12"
        assert float(remaining[0]["override_amount"]) == 450.0


def test_schedule_api_rejects_non_list_rules_without_deleting_existing_schedule(app, client, make_user):
    uid, username, password = make_user(username="proj-schedule-object-rules", password="password123")
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
        json={"account_id": account_id, "rules": {"start_month": "2030-09", "amount": 700}},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"ok": False, "error": "rules must be a list"}

    with app.app_context():
        remaining = fetch_contribution_overrides_for_reason(account_id, uid, "schedule")
        assert len(remaining) == 1
        assert remaining[0]["from_month"] == "2028-11"
        assert remaining[0]["to_month"] == "9999-12"
        assert float(remaining[0]["override_amount"]) == 450.0


def test_schedule_api_rejects_invalid_account_id_without_server_error(app, client, make_user):
    uid, username, password = make_user(username="proj-schedule-bad-account", password="password123")
    with app.app_context():
        assumptions = dict(fetch_assumptions(uid))
        assumptions.update({
            "annual_growth_rate": 0.05,
            "retirement_age": 62,
            "date_of_birth": "1983-05-25",
            "salary_day": 25,
        })
        update_assumptions(assumptions, uid)

    _login(client, username, password)
    resp = client.post(
        "/projections/api/account-schedule",
        json={"account_id": "not-an-id", "rules": []},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"ok": False, "error": "account_id must be a valid account"}



def test_yearly_account_series_uses_the_point_month_not_the_previous_year_for_overrides(app, client, make_user, monkeypatch):
    from app import calculations

    class FakeDate(real_date):
        @classmethod
        def today(cls):
            return cls(2026, 6, 18)

    monkeypatch.setattr(calculations, "date", FakeDate)

    uid, username, password = make_user(username="proj-series-yearly-lisa", password="password123")
    with app.app_context():
        assumptions = dict(fetch_assumptions(uid))
        assumptions.update({
            "annual_growth_rate": 0.05,
            "retirement_age": 60,
            "date_of_birth": "1982-12-18",
            "salary_day": 28,
        })
        update_assumptions(assumptions, uid)
        account_id = create_account(_account("Lifetime ISA", "Lifetime ISA", 277, 0), uid)
        create_contribution_override({
            "account_id": account_id,
            "from_month": "2029-04",
            "to_month": "2029-07",
            "override_amount": 1000,
            "reason": "temporary_plan",
        }, uid)

    _login(client, username, password)
    resp = client.get(f"/projections/api/account-series?account_id={account_id}&mode=yearly")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True

    point_2030_06 = next(point for point in data["points"] if point["month_key"] == "2030-06")
    assert point_2030_06["label"] == "2030-06"
    assert point_2030_06["age"] == 47.5
    assert point_2030_06["personal_monthly"] == 0.0
    assert point_2030_06["into_pot_monthly"] == 0.0
    assert "Age 47" not in {point["label"] for point in data["points"]}


def test_schedule_api_replaces_existing_schedule_rules_instead_of_appending(app, client, make_user):
    uid, username, password = make_user(username="proj-schedule-replace", password="password123")
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
            "override_amount": 750,
            "reason": "schedule",
        }, uid)

    _login(client, username, password)
    resp = client.post(
        "/projections/api/account-schedule",
        json={
            "account_id": account_id,
            "rules": [
                {"start_age": 50, "amount": 900},
                {"start_age": 52, "amount": 1100},
            ],
        },
    )

    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}

    with app.app_context():
        remaining = fetch_contribution_overrides_for_reason(account_id, uid, "schedule")
        assert len(remaining) == 2
        assert [float(row["override_amount"]) for row in remaining] == [900.0, 1100.0]
        assert [(row["from_month"], row["to_month"]) for row in remaining] == [
            ("2033-05", "2035-04"),
            ("2035-05", "9999-12"),
        ]


def test_schedule_api_saves_month_based_rules_without_date_of_birth(app, client, make_user):
    uid, username, password = make_user(username="proj-schedule-month", password="password123")
    with app.app_context():
        assumptions = dict(fetch_assumptions(uid))
        assumptions.update({
            "annual_growth_rate": 0.05,
            "retirement_age": 62,
            "date_of_birth": None,
            "salary_day": 25,
        })
        update_assumptions(assumptions, uid)
        account_id = create_account(_account("ISA", "Stocks & Shares ISA", 10000, 300), uid)

    _login(client, username, password)
    resp = client.post(
        "/projections/api/account-schedule",
        json={
            "account_id": account_id,
            "rules": [
                {"start_month": "2030-09", "amount": 700},
                {"start_month": "2032-01", "amount": 950},
            ],
        },
    )

    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}

    with app.app_context():
        remaining = fetch_contribution_overrides_for_reason(account_id, uid, "schedule")
        assert [(row["from_month"], row["to_month"]) for row in remaining] == [
            ("2030-09", "2031-12"),
            ("2032-01", "9999-12"),
        ]
        assert [float(row["override_amount"]) for row in remaining] == [700.0, 950.0]

    get_resp = client.get(f"/projections/api/account-schedule?account_id={account_id}")
    assert get_resp.status_code == 200
    data = get_resp.get_json()
    assert data["ok"] is True
    assert data["has_dob"] is False
    assert data["rules"] == [
        {"from_month": "2030-09", "start_month": "2030-09", "start_age": None, "amount": 700.0},
        {"from_month": "2032-01", "start_month": "2032-01", "start_age": None, "amount": 950.0},
    ]


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
