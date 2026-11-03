from tests.path_helpers import STATIC_ROOT

def _login_for_mobile_cleanup(client, make_user, username):
    _, username, password = make_user(username=username, password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)


def test_the_retirement_forecast_lives_inside_the_house_page(app, client, make_user):
    """It used to be a whole page. It is one collapsed section of Progress now."""
    uid, username, password = make_user(username="projections-mobile", password="password123")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE assumptions SET annual_growth_rate = 0.07, retirement_age = 60,
                    date_of_birth = '1980-01-01', retirement_date_mode = 'end_of_tax_year'
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

    # the old URL still works, it just points at the one screen now
    resp = client.get("/projections/")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/house/#forecast")

    resp = client.get("/house/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'id="forecast"' in html
    assert '<p class="eyebrow">Future estimates</p>' in html
    assert 'id="projectionChartMobile"' in html


def test_plan_vs_actual_lives_inside_the_house_page(app, client, make_user):
    """It used to be a whole page. It is one collapsed section of Progress now."""
    _login_for_mobile_cleanup(client, make_user, "performance-mobile")

    resp = client.get("/performance/")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/house/#history")

    resp = client.get("/house/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="history"' in html
    assert '<p class="eyebrow">Plan comparison</p>' in html


def test_contribution_history_lives_inside_the_house_page(app, client, make_user):
    """It used to be a whole page. It is one collapsed section of Progress now."""
    _login_for_mobile_cleanup(client, make_user, "contrib-mobile")

    resp = client.get("/performance/contributions/")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/house/#contributions")

    resp = client.get("/house/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="contributions"' in html
    assert 'Month-by-month contribution history across all accounts' in html
    assert 'Contribution Summary' not in html


