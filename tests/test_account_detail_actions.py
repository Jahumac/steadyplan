from app.models import create_account, get_connection


def _account_payload():
    return {
        "name": "Stocks & Shares ISA",
        "provider": "Trading 212",
        "wrapper_type": "Stocks & Shares ISA",
        "category": "Investment",
        "tags": "",
        "current_value": 6265.79,
        "monthly_contribution": 1300,
        "pension_contribution_day": 0,
        "goal_value": None,
        "valuation_mode": "holdings",
        "growth_mode": "default",
        "growth_rate_override": None,
        "owner": "Janusz",
        "is_active": 1,
        "notes": "",
        "last_updated": "2026-05-25",
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


def test_account_detail_actions_are_direct_not_overflow_menu(app, client, make_user):
    uid, username, password = make_user()
    with app.app_context():
        account_id = create_account(_account_payload(), uid)

    client.post("/login", data={"username": username, "password": password})
    resp = client.get(f"/accounts/{account_id}")

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "account-detail-actions" in html
    assert "data-overflow" not in html
    assert "acct-overflow" not in html
    assert "More actions" not in html
    assert "?mode=edit" in html
    assert "+ Add holding" in html
    assert "Delete" in html


def test_account_detail_unlinked_holding_badge_uses_plain_refresh_copy(app, client, make_user):
    uid, username, password = make_user(username="account-unlinked-holding-copy", password="password123")
    with app.app_context():
        account_id = create_account(_account_payload(), uid)
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO holdings (account_id, holding_name, ticker, value, units, price) VALUES (?, 'World ETF', 'VWRP', 1000, 10, 100)",
                (account_id,),
            )
            conn.commit()

    client.post("/login", data={"username": username, "password": password})
    resp = client.get(f"/accounts/{account_id}")

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "No price source linked — prices won" in html
    assert "refresh here" in html
    assert "No price source linked — prices won't update automatically" not in html
    assert "no auto-price" in html


def test_account_detail_helper_uses_lifetime_isa_bonus_wording(app, client, make_user):
    uid, username, password = make_user(username="account-lifetime-isa-bonus", password="password123")
    with app.app_context():
        account_id = create_account(_account_payload(), uid)
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO portfolio_daily_snapshots (user_id, snapshot_date, total_value) VALUES (?, '2026-05-01', 6000)",
                (uid,),
            )
            conn.execute(
                "INSERT INTO portfolio_daily_snapshots (user_id, snapshot_date, total_value) VALUES (?, '2026-05-02', 6100)",
                (uid,),
            )
            conn.execute(
                "INSERT INTO account_daily_snapshots (user_id, account_id, snapshot_date, value) VALUES (?, ?, '2026-05-01', 6000)",
                (uid, account_id),
            )
            conn.execute(
                "INSERT INTO account_daily_snapshots (user_id, account_id, snapshot_date, value) VALUES (?, ?, '2026-05-02', 6100)",
                (uid, account_id),
            )
            conn.commit()

    client.post("/login", data={"username": username, "password": password})
    resp = client.get(f"/accounts/{account_id}")

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "includes Lifetime ISA bonus, tax relief, and employer match where applicable" in html
    assert "includes LISA bonus, tax relief, and employer match where applicable" not in html


def test_account_detail_contribution_adjustments_helper_uses_plain_wording(app, client, make_user):
    uid, username, password = make_user(username="account-adjustment-copy", password="password123")
    with app.app_context():
        account_id = create_account(_account_payload(), uid)

    client.post("/login", data={"username": username, "password": password})
    resp = client.get(f"/accounts/{account_id}")

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Below it are any temporary adjustments you've set (e.g. holidays, bonuses)." in html
    assert "Below it are any <em>life-happens</em> adjustments you've set (e.g. holidays, bonuses)." not in html


def test_cash_isa_account_detail_shows_explicit_allowance_effect_selector(app, client, make_user):
    uid, username, password = make_user(username="cash-isa-allowance-selector", password="password123")
    with app.app_context():
        payload = _account_payload()
        payload["name"] = "Cash ISA"
        payload["wrapper_type"] = "Cash ISA"
        payload["valuation_mode"] = "manual"
        account_id = create_account(payload, uid)

    client.post("/login", data={"username": username, "password": password})
    resp = client.get(f"/accounts/{account_id}")

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "ISA allowance effect" in html
    assert "No effect on tracked ISA usage" in html
    assert "Flexible ISA withdrawal restores room" in html
    assert "Nothing is assumed by default." in html


def test_cash_isa_cash_flow_event_stores_explicit_allowance_effect(app, client, make_user):
    uid, username, password = make_user(username="cash-isa-allowance-save", password="password123")
    with app.app_context():
        payload = _account_payload()
        payload["name"] = "Cash ISA"
        payload["wrapper_type"] = "Cash ISA"
        payload["valuation_mode"] = "manual"
        account_id = create_account(payload, uid)

    client.post("/login", data={"username": username, "password": password})
    resp = client.post(
        f"/accounts/{account_id}/cash-events/add",
        data={
            "cash_event_date": "2026-04-10",
            "cash_event_kind": "withdrawal",
            "cash_event_amount": "150",
            "cash_event_allowance_effect": "flexible_withdrawal",
            "cash_event_note": "Move out",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 302
    with app.app_context():
        with get_connection() as conn:
            row = conn.execute(
                "SELECT amount, allowance_effect FROM cash_flow_events WHERE user_id = ? AND account_id = ? ORDER BY id DESC LIMIT 1",
                (uid, account_id),
            ).fetchone()

    assert row["amount"] == -150
    assert row["allowance_effect"] == "flexible_withdrawal"
