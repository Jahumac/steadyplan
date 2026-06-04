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


def test_account_detail_keeps_zero_history_empty_state(app, client, make_user):
    uid, username, password = make_user(username="account-zero-history", password="password123")
    with app.app_context():
        account_id = create_account(_account_payload(), uid)

    client.post("/login", data={"username": username, "password": password})
    response = client.get(f"/accounts/{account_id}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "No history yet. Update your account balance or run the price scheduler to start recording daily snapshots." in body
    assert "First baseline saved" not in body
    assert "This account has its first snapshot." not in body


def test_account_detail_acknowledges_first_daily_snapshot(app, client, make_user):
    uid, username, password = make_user(username="account-first-daily-snapshot", password="password123")
    with app.app_context():
        account_id = create_account(_account_payload(), uid)
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO account_daily_snapshots (user_id, account_id, snapshot_date, value) VALUES (?, ?, '2026-05-01', 6000)",
                (uid, account_id),
            )
            conn.commit()

    client.post("/login", data={"username": username, "password": password})
    response = client.get(f"/accounts/{account_id}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "First baseline saved" in body
    assert "This account has its first snapshot." in body
    assert "monthly update and the chart will appear." in body
    assert "Back to overview" in body
    assert "No history yet. Update your account balance or run the price scheduler to start recording daily snapshots." not in body


def test_account_detail_acknowledges_first_monthly_snapshot_without_daily_history(app, client, make_user):
    uid, username, password = make_user(username="account-first-monthly-snapshot", password="password123")
    with app.app_context():
        account_id = create_account(_account_payload(), uid)
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key) VALUES ('2026-05-01', ?, 6000, '2026-05')",
                (account_id,),
            )
            conn.commit()

    client.post("/login", data={"username": username, "password": password})
    response = client.get(f"/accounts/{account_id}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "First baseline saved" in body
    assert "This account has its first snapshot." in body
    assert "monthly update and the chart will appear." in body
    assert "No history yet. Update your account balance or run the price scheduler to start recording daily snapshots." not in body
