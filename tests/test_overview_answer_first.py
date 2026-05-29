from datetime import date


def test_overview_surfaces_accessible_vs_locked_summary(app, client, make_user):
    uid, username, password = make_user(username="overview-access", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 1, 'manual')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'LISA', 'Lifetime ISA', 2000, 1, 'manual')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'Pension', 'SIPP', 3000, 1, 'manual')
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Accessible vs locked" in html
    assert "Open Planning" in html
    assert "Accessible now" in html
    assert "Restricted" in html
    assert "Locked later" in html
    assert "£1,000" in html
    assert "£2,000" in html
    assert "£3,000" in html
    assert "17% of your current total" in html
    assert "Next accessible milestone:" in html
    assert "£20,000" in html


def test_overview_hero_prioritises_access_labels_over_secondary_stats(app, client, make_user):
    uid, username, password = make_user(username="overview-hero", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 10000, 250, 1, 'manual')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO monthly_reviews (user_id, month_key, status)
                VALUES (?, ?, 'complete')
                """,
                (uid, month_key),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Accessible now" in html
    assert "Locked later" in html
    assert "Monthly contributions" in html
    assert "Projected at retirement" in html
    assert "Goal progress" not in html
    assert "Tax Year " not in html
