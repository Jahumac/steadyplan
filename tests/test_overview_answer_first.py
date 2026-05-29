from datetime import date


def test_overview_getting_started_card_prioritises_basics_and_defers_deeper_steps(app, client, make_user):
    _, username, password = make_user(username="overview-onboarding-new", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Start here" in html
    assert "You only need the basics to begin." in html
    assert "Essential to start" in html
    assert "Do later" in html
    assert "Complete your profile" in html
    assert "Add your first account" in html
    assert "Set a goal once you know what you want to aim for." in html
    assert "Do your first monthly update after your first contribution or balance change settles." in html
    assert 'href="/settings/?mode=edit"' in html


def test_overview_getting_started_primary_action_moves_to_first_incomplete_basic_step(app, client, make_user):
    uid, username, password = make_user(username="overview-onboarding-profile", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01' WHERE user_id = ?",
                (uid,),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Add your first account" in html
    assert "Start with one real account so Overview has something concrete to show." in html
    assert "Add account" in html
    assert 'href="/accounts/?mode=create"' in html


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
