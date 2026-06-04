def test_monthly_review_first_use_focus_surfaces_baseline_reassurance(app, client, make_user):
    uid, username, password = make_user(username="monthly-review-first-use", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, valuation_mode, monthly_contribution, current_value, is_active)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 'manual', 150, 1000, 1)
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Emergency fund', 5000, '', '', '')
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/monthly-review/?focus=first_update&month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "<p class=\"eyebrow\">Start here</p>" in html
    assert "Do your first monthly update" in html
    assert "One pass is enough to create your first snapshot." in html
    assert "This screen is just for creating that first honest baseline." in html
    assert "If nothing changed yet, you can come back after your first contribution or balance move settles." in html
    assert "<p class=\"eyebrow\">Monthly Update</p>" not in html
    assert "Confirm contributions, update balances, then finish with your note." in html


def test_monthly_review_without_first_use_focus_keeps_regular_hero(app, client, make_user):
    uid, username, password = make_user(username="monthly-review-regular-hero", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, valuation_mode, monthly_contribution, current_value, is_active)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 'manual', 150, 1000, 1)
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/monthly-review/?month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "<p class=\"eyebrow\">Monthly Update</p>" in html
    assert "<h2 class=\"hero-value\">April 2026</h2>" in html
    assert "Do your first monthly update" not in html
    assert "This screen is just for creating that first honest baseline." not in html
