def test_budget_page_surfaces_primary_editing_guidance_and_collapses_import_export_tools(app, client, make_user):
    _, username, password = make_user(username="budget-mobile", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/budget/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "This month" in html
    assert "Edit numbers below to shape this month." in html
    assert "Budget Setup" in html
    assert "Import / export tools" in html
    assert "Export month" in html
    assert "Import tax year" in html


def test_monthly_review_page_surfaces_start_here_steps_and_hides_secondary_links_behind_details(app, client, make_user):
    _, username, password = make_user(username="review-mobile", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/monthly-review/?month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Start here" in html
    assert "1. Confirm contributions" in html
    assert "2. Update balances" in html
    assert "3. Save a note and mark reviewed" in html
    assert "Related checks" in html
    assert "Review goals" in html
    assert "Review debts" in html
    assert "Review assumptions" in html
    assert "Update tools" in html
    assert "CSV Import" in html


def test_monthly_review_wraps_premium_bonds_and_csv_import_in_secondary_details(app, client, make_user):
    uid, username, password = make_user(username="review-secondary-mobile", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, valuation_mode, current_value, is_active)
                VALUES (?, 'PB', 'Premium Bonds', 'premium_bonds', 1000, 1)
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/monthly-review/?month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'class="monthly-review-secondary-details"' in html
    assert "Update tools" in html
    assert "Premium Bonds" in html
    assert "CSV Import" in html
