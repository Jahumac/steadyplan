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

    assert '<title>Monthly Update · SteadyPlan</title>' in html
    assert '<title>Monthly review · SteadyPlan</title>' not in html
    assert 'href="/monthly-review/" class="subnav-active">Monthly Update</a>' in html
    assert 'href="/monthly-review/" class="subnav-active">Monthly review</a>' not in html
    assert '<p class="eyebrow">Monthly Update</p>' in html
    assert '<p class="eyebrow">Monthly review</p>' not in html
    assert '<span>Monthly update status</span>' in html
    assert '<span>Review status</span>' not in html
    assert '<div class="hero-strip-stat">\n      <span>Status</span>' not in html
    assert '<strong>Not started</strong>' in html
    assert '<strong>In progress</strong>' not in html
    assert '<span>From you</span>' in html
    assert '<span>Monthly in</span>' not in html
    assert '<span>Accounts to update</span>' in html
    assert '<span>Accounts to review</span>' not in html
    assert '<div class="hero-strip-stat">\n      <span>Accounts</span>' not in html
    assert "1. Confirm contributions" in html
    assert "Confirm anything that happened this month." in html
    assert "Tick off anything that happened this month." not in html
    assert 'href="#expected-contributions" class="badge">Expected contributions</a>' in html
    assert 'href="#expected-contributions" class="badge">Confirm contributions</a>' not in html
    assert "2. Update balances" in html
    assert "3. Save a note and mark this month reviewed" in html
    assert "3. Save a note and mark reviewed" not in html
    assert "Work top to bottom: confirm expected contributions, update holdings or manual balances, log prize draw results if needed, then add a note and mark this month reviewed." in html
    assert "Work top to bottom: confirm expected contributions, update holdings or manual balances, log prize draw results if needed, then add a note and mark the month reviewed." not in html
    assert "Work down the page: confirm expected contributions" not in html
    assert "Still to do: 0 contributions to confirm · 0 accounts to update" in html
    assert "Still to do: 0 contributions to confirm · 0 accounts not updated" not in html
    assert "To do: 0 contributions to confirm · 0 accounts to update" not in html
    assert "Leave a quick reminder, then mark your monthly update complete when you are happy." in html
    assert "Leave a quick reminder, then mark this month reviewed when you are happy." not in html
    assert "Leave a quick reminder, then mark the month reviewed when you are happy." not in html
    assert "Leave a quick reminder, then lock the month when you are happy." not in html
    assert 'href="#monthly-note" class="badge badge-primary-action">Save a note and mark monthly update complete</a>' in html
    assert 'href="#monthly-note" class="badge badge-primary-action">Save a note and mark this month reviewed</a>' not in html
    assert 'href="#monthly-note" class="badge badge-primary-action">Save a note and mark reviewed</a>' not in html
    assert 'href="#monthly-note" class="badge badge-meta">Save a note and mark this month reviewed</a>' in html
    assert 'href="#monthly-note" class="badge badge-meta">Save a note and mark reviewed</a>' not in html
    assert "Confirm expected contributions that happened this month. This is a review flag (not a transaction record). Update holdings or manual balances below where needed." in html
    assert "Confirm expected contributions that happened this month. This is a review flag (not a transaction record). Update holdings or balances below where needed." not in html
    assert "No contributions to track this month." in html
    assert "Set them up in <a href=\"/accounts/\" class=\"link-accent\">Accounts</a> and they’ll appear here for your monthly update.</p>" in html
    assert "Set them up in <a href=\"/accounts/\" class=\"link-accent\">Accounts</a> and they’ll appear here.</p>" not in html
    assert "log prize draw results if needed" in html
    assert "log Premium Bonds if needed" not in html
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
    assert '<span class="badge badge-meta">Prize draw results</span>' in html
    assert '<span class="badge badge-meta">Premium Bonds</span>' not in html
    assert 'Log prize draw results and update balances' in html
    assert 'Prize draw results and balance updates' not in html
    assert 'Open account' in html
    assert 'Review account' not in html
    assert '<p class="eyebrow">Prize draw results</p>' in html
    assert '<p class="eyebrow">Premium Bonds</p>' not in html
    assert "<h2>Prize draw results</h2>" in html
    assert "<h2>Prize Draw Results</h2>" not in html
    assert "Prize result not logged" in html
    assert "Prize not logged" not in html
    assert ">Prize result (£)<" in html
    assert ">Prize this month (£)<" not in html
    assert "Enter 0 if no prize won this month" in html
    assert "Enter 0 if no win this month" not in html
    assert ">Current balance (£)<" in html
    assert ">Current NS&amp;I balance (£)<" not in html
    assert ">Log prize result<" in html
    assert ">Log prize<" not in html
    assert "<p class=\"eyebrow\">CSV import</p>" in html
    assert "<p class=\"eyebrow\">Shortcut</p>" not in html
    assert "<h2>CSV import</h2>" in html
    assert "<h2>CSV Import</h2>" not in html
    assert "<span class=\"badge badge-meta\">CSV import</span>" in html
    assert "Preview CSV imports for bigger holdings updates" in html
    assert "CSV import for bigger holdings updates" not in html
    assert "Update tools" not in html
    assert "Open CSV import" in html
    assert 'id="csv-import-cancel">Hide CSV import<' in html
    assert 'id="csv-import-cancel">Cancel<' not in html
    assert ">CSV file<" in html
    assert ">CSV File<" not in html
    assert ">Preview import<" in html
    assert ">Preview Import<" not in html
    assert ">Show<" not in html



def test_monthly_review_zero_prize_result_uses_outcome_badge_wording(app, client, make_user):
    uid, username, password = make_user(username="review-zero-prize-badge", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, valuation_mode, current_value, is_active)
                VALUES (?, 'PB Zero', 'Premium Bonds', 'premium_bonds', 1000, 1)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO premium_bonds_prizes (user_id, account_id, month_key, prize_amount, logged_at)
                VALUES (?, ?, '2026-04', 0, '2026-04-01T00:00:00')
                """,
                (uid, account_id),
            )
            conn.commit()

    resp = client.get("/monthly-review/?month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "No prize won" in html
    assert "No win logged" not in html
    assert ">Update prize result<" in html


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
    mark_idx = html.index("Mark monthly update complete")

    assert '<p class="eyebrow">Monthly note</p>' in html
    assert '<p class="eyebrow">Notes</p>' not in html
    assert '>Save monthly note<' in html
    assert '>Save note<' not in html
    assert '>Mark monthly update complete<' in html
    assert '>Mark this month reviewed<' not in html
    assert '>Mark reviewed<' not in html
    assert '>Mark month reviewed<' not in html
    assert '<h3>Mark ' in html
    assert ' monthly update complete?</h3>' in html
    assert ' reviewed?</h3>' not in html
    assert 'id="confirm-complete-yes">Yes, mark monthly update complete<' in html
    assert 'id="confirm-complete-yes">Yes, mark this month reviewed<' not in html
    assert 'id="confirm-complete-yes">Yes, mark reviewed<' not in html
    assert 'id="confirm-complete-no">Keep monthly update open<' in html
    assert 'id="confirm-complete-no">Keep reviewing<' not in html
    assert 'id="confirm-complete-no">Cancel<' not in html
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


def test_monthly_review_completed_state_uses_complete_badge_in_monthly_note_section(app, client, make_user):
    _, username, password = make_user(username="review-complete-badge", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.post(
        "/monthly-review/",
        data={
            "form_name": "mark_complete",
            "month": "2026-04",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert '>Complete<' in html
    assert '>Locked<' not in html
    assert '>Reopen monthly update<' in html
    assert '>Reopen review<' not in html
    assert 'data-confirm-title="Reopen monthly update?"' in html
    assert 'data-confirm-title="Reopen review?"' not in html
    assert 'data-confirm-ok="Yes, reopen monthly update"' in html
    assert 'data-confirm-ok="Yes, reopen review"' not in html
    assert 'data-confirm-cancel="Keep monthly update complete">Reopen monthly update<' in html
    assert 'data-confirm-cancel="Keep review complete">Reopen review<' not in html


def test_monthly_review_expected_contributions_section_uses_expected_contributions_heading(app, client, make_user):
    _, username, password = make_user(username="review-contributions-heading", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/monthly-review/?month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert '<p class="eyebrow">Expected contributions</p>' in html
    assert '<p class="eyebrow">To confirm</p>' not in html
    assert "<h2>Expected contributions</h2>" in html


def test_monthly_review_contribution_checkbox_uses_explicit_label(app, client, make_user):
    uid, username, password = make_user(username="review-confirm-contribution-label", password="password123")
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

    assert '<span class="helper-text m-0">Confirm contribution</span>' in html
    assert '<span class="helper-text m-0">Confirm</span>' not in html
    assert 'title="Confirm contribution happened"' in html
    assert 'class="badge badge-sm contribution-skip-btn">Skip this month<' in html
    assert 'class="badge badge-sm contribution-skip-btn">Skip<' not in html
    assert '<p class="helper-text m-0">Contribution not confirmed</p>' in html
    assert '<p class="helper-text m-0">Not confirmed</p>' not in html


def test_monthly_review_confirmed_contribution_uses_explicit_status_label(app, client, make_user):
    uid, username, password = make_user(username="review-confirmed-contribution-label", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, valuation_mode, monthly_contribution, current_value, is_active)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 'manual', 150, 1000, 1)
                """,
                (uid,),
            ).lastrowid
            review_id = conn.execute(
                """
                INSERT INTO monthly_reviews (user_id, month_key, status, created_at, updated_at)
                VALUES (?, '2026-04', 'in_progress', datetime('now'), datetime('now'))
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO monthly_review_items (
                    review_id, account_id, expected_contribution,
                    contribution_confirmed, holdings_updated, balance_updated, notes
                )
                VALUES (?, ?, 150, 1, 0, 0, '')
                """,
                (review_id, account_id),
            )
            conn.commit()

    resp = client.get("/monthly-review/?month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert '<p class="helper-text m-0">Contribution confirmed</p>' in html
    assert '<p class="helper-text m-0">Confirmed</p>' not in html


def test_monthly_review_first_update_section_uses_update_balances_heading(app, client, make_user):
    _, username, password = make_user(username="review-update-heading", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/monthly-review/?month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert '<p class="eyebrow">Update balances</p>' in html
    assert '<p class="eyebrow">Step 2</p>' not in html
    assert "<h2>Update balances</h2>" in html
    assert "Update holdings-based accounts first, then continue to any manual balances below." in html
    assert "Start with holdings-based accounts, then continue to any manual balances below." not in html
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
    assert "Update balances for manually valued accounts." in html
    assert "Update balances for accounts that are valued manually." not in html
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

    assert ">Current balance (£)<" in html
    assert ">Current Balance<" not in html
    assert ">Update balance<" in html
    assert "Open account" in html
    assert "Review account" not in html
    assert ">Current balance<" not in html
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
    assert 'title="Refresh latest price"' in html
    assert 'title="Fetch latest price"' not in html
    assert ">Latest price<" in html
    assert ">Price<" not in html
    assert ">Current value<" in html
    assert ">Value<" not in html
    assert ">Update holding<" in html
    assert "Open account" in html
    assert "Review account" not in html
    assert ">Save<" not in html
    assert "↻ Update All Prices" not in html


def test_monthly_review_empty_holdings_state_uses_explicit_add_account_cta(app, client, make_user):
    _, username, password = make_user(username="review-empty-holdings", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/monthly-review/?month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "No holdings-based accounts" in html
    assert "appear here ready for your monthly update" in html
    assert "show up ready for your monthly update" not in html
    assert "ready for your monthly check-in" not in html
    assert ">Add a holdings-based account<" in html
    assert ">Add holdings-based account<" not in html
    assert ">+ Add account<" not in html


def test_monthly_review_empty_account_helper_uses_monthly_update_wording(app, client, make_user):
    uid, username, password = make_user(username="review-empty-account-helper", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, valuation_mode, current_value, is_active)
                VALUES (?, 'Holdings shell', 'holdings', 0, 1)
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/monthly-review/?month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "No holdings here yet." in html
    assert "Add holdings in <a href=\"/accounts/\" class=\"link-accent\">Accounts</a> and they’ll appear here for your monthly update.</p>" in html
    assert "Add some in <a href=\"/accounts/\" class=\"link-accent\">Accounts</a> and they’ll appear here for your monthly update.</p>" not in html
    assert "show up for your monthly update" not in html
    assert "show up for your next update" not in html


def test_monthly_review_finish_shortcuts_match_final_step_wording(app, client, make_user):
    _, username, password = make_user(username="review-finish-shortcut", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/monthly-review/?month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert html.count('href="#monthly-note"') >= 2
    assert "Save a note and mark this month reviewed" in html
    assert "Save a note and mark reviewed" not in html
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
    assert "Update holdings or jump to manual balances when needed." in html
    assert "Open holdings or jump to manual balances when needed." not in html
    assert 'href="#manual-accounts"' not in html
    assert "Update manual balances" not in html
    assert "No manual balances to update this month." in html
    assert "No manual balances to review this month." not in html
    assert "If you add any manually valued accounts, they’ll appear here for your monthly update." in html
    assert "If you add any manually valued accounts, they’ll appear here." not in html
    assert "If you add any manual-value accounts, they’ll appear here." not in html
    assert "No manual accounts to review this month." not in html
