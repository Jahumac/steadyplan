def _login_for_mobile_cleanup(client, make_user, username):
    _, username, password = make_user(username=username, password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)


def test_projections_marks_global_month_strip_for_mobile_hiding(app, client, make_user):
    uid, username, password = make_user(username="projections-mobile", password="password123")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE assumptions
                SET annual_growth_rate = 0.07,
                    retirement_age = 60,
                    date_of_birth = '1980-01-01',
                    retirement_date_mode = 'end_of_tax_year'
                WHERE user_id = ?
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, fund_fee_pct, is_active)
                VALUES (?, 'Vanguard ISA', 'Stocks & Shares ISA', 10000, 500, 0.50, 1)
                """,
                (uid,),
            )
            conn.commit()

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/projections/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert '<section class="budget-year-strip month-strip-global month-strip-mobile-hidden' in html
    assert '<p class="eyebrow">Projections</p>' in html
    assert '<summary>Assumptions</summary>' in html
    assert '<summary>Account breakdown</summary>' in html
    assert '<summary>Growth curve</summary>' in html
    assert '<summary>Scenario planner</summary>' in html
    assert 'class="card mb-1 projections-desktop-detail"' in html
    assert 'class="projections-compact-details projections-compact-only mb-1"' in html
    assert 'id="projectionChartMobile"' in html
    assert 'id="wi_age_mobile"' in html
    assert 'id="wi_reset_mobile"' in html

    css = open("/opt/data/steadyplan/app/static/css/styles.css").read()
    assert ".projections-compact-only {" in css
    assert ".projections-desktop-detail {" in css
    assert ".projections-compact-details summary::after {" in css
    assert "display: block !important;" in css


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
