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
    assert "Opening/imported is money already present when tracking started." in body
    assert "Contributed / Initial funding" not in body


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
