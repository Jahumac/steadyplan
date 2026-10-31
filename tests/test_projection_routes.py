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


def _seed_account(app, uid, *, name="ISA", wrapper="Stocks & Shares ISA",
                  value=10000, monthly=300, dob="1983-05-25"):
    assumptions = dict(fetch_assumptions(uid))
    assumptions.update({
        "annual_growth_rate": 0.05,
        "retirement_age": 62,
        "date_of_birth": dob,
        "salary_day": 25,
    })
    update_assumptions(assumptions, uid)
    return create_account(_account(name, wrapper, value, monthly), uid)


def test_schedule_api_is_read_only(app, client, make_user):
    """The projections panel no longer writes: the payment calendar is the only editor.

    Two editors on contribution_overrides meant whichever you touched last silently
    won, and the two surfaces could disagree about the same month.
    """
    uid, username, password = make_user(username="proj-readonly", password="password123")
    with app.app_context():
        account_id = _seed_account(app, uid)
        create_contribution_override({
            "account_id": account_id,
            "from_month": "2028-11",
            "to_month": "9999-12",
            "override_amount": 750,
            "reason": "schedule",
        }, uid)
        before = fetch_contribution_overrides_for_reason(account_id, uid, "schedule")
        assert len(before) == 1

    _login(client, username, password)
    resp = client.post(
        "/projections/api/account-schedule",
        json={"account_id": account_id, "rules": [{"start_month": "2030-09", "amount": 900}]},
    )

    assert resp.status_code == 405

    with app.app_context():
        after = fetch_contribution_overrides_for_reason(account_id, uid, "schedule")
        assert len(after) == 1
        assert after[0]["from_month"] == "2028-11"
        assert after[0]["to_month"] == "9999-12"
        assert float(after[0]["override_amount"]) == 750.0


def test_schedule_api_flags_itself_read_only_and_points_at_the_calendar(app, client, make_user):
    uid, username, password = make_user(username="proj-readonly-flag", password="password123")
    with app.app_context():
        account_id = _seed_account(app, uid, name="SIPP", wrapper="SIPP", value=50000, monthly=500)

    _login(client, username, password)
    data = client.get(f"/projections/api/account-schedule?account_id={account_id}").get_json()

    assert data["ok"] is True
    assert data["read_only"] is True
    assert data["edit_url"].startswith("/budget/")


def test_schedule_api_returns_standing_plan_rows(app, client, make_user):
    uid, username, password = make_user(username="proj-standing", password="password123")
    with app.app_context():
        account_id = _seed_account(app, uid)
        create_contribution_override({
            "account_id": account_id,
            "from_month": "2028-11",
            "to_month": "9999-12",
            "override_amount": 750,
            "reason": "schedule",
        }, uid)

    _login(client, username, password)
    data = client.get(f"/projections/api/account-schedule?account_id={account_id}").get_json()

    assert data["rules"] == [
        {"from_month": "2028-11", "start_month": "2028-11", "start_age": 45, "amount": 750.0},
    ]


def test_schedule_api_reflects_calendar_rules_but_not_one_off_edits(app, client, make_user):
    """Recurring rules from the calendar show up here; month tweaks and dated
    temporary plans do not, because they are not standing changes."""
    uid, username, password = make_user(username="proj-scope", password="password123")
    with app.app_context():
        account_id = _seed_account(app, uid)
        create_contribution_override({
            "account_id": account_id, "from_month": "2028-11", "to_month": "9999-12",
            "override_amount": 750, "reason": "schedule",
        }, uid)
        create_contribution_override({
            "account_id": account_id, "from_month": "2032-01", "to_month": "9999-12",
            "override_amount": 900, "reason": "rule:Pay rise",
        }, uid)
        create_contribution_override({
            "account_id": account_id, "from_month": "2030-06", "to_month": "2030-06",
            "override_amount": 50, "reason": "Calendar edit",
        }, uid)
        create_contribution_override({
            "account_id": account_id, "from_month": "2031-07", "to_month": "2031-09",
            "override_amount": 200, "reason": "temporary_plan:Holiday",
        }, uid)

    _login(client, username, password)
    months = [r["start_month"] for r in
              client.get(f"/projections/api/account-schedule?account_id={account_id}").get_json()["rules"]]

    assert months == ["2028-11", "2032-01"]


def test_schedule_api_requires_account_id(app, client, make_user):
    uid, username, password = make_user(username="proj-no-account", password="password123")
    with app.app_context():
        _seed_account(app, uid)

    _login(client, username, password)
    resp = client.get("/projections/api/account-schedule")

    assert resp.status_code == 400
    assert resp.get_json() == {"ok": False, "error": "account_id required"}


def test_schedule_api_rejects_unknown_account_without_server_error(app, client, make_user):
    uid, username, password = make_user(username="proj-bad-account", password="password123")
    with app.app_context():
        _seed_account(app, uid)

    _login(client, username, password)
    resp = client.get("/projections/api/account-schedule?account_id=999999")

    assert resp.status_code == 404
    assert resp.get_json()["ok"] is False


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
