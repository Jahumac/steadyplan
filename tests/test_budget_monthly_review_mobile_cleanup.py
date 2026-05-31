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
    assert "CSV import" in html
    assert "CSV Import" not in html
    assert "Update tools" not in html


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
    assert '<details class="monthly-review-secondary-details" open>' not in html
    assert "Premium Bonds" in html
    assert "<h2>Prize draw results</h2>" in html
    assert "<h2>Prize Draw Results</h2>" not in html
    assert ">Log prize result<" in html
    assert ">Log prize<" not in html
    assert "<p class=\"eyebrow\">CSV import</p>" in html
    assert "<p class=\"eyebrow\">Shortcut</p>" not in html
    assert "<h2>CSV import</h2>" in html
    assert "<h2>CSV Import</h2>" not in html
    assert "<span class=\"badge badge-meta\">CSV import</span>" in html
    assert "Update tools" not in html
    assert "Open CSV import" in html
    assert 'id="csv-import-cancel">Hide CSV import<' in html
    assert 'id="csv-import-cancel">Cancel<' not in html
    assert ">CSV file<" in html
    assert ">CSV File<" not in html
    assert ">Preview import<" in html
    assert ">Preview Import<" not in html
    assert ">Show<" not in html



def test_monthly_review_places_finish_step_after_update_sections(app, client, make_user):
    _, username, password = make_user(username="review-finish-order", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/monthly-review/?month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    expected_idx = html.index("Expected contributions")
    manual_idx = html.index("Manual balances")
    note_idx = html.index("Monthly note")

    assert expected_idx < manual_idx < note_idx


def test_monthly_review_places_mark_reviewed_action_in_finish_section(app, client, make_user):
    _, username, password = make_user(username="review-finish-action", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/monthly-review/?month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    note_idx = html.index("Monthly note")
    mark_idx = html.index("Mark month reviewed")

    assert '<p class="eyebrow">Monthly note</p>' in html
    assert '<p class="eyebrow">Notes</p>' not in html
    assert note_idx < mark_idx


def test_monthly_review_start_here_update_link_targets_first_update_section(app, client, make_user):
    _, username, password = make_user(username="review-update-anchor", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/monthly-review/?month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'href="#update-balances"' in html
    assert 'id="update-balances"' in html

    contributions_idx = html.index("Expected contributions")
    update_idx = html.index('id="update-balances"')
    manual_idx = html.index("Manual balances")

    assert contributions_idx < update_idx < manual_idx


def test_monthly_review_first_update_section_uses_update_balances_heading(app, client, make_user):
    _, username, password = make_user(username="review-update-heading", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/monthly-review/?month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert '<p class="eyebrow">Update balances</p>' in html
    assert '<p class="eyebrow">Step 2</p>' not in html
    assert "<h2>Update balances</h2>" in html
    assert "Holdings-Based Accounts" not in html


def test_monthly_review_manual_section_uses_manual_balances_heading(app, client, make_user):
    _, username, password = make_user(username="review-manual-heading", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/monthly-review/?month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert '<p class="eyebrow">Manual balances</p>' in html
    assert '<p class="eyebrow">Manual</p>' not in html
    assert "<h2>Manual balances</h2>" in html
    assert "Manual Accounts" not in html


def test_monthly_review_manual_balance_field_uses_sentence_case_label(app, client, make_user):
    uid, username, password = make_user(username="review-manual-balance-label", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, valuation_mode, current_value, is_active)
                VALUES (?, 'Cash pot', 'manual', 2500, 1)
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/monthly-review/?month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert ">Current balance<" in html
    assert ">Current Balance<" not in html
    assert ">Update balance<" in html
    assert ">Update<" not in html


def test_monthly_review_update_balances_uses_refresh_prices_now_cta(app, client, make_user):
    uid, username, password = make_user(username="review-refresh-prices", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, valuation_mode, current_value, is_active)
                VALUES (?, 'Holdings', 'holdings', 0, 1)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO holdings (account_id, holding_name, ticker, value, units, price)
                VALUES (?, 'VUSA', 'VUSA', 1000, 10, 100)
                """,
                (account_id,),
            )
            conn.commit()

    resp = client.get("/monthly-review/?month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Refresh prices now" in html
    assert ">Update holding<" in html
    assert ">Save<" not in html
    assert "↻ Update All Prices" not in html


def test_monthly_review_finish_shortcuts_match_final_step_wording(app, client, make_user):
    _, username, password = make_user(username="review-finish-shortcut", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/monthly-review/?month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert html.count('href="#monthly-note"') >= 2
    assert "Save a note and mark reviewed" in html
    assert "Save note and mark reviewed" not in html
    assert "Save note and finish" not in html
    assert "Finish review" not in html


def test_monthly_review_manual_balances_shortcut_matches_section_anchor_and_heading(app, client, make_user):
    _, username, password = make_user(username="review-manual-shortcut", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/monthly-review/?month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'href="#manual-balances"' in html
    assert 'id="manual-balances"' in html
    assert ">Manual balances<" in html
    assert "jump to manual balances when needed." in html
    assert 'href="#manual-accounts"' not in html
    assert "Update manual balances" not in html
    assert "No manual balances to review this month." in html
    assert "No manual accounts to review this month." not in html
