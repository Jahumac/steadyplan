from datetime import date

from app.models import save_daily_snapshot


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
