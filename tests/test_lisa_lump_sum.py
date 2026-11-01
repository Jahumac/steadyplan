"""Lump-sum (one-off) contributions, with Lifetime ISA rules.

A LISA has a hard £4,000 annual cap inside the ISA allowance, and the 25%
government bonus is capped at £1,000/year as a consequence. Contributing past the
cap is not just "no bonus" — a provider rejects the excess, so the app refuses it
and says by how much rather than silently accepting it.
"""


def _account(name, wrapper_type, monthly=0, value=0):
    return {
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


def _login(client, username, password):
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)


def _set_age(app, uid, dob="1983-05-25"):
    from app.models import fetch_assumptions, update_assumptions

    with app.app_context():
        assumptions = dict(fetch_assumptions(uid))
        assumptions.update({"date_of_birth": dob, "retirement_age": 62, "salary_day": 25})
        update_assumptions(assumptions, uid)


def _contributions(app, uid):
    from app.models import fetch_isa_contributions

    with app.app_context():
        return fetch_isa_contributions(uid, "2000-01-01", "2099-12-31")


def test_lisa_lump_sum_under_the_cap_is_recorded(app, client, make_user):
    from app.models import create_account

    uid, username, password = make_user(username="lisa-lump", password="password123")
    _set_age(app, uid)
    with app.app_context():
        account_id = create_account(_account("My Lifetime ISA", "Lifetime ISA"), uid)

    _login(client, username, password)
    resp = client.post(
        "/allowance/add",
        data={"account_id": account_id, "amount": "4000", "contribution_date": "2026-06-01"},
        follow_redirects=True,
    )

    assert resp.status_code == 200
    rows = _contributions(app, uid)
    assert len(rows) == 1
    assert float(rows[0]["amount"]) == 4000.0
    assert rows[0]["wrapper_type"] == "Lifetime ISA"


def test_lisa_lump_sum_over_the_cap_is_refused_with_the_numbers(app, client, make_user):
    """£4,000 into a LISA that has already used £3,500 must be refused."""
    from app.models import create_account, add_isa_contribution

    uid, username, password = make_user(username="lisa-over", password="password123")
    _set_age(app, uid)
    with app.app_context():
        account_id = create_account(_account("My Lifetime ISA", "Lifetime ISA"), uid)
        add_isa_contribution(uid, account_id, 3500, "2026-05-01", "earlier lump sum")

    _login(client, username, password)
    resp = client.post(
        "/allowance/add",
        data={"account_id": account_id, "amount": "4000", "contribution_date": "2026-06-01"},
        follow_redirects=True,
    )

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Lifetime ISA limit reached" in body
    assert "3,500.00" in body      # already used
    assert "500.00 is left" in body

    # Nothing was written: still only the original row.
    rows = _contributions(app, uid)
    assert len(rows) == 1
    assert float(rows[0]["amount"]) == 3500.0


def test_lump_sum_exactly_filling_the_lisa_cap_is_allowed(app, client, make_user):
    from app.models import create_account, add_isa_contribution

    uid, username, password = make_user(username="lisa-exact", password="password123")
    _set_age(app, uid)
    with app.app_context():
        account_id = create_account(_account("My Lifetime ISA", "Lifetime ISA"), uid)
        add_isa_contribution(uid, account_id, 2500, "2026-05-01")

    _login(client, username, password)
    client.post(
        "/allowance/add",
        data={"account_id": account_id, "amount": "1500", "contribution_date": "2026-06-01"},
        follow_redirects=True,
    )

    rows = _contributions(app, uid)
    assert sorted(float(r["amount"]) for r in rows) == [1500.0, 2500.0]


def test_lisa_cap_does_not_apply_to_a_regular_isa(app, client, make_user):
    """The £4,000 LISA cap must not bleed onto Stocks & Shares ISA entries."""
    from app.models import create_account

    uid, username, password = make_user(username="isa-no-lisa-cap", password="password123")
    _set_age(app, uid)
    with app.app_context():
        account_id = create_account(_account("My S&S ISA", "Stocks & Shares ISA"), uid)

    _login(client, username, password)
    resp = client.post(
        "/allowance/add",
        data={"account_id": account_id, "amount": "12000", "contribution_date": "2026-06-01"},
        follow_redirects=True,
    )

    assert resp.status_code == 200
    rows = _contributions(app, uid)
    assert len(rows) == 1
    assert float(rows[0]["amount"]) == 12000.0


def test_lisa_contribution_blocked_at_age_50(app, client, make_user):
    from app.models import create_account

    uid, username, password = make_user(username="lisa-age-50", password="password123")
    # Turns 50 long before the contribution date.
    _set_age(app, uid, dob="1970-01-01")
    with app.app_context():
        account_id = create_account(_account("My Lifetime ISA", "Lifetime ISA"), uid)

    _login(client, username, password)
    resp = client.post(
        "/allowance/add",
        data={"account_id": account_id, "amount": "1000", "contribution_date": "2026-06-01"},
        follow_redirects=True,
    )

    assert "cannot be made" in resp.get_data(as_text=True) or "50 or over" in resp.get_data(as_text=True)
    assert _contributions(app, uid) == []


def test_allowance_page_exposes_lisa_lump_sum_hooks(app, client, make_user):
    """The live bonus preview needs the room figures and the wrapper on each option."""
    from app.models import create_account

    uid, username, password = make_user(username="lisa-ui", password="password123")
    _set_age(app, uid)
    with app.app_context():
        create_account(_account("My Lifetime ISA", "Lifetime ISA"), uid)

    _login(client, username, password)
    body = client.get("/allowance/").get_data(as_text=True)

    assert "data-lisa-allowance=" in body
    assert "data-lisa-used=" in body
    assert 'data-wrapper="Lifetime ISA"' in body
    assert "data-lump-sum-lisa-hint" in body

    js = client.get("/static/js/app.js").get_data(as_text=True)
    assert "initLisaLumpSumHint" in js
    assert "data-lisa-allowance" in js


# ── Bonus timing and allocation ─────────────────────────────────────────────
# The 25% bonus is not credited on the day you pay in. Providers claim it from
# HMRC and quote roughly 4-9 weeks; the app models 6 weeks, landing two months on.


def test_lisa_bonus_arrival_month_accounts_for_the_provider_window():
    from app.calculations import lisa_bonus_arrival_month

    assert lisa_bonus_arrival_month("2026-06-01") == "2026-08"
    assert lisa_bonus_arrival_month("2026-11-20") == "2027-01"   # rolls into next year
    assert lisa_bonus_arrival_month(None) is None
    assert lisa_bonus_arrival_month("not-a-date") is None


def test_lisa_bonus_per_contribution_stops_at_the_annual_cap():
    from app.calculations import lisa_bonus_by_contribution

    rows = [
        {"id": 1, "amount": 2500, "contribution_date": "2026-05-01", "wrapper_type": "Lifetime ISA"},
        {"id": 2, "amount": 2500, "contribution_date": "2026-07-01", "wrapper_type": "Lifetime ISA"},
    ]
    bonus = lisa_bonus_by_contribution(rows)

    assert bonus[1] == 625.0    # 25% of £2,500
    assert bonus[2] == 375.0    # only £1,500 of it fits under the £4,000 cap
    assert sum(bonus.values()) == 1000.0   # the £1,000 annual maximum


def test_lisa_bonus_ignores_non_lisa_contributions():
    from app.calculations import lisa_bonus_by_contribution

    rows = [
        {"id": 1, "amount": 4000, "contribution_date": "2026-05-01", "wrapper_type": "Stocks & Shares ISA"},
        {"id": 2, "amount": 1000, "contribution_date": "2026-06-01", "wrapper_type": "Lifetime ISA"},
    ]
    bonus = lisa_bonus_by_contribution(rows)

    assert bonus.get(1, 0) == 0
    assert bonus[2] == 250.0


def test_monthly_plan_takes_the_first_slice_of_the_lisa_cap():
    """£1,000 of monthly LISA contributions leave £3,000 of room for a lump sum."""
    from app.calculations import lisa_bonus_by_contribution

    rows = [{"id": 9, "amount": 4000, "contribution_date": "2026-06-01", "wrapper_type": "Lifetime ISA"}]
    bonus = lisa_bonus_by_contribution(rows, monthly_lisa_total=1000.0)

    assert bonus[9] == 750.0   # 25% of the remaining £3,000 room, not 25% of £4,000


def test_isa_usage_reports_the_lisa_bonus_total(app):
    """calculate_isa_usage must expose the bonus it used to leave to the monthly path."""
    from app.calculations import calculate_isa_usage
    from datetime import date

    accounts = [{
        "id": 1, "name": "LISA", "wrapper_type": "Lifetime ISA",
        "monthly_contribution": 0, "monthly_cash_park": 0, "category": "Investment",
    }]
    contributions = [{
        "id": 1, "account_id": 1, "amount": 4000, "contribution_date": "2026-06-01",
        "wrapper_type": "Lifetime ISA",
    }]

    usage = calculate_isa_usage(accounts, contributions, date(2026, 6, 15), 0)

    assert usage["lisa_used"] == 4000.0
    assert usage["lisa_bonus_total"] == 1000.0
    assert usage["adhoc_lisa_bonus"] == 1000.0


def test_allowance_page_shows_bonus_and_expected_month(app, client, make_user):
    from app.models import create_account, add_isa_contribution

    uid, username, password = make_user(username="lisa-bonus-ui", password="password123")
    _set_age(app, uid)
    with app.app_context():
        account_id = create_account(_account("My Lifetime ISA", "Lifetime ISA"), uid)
        add_isa_contribution(uid, account_id, 4000, "2026-06-01", "annual lump sum")

    _login(client, username, password)
    body = client.get("/allowance/").get_data(as_text=True)

    assert "government bonus earned so far" in body
    assert "1,000.00" in body          # the bonus total
    assert "expected 2026-08" in body  # six weeks later, at month resolution
