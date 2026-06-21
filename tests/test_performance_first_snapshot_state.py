from datetime import date, timedelta

from app.models import get_connection, save_daily_snapshot


def test_performance_page_keeps_zero_snapshot_empty_state(client, make_user):
    _, username, password = make_user(username="perf-zero-snapshots", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")
    response = client.get("/performance/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert "No data yet" in body
    assert "Complete two monthly updates to start seeing performance charts" in body
    assert "Open monthly update" in body
    assert f'href="/monthly-review/?month={month_key}#expected-contributions"' in body
    assert f'href="/monthly-review/?month={month_key}">Open monthly update</a>' not in body
    assert 'href="/monthly-review/">Open monthly update</a>' not in body
    assert "One snapshot down" not in body
    assert "First baseline saved" not in body


def test_performance_page_acknowledges_first_snapshot(client, make_user):
    uid, username, password = make_user(username="perf-first-snapshot", password="password123")
    with client.application.app_context():
        save_daily_snapshot(uid, 1000, date.today().isoformat())

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get("/performance/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert "Your first baseline is saved" in body
    assert "Complete next month's monthly update and the performance chart will appear." in body
    assert "Your first baseline is saved. Complete next month's monthly update and the performance chart will appear." not in body
    assert "One snapshot down" not in body
    assert "SteadyPlan has your first snapshot." not in body
    assert "First baseline saved" not in body
    assert "Next month's monthly update will start the performance chart." not in body
    assert "Come back after next month's monthly update and the performance chart will appear." not in body
    month_key = date.today().strftime("%Y-%m")
    assert "Open monthly update" in body
    assert f'href="/monthly-review/?month={month_key}#expected-contributions"' in body
    assert f'href="/monthly-review/?month={month_key}">Open monthly update</a>' not in body
    assert 'href="/monthly-review/">Open monthly update</a>' not in body
    assert "Back to overview" not in body
    assert "No data yet" not in body


def test_performance_page_shows_imported_baseline_reconciliation(client, make_user):
    uid, username, password = make_user(username="perf-imported-summary", password="password123")
    today = date.today()
    prior_day = today - timedelta(days=35)
    current_month = today.strftime("%Y-%m")
    prior_month_day = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    prior_month = prior_month_day.strftime("%Y-%m")

    with client.application.app_context():
        with get_connection() as conn:
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1250, 200, 1)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key) VALUES (?, ?, 1000, ?)",
                (prior_month_day.isoformat(), account_id, prior_month),
            )
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key) VALUES (?, ?, 1250, ?)",
                (today.replace(day=1).isoformat(), account_id, current_month),
            )
            conn.execute(
                """
                INSERT INTO cash_flow_events (user_id, account_id, event_date, amount, kind, note, created_at)
                VALUES (?, ?, ?, 200, 'deposit', 'Monthly deposit', ?)
                """,
                (uid, account_id, today.isoformat(), f"{today.isoformat()}T00:00:00+00:00"),
            )
            conn.commit()
        save_daily_snapshot(uid, 1000, prior_day.isoformat())
        save_daily_snapshot(uid, 1250, today.isoformat())

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get("/performance/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert "Opening / Imported" in body
    assert "£1,000" in body
    assert "Contributed" in body
    assert "£200" in body
    assert "Gain / Interest" in body
    assert "+£50" in body
    assert "Total return" in body
    assert "Annualised return" in body
    assert "Not enough history yet" in body
    assert "Annualised return appears after 12 monthly return periods, so early results do not look falsely dramatic." in body
    assert "Opening/imported is money already present when tracking started." in body
    assert "How to read Performance" in body
    assert "Annualised</strong> appears only after enough history" in body
    assert "Cash ISA uses cash interest; Premium Bonds use prize gain; investment accounts use market gain/loss." in body
    assert "Contributed / Initial funding" not in body


def test_performance_page_renders_historical_movement_form(client, make_user):
    uid, username, password = make_user(username="perf-manual-event-form", password="password123")
    today = date.today()
    current_month = today.strftime("%Y-%m")
    prior_month_day = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    prior_month = prior_month_day.strftime("%Y-%m")

    with client.application.app_context():
        with get_connection() as conn:
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active)
                VALUES (?, 'Premium Bonds', 'Premium Bonds', 800, 0, 1)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key) VALUES (?, ?, 25, ?)",
                (prior_month_day.isoformat(), account_id, prior_month),
            )
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key) VALUES (?, ?, 800, ?)",
                (today.replace(day=1).isoformat(), account_id, current_month),
            )
            conn.commit()
        save_daily_snapshot(uid, 25, prior_month_day.isoformat())
        save_daily_snapshot(uid, 800, today.isoformat())

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get("/performance/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert "Record a historical movement" in body
    assert "Use this when an account was added late or a top-up/withdrawal was missed." in body
    assert "Opening baseline month" in body
    assert "Premium Bonds had £25 before a £775 top-up" in body
    assert "Record movement" in body


def test_performance_page_records_historical_movement_with_opening_baseline(client, make_user):
    uid, username, password = make_user(username="perf-manual-event-submit", password="password123")
    with client.application.app_context():
        with get_connection() as conn:
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active)
                VALUES (?, 'Premium Bonds', 'Premium Bonds', 800, 0, 1)
                """,
                (uid,),
            ).lastrowid
            conn.commit()

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.post(
        "/performance/cash-flow-events",
        data={
            "account_id": str(account_id),
            "event_date": "2026-06-01",
            "kind": "deposit",
            "amount": "775",
            "opening_month": "2026-05",
            "opening_value": "25",
            "note": "One-off PB audit top-up",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Recorded Premium Bonds opening baseline £25.00 and deposit £775.00." in body
    assert "Performance history" in body
    assert "One-off PB audit top-up" in body
    assert "+£775.00" in body
    assert "Remove this Performance movement?" in body

    with client.application.app_context():
        with get_connection() as conn:
            snapshot = conn.execute(
                "SELECT balance FROM monthly_snapshots WHERE account_id = ? AND month_key = '2026-05'",
                (account_id,),
            ).fetchone()
            event = conn.execute(
                "SELECT id, amount, kind, note, allowance_effect FROM cash_flow_events WHERE account_id = ?",
                (account_id,),
            ).fetchone()
    assert snapshot["balance"] == 25
    assert event["amount"] == 775
    assert event["kind"] == "deposit"
    assert event["note"] == "One-off PB audit top-up"
    assert event["allowance_effect"] == "none"

    delete_response = client.post(
        f"/performance/cash-flow-events/{event['id']}/delete",
        follow_redirects=True,
    )
    assert delete_response.status_code == 200
    delete_body = delete_response.get_data(as_text=True)
    assert "Removed that Performance movement. Account balances and snapshots were not changed." in delete_body
    assert "One-off PB audit top-up" not in delete_body

    with client.application.app_context():
        with get_connection() as conn:
            remaining = conn.execute(
                "SELECT COUNT(*) AS count FROM cash_flow_events WHERE account_id = ?",
                (account_id,),
            ).fetchone()["count"]
            snapshot_after_delete = conn.execute(
                "SELECT balance FROM monthly_snapshots WHERE account_id = ? AND month_key = '2026-05'",
                (account_id,),
            ).fetchone()
    assert remaining == 0
    assert snapshot_after_delete["balance"] == 25


def test_performance_page_shows_account_reconciliation_breakdown(client, make_user):
    uid, username, password = make_user(username="perf-account-reconciliation", password="password123")
    today = date.today()
    prior_day = today - timedelta(days=35)
    current_month = today.strftime("%Y-%m")
    prior_month_day = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    prior_month = prior_month_day.strftime("%Y-%m")

    with client.application.app_context():
        with get_connection() as conn:
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active)
                VALUES (?, 'Stocks ISA', 'Stocks & Shares ISA', 1250, 200, 1)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key) VALUES (?, ?, 1000, ?)",
                (prior_month_day.isoformat(), account_id, prior_month),
            )
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key) VALUES (?, ?, 1250, ?)",
                (today.replace(day=1).isoformat(), account_id, current_month),
            )
            conn.execute(
                """
                INSERT INTO cash_flow_events (user_id, account_id, event_date, amount, kind, note, created_at)
                VALUES (?, ?, ?, 200, 'deposit', 'Monthly deposit', ?)
                """,
                (uid, account_id, today.isoformat(), f"{today.isoformat()}T00:00:00+00:00"),
            )
            conn.commit()
        save_daily_snapshot(uid, 1000, prior_day.isoformat())
        save_daily_snapshot(uid, 1250, today.isoformat())

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get("/performance/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert "Account reconciliation" in body
    assert "Shows how each account's current value is explained by opening/imported money, later contributions, and gain/interest." in body
    assert "Stocks ISA" in body
    assert '<td class="num">£1,000</td>' in body
    assert '<td class="num">£200</td>' in body
    assert '<td class="num perf-positive">+£50</td>' in body
    assert '<td class="num text-bold">£1,250</td>' in body
