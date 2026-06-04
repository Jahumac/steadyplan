from datetime import date

from app.models import save_daily_snapshot


def test_performance_page_keeps_zero_snapshot_empty_state(client, make_user):
    _, username, password = make_user(username="perf-zero-snapshots", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    response = client.get("/performance/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert "No data yet" in body
    assert "Complete two monthly updates to start seeing performance charts" in body
    assert "Open monthly update" in body
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

    assert "One snapshot down" in body
    assert "Your first baseline is saved. Next month's monthly update will start the performance chart." in body
    assert "First baseline saved" in body
    assert "SteadyPlan has your first snapshot." in body
    assert "the performance chart will appear." in body
    assert "Back to overview" in body
    assert "No data yet" not in body
    assert "Open monthly update" not in body
