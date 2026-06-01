def _login_for_mobile_cleanup(client, make_user, username):
    _, username, password = make_user(username=username, password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)


def test_projections_marks_global_month_strip_for_mobile_hiding(app, client, make_user):
    _login_for_mobile_cleanup(client, make_user, "projections-mobile")

    resp = client.get("/projections/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert '<section class="budget-year-strip month-strip-global month-strip-mobile-hidden' in html
    assert '<p class="eyebrow">Projections</p>' in html


def test_performance_marks_global_month_strip_for_mobile_hiding(app, client, make_user):
    _login_for_mobile_cleanup(client, make_user, "performance-mobile")

    resp = client.get("/performance/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert '<section class="budget-year-strip month-strip-global month-strip-mobile-hidden' in html
    assert '<p class="eyebrow">On track vs. plan</p>' in html


def test_contribution_history_marks_global_month_strip_for_mobile_hiding(app, client, make_user):
    _login_for_mobile_cleanup(client, make_user, "contrib-mobile")

    resp = client.get("/performance/contributions/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert '<section class="budget-year-strip month-strip-global month-strip-mobile-hidden' in html
    assert 'Contribution Summary' in html
