from datetime import date


from tests.path_helpers import STATIC_ROOT
def test_budget_page_moves_primary_editing_guidance_into_hero_for_mobile_cleanup(app, client, make_user):
    _, username, password = make_user(username="budget-mobile", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/budget/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    month_key = date.today().strftime("%Y-%m")

    assert '<section class="subnav-mobile-family subnav-mobile-family-budget" aria-label="Budget views">' in html
    assert 'class="subnav-mobile-current"' not in html
    assert html.count(f'href="/monthly-review/?month={month_key}">Monthly Update</a>') == 2
    assert 'href="/monthly-review/">Monthly Update</a>' not in html
    assert '<section class="budget-year-strip month-strip-mobile-hidden month-accent-' in html
    assert 'class="hero-actions-col budget-hero-actions"' in html
    assert 'class="badge-row budget-hero-badges"' in html
    assert 'class="budget-month-nav budget-hero-month-nav"' in html
    assert 'class="badge badge-meta budget-prev-month"' in html
    assert 'class="badge badge-meta budget-next-month"' in html
    assert 'class="helper-text m-0 budget-hero-mobile-hint">Edit numbers below to shape this month.</p>' in html
    assert 'href="/budget/items/?mode=create&amp;focus=first_budget&amp;month=' in html
    assert 'href="/budget/items/?month=' not in html
    assert "Budget Setup" in html
    assert "Normal edits save as you type." in html
    assert "Just click any number and type to change it for this month." not in html
    assert "Use <em>Budget what-if</em> below for temporary simulations." in html
    assert "Budget Setup</em> is where you add or remove recurring budget lines." in html
    assert "Use <em>Budget Setup</em> only to add or remove budget lines." not in html
    assert "It saves automatically." not in html
    assert "Your take-home pay and any side income. This is the money you can allocate across the rest of the budget." in html
    assert "Your take-home pay and any side income — used to show how much is available to allocate." not in html
    assert "Minimum payments and extra debt overpayments — use this section to track what you plan to repay this month." in html
    assert "Minimum payments and extra chunks you're throwing at debt — every pound here gets you closer to freedom." not in html
    assert "Set aside money for future goals. Items marked <em>linked account</em> use the monthly payment from that account." in html
    assert "Pay yourself first! Items marked <em>linked account</em> pull their amount from your account's monthly contribution." not in html
    assert "Jump to budget" in html
    assert "Import / export tools" in html
    assert "Export month" in html
    assert "Import tax year" in html
    assert '<section class="card mb-1 budget-compact-flow-card">' not in html
    assert '<p class="eyebrow">This month</p>' not in html
    assert "Keep budget editing simple" not in html

    css_files = list(STATIC_ROOT.joinpath("css/modules").glob("*.css"))
    css = "".join(f.read_text() for f in css_files)
    assert ".budget-hero-actions {" in css
    assert "flex-direction: column;" in css
    assert ".subnav-mobile-family {" in css
    assert ".subnav-mobile-family-budget .subnav-mobile-panel .badge," in css
    assert ".subnav-page.subnav-budget," in css
    assert ".budget-hero-badges {" in css
    assert ".budget-hero-badges .badge {" in css
    assert ".budget-hero-mobile-hint {" in css
    assert ".monthly-review-start-details {" in css
    assert ".monthly-review-start-details summary {" in css
    assert ".monthly-review-start-details .compact-flow-list {" in css
    assert ".review-hero-todo {" in css
    assert ".review-hero-todo .badge {" in css
    assert ".contribution-check-main {" in css
    assert ".contribution-check-toggle {" in css
    assert ".contribution-check-side {" in css
    assert ".contribution-check-status {" in css
    assert ".contribution-check-toggle .helper-text {" in css
    assert ".contribution-check-account p {" in css
    assert ".contribution-check-side .badge {" in css
    assert "@media (min-width: 601px) and (max-width: 1024px)" in css
    assert ".subnav-page.subnav-budget {\n    display: grid;\n    grid-template-columns: repeat(3, minmax(0, 1fr));" in css
    assert ".subnav-page.subnav-budget a {\n    white-space: normal;" in css
    assert "@media (max-width: 768px)" in css
    assert "grid-template-columns: minmax(0, 1fr);" in css
    assert "padding-left: 1.7rem;" in css
    assert "justify-content: space-between;" in css
    assert "flex-wrap: wrap;" in css
    assert "white-space: normal;" in css
    assert "display: none;" in css
    assert "justify-content: center;" in css
    assert "margin-bottom: 0.65rem;" in css

    hero_idx = html.index('class="hero-actions-col budget-hero-actions"')
    jump_idx = html.index('href="#income">Jump to budget</a>')
    month_nav_idx = html.index('class="budget-month-nav budget-hero-month-nav"')
    toolbar_idx = html.index('class="budget-toolbar"')

    assert hero_idx < jump_idx < month_nav_idx < toolbar_idx


def test_monthly_review_moves_start_here_flow_into_hero_for_mobile_cleanup(app, client, make_user):
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
    assert '<section class="budget-year-strip month-strip-global month-strip-mobile-hidden' in html
    assert '<div class="hero-strip-stat">\n      <span>Status</span>' not in html
    assert '<strong>Not started</strong>' in html
    assert '<strong>In progress</strong>' not in html
    assert '<span>From you</span>' in html
    assert '<span>Monthly in</span>' not in html
    assert '<span>Accounts to update</span>' in html
    assert '<span>Accounts to review</span>' not in html
    assert '<div class="hero-strip-stat">\n      <span>Accounts</span>' not in html
    assert 'class="review-hero-flow"' in html
    assert 'class="monthly-review-start-details"' in html
    assert '<details class="monthly-review-start-details" open>' not in html
    assert "How to finish this month" in html
    assert "Three short steps: confirm contributions, update balances, then finish with your note." in html
    assert ">Show flow<" in html
    assert "3-step monthly update flow" not in html
    assert 'class="badge-row review-hero-badges"' in html
    assert '<section class="card mb-1 monthly-review-start-card">' not in html
    assert "On a phone, keep the flow narrow: confirm, update, then finish." not in html
    assert "1. Confirm contributions" in html
    assert "Confirm anything that happened this month." in html
    assert "Tick off anything that happened this month." not in html
    assert 'href="#expected-contributions" class="badge">Confirm contributions</a>' in html
    assert 'href="#expected-contributions" class="badge">Contributions</a>' not in html
    assert 'href="#expected-contributions" class="badge">Expected contributions</a>' not in html
    assert 'href="#update-balances" class="badge badge-meta">Update balances</a>' in html
    assert 'href="#update-balances" class="badge badge-meta">Balances</a>' not in html
    assert "2. Update balances" in html
    assert "3. Finish monthly update" in html
    assert "3. Save a note and mark this month reviewed" not in html
    assert "3. Save a note and mark monthly update complete" not in html
    assert "3. Save a note and mark reviewed" not in html
    assert "Confirm contributions, update balances, then finish with your note." in html
    assert "Work top to bottom: confirm expected contributions, update holdings or manual balances, log prize draw results if needed, then add a note and mark monthly update complete." not in html
    assert "Work top to bottom: confirm expected contributions, update holdings or manual balances, log prize draw results if needed, then add a note and mark this month reviewed." not in html
    assert "Work top to bottom: confirm expected contributions, update holdings or manual balances, log prize draw results if needed, then add a note and mark the month reviewed." not in html
    assert "Work down the page: confirm expected contributions" not in html
    assert 'class="review-hero-todo" aria-label="Still to do"' in html
    assert ">0 contributions left<" in html
    assert ">0 accounts left<" in html
    assert "Still to do: 0 contributions to confirm · 0 accounts to update" not in html
    assert "Still to do: 0 contributions to confirm · 0 accounts not updated" not in html
    assert "To do: 0 contributions to confirm · 0 accounts to update" not in html
    assert "Save a quick note, then mark the Monthly Update complete when you are happy." in html
    assert "Leave a quick reminder, then mark this month reviewed when you are happy." not in html
    assert "Leave a quick reminder, then mark the month reviewed when you are happy." not in html
    assert "Leave a quick reminder, then lock the month when you are happy." not in html
    assert 'href="#monthly-note" class="badge badge-primary-action">Finish monthly update</a>' in html
    assert 'href="#monthly-note" class="badge badge-primary-action">Save a note and mark this month reviewed</a>' not in html
    assert 'href="#monthly-note" class="badge badge-primary-action">Save a note and mark reviewed</a>' not in html
    assert 'href="#monthly-note" class="badge badge-meta">Finish monthly update</a>' in html
    assert 'href="#monthly-note" class="badge badge-meta">Finish update</a>' not in html
    assert 'href="#monthly-note" class="badge badge-meta">Save a note and mark this month reviewed</a>' not in html
    assert 'href="#monthly-note" class="badge badge-meta">Save a note and mark reviewed</a>' not in html
    assert 'href="#monthly-note" class="badge badge-meta">Save a note and mark monthly update complete</a>' not in html
    assert "Confirm anything that happened this month. This is a monthly update flag — update balances below if needed." in html
    assert "Confirm expected contributions that happened this month. This is a monthly update flag (not a transaction record). Update holdings or manual balances below where needed." not in html
    assert "Confirm expected contributions that happened this month. This is a review flag (not a transaction record). Update holdings or manual balances below where needed." not in html
    assert "Confirm expected contributions that happened this month. This is a review flag (not a transaction record). Update holdings or balances below where needed." not in html
    assert "No account payments to track this month." in html
    assert "<a href=\"/accounts/?mode=create&amp;focus=first_account\" class=\"link-accent\">Add your first account</a> and set a monthly payment, then it’ll appear here for your Monthly Update.</p>" in html
    assert "Set them up in <a href=\"/accounts/?mode=create&amp;focus=first_account\" class=\"link-accent\">Accounts</a> and they’ll appear here for your Monthly Update.</p>" not in html
    assert "Set them up in <a href=\"/accounts/\" class=\"link-accent\">Accounts</a> and they’ll appear here for your Monthly Update.</p>" not in html
    assert "Set them up in <a href=\"/accounts/?mode=create&amp;focus=first_account\" class=\"link-accent\">Accounts</a> and they’ll appear here.</p>" not in html
    assert "log prize draw results if needed" not in html
    assert "Confirm contributions, update balances, then finish with your note." in html
    assert "log Premium Bonds if needed" not in html
    assert "Related checks" in html
    assert "Create your first goal" in html
    assert "Review goals" not in html
    assert 'href="/goals/?mode=create&amp;focus=first_goal" class="badge badge-meta">Create your first goal</a>' in html
    assert 'href="/goals/" class="badge badge-meta">Review goals</a>' not in html
    assert "Review debts" in html
    assert "Edit planning numbers" in html
    assert 'href="/settings/?mode=edit&amp;focus=scenario_estimate_assumptions"' in html
    assert 'href="/settings/?mode=edit"' not in html
    assert "Review scenario estimate assumptions" not in html
    assert "Review assumptions" not in html
    assert "CSV import" in html
    assert "CSV Import" not in html
    assert "Update tools" not in html

    hero_flow_idx = html.index('class="review-hero-flow"')
    first_section_idx = html.index('id="expected-contributions"')

    assert hero_flow_idx < first_section_idx


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
    assert 'Open prize history' in html
    assert 'Open account' not in html
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


def test_monthly_review_contribution_chip_spells_out_lifetime_isa_bonus(app, client, make_user):
    uid, username, password = make_user(username="review-lifetime-isa-chip", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active)
                VALUES (?, 'House deposit', 'Lifetime ISA', 5000, 100, 1)
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/monthly-review/?month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "+£25.00 Lifetime ISA bonus" in html
    assert "+£25.00 bonus" not in html


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
    mark_idx = html.index("Mark Monthly Update complete")

    assert '<p class="eyebrow">Monthly note</p>' in html
    assert '<p class="eyebrow">Notes</p>' not in html
    assert '>Save monthly note<' in html
    assert '>Save note<' not in html
    assert '>Mark Monthly Update complete<' in html
    assert '>Mark this month reviewed<' not in html
    assert '>Mark reviewed<' not in html
    assert '>Mark month reviewed<' not in html
    assert '<h3>Mark ' in html
    assert ' Monthly Update complete?</h3>' in html
    assert ' reviewed?</h3>' not in html
    assert 'id="confirm-complete-yes">Yes, mark Monthly Update complete<' in html
    assert 'id="confirm-complete-yes">Yes, mark this month reviewed<' not in html
    assert 'id="confirm-complete-yes">Yes, mark reviewed<' not in html
    assert 'id="confirm-complete-no">Keep Monthly Update open<' in html
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
    assert '>Reopen Monthly Update<' in html
    assert '>Reopen review<' not in html
    assert 'data-confirm-title="Reopen Monthly Update?"' in html
    assert 'data-confirm-title="Reopen review?"' not in html
    assert 'data-confirm-ok="Yes, reopen monthly update"' in html
    assert 'data-confirm-ok="Yes, reopen review"' not in html
    assert 'data-confirm-cancel="Keep Monthly Update complete">Reopen Monthly Update<' in html
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

    assert 'class="contribution-check-main"' in html
    assert 'class="contribution-check-toggle flex flex-center gap-05"' in html
    assert 'class="contribution-check-account"' in html
    assert 'class="contribution-check-side"' in html
    assert 'class="contribution-check-status"' in html
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
    assert "Update holdings first, then any manual balances below." in html
    assert "Update holdings-based accounts first, then continue to any manual balances below." not in html
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
    assert "Update manually valued accounts." in html
    assert "Update balances for manually valued accounts." not in html
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
    assert "Open balance" in html
    assert "Open account" not in html
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
    assert "Open holdings" in html
    assert "Open account" not in html
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
    assert "appear here ready for your Monthly Update" in html
    assert "show up ready for your Monthly Update" not in html
    assert "ready for your monthly check-in" not in html
    assert "Add your first holdings account and it’ll appear here ready for your Monthly Update." in html
    assert "Add a holdings-based account and it’ll appear here ready for your Monthly Update." not in html
    assert ">Add your first holdings account<" in html
    assert 'href="/accounts/?mode=create&amp;focus=first_account" class="badge badge-primary-action">Add your first holdings account</a>' in html
    assert 'href="/accounts/" class="badge badge-primary-action">Add your first holdings account</a>' not in html
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
    assert "<a href=\"/accounts/?mode=create&amp;focus=first_account\" class=\"link-accent\">Add your first holdings account</a> and it’ll appear here for your Monthly Update.</p>" in html
    assert "Add holdings in <a href=\"/accounts/?mode=create&amp;focus=first_account\" class=\"link-accent\">Accounts</a> and they’ll appear here for your Monthly Update.</p>" not in html
    assert "Add holdings in <a href=\"/accounts/\" class=\"link-accent\">Accounts</a> and they’ll appear here for your Monthly Update.</p>" not in html
    assert "Add some in <a href=\"/accounts/?mode=create&amp;focus=first_account\" class=\"link-accent\">Accounts</a> and they’ll appear here for your Monthly Update.</p>" not in html
    assert "show up for your Monthly Update" not in html
    assert "show up for your next update" not in html


def test_monthly_review_finish_shortcuts_match_final_step_wording(app, client, make_user):
    _, username, password = make_user(username="review-finish-shortcut", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/monthly-review/?month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert html.count('href="#monthly-note"') >= 2
    assert 'href="#monthly-note" class="badge badge-meta">Finish monthly update</a>' in html
    assert 'href="#monthly-note" class="badge badge-meta">Finish update</a>' not in html
    assert 'href="#monthly-note" class="badge badge-meta">Save a note and mark this month reviewed</a>' not in html
    assert "3. Finish monthly update" in html
    assert "3. Save a note and mark this month reviewed" not in html
    assert "3. Save a note and mark monthly update complete" not in html
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
    assert '>Manual balances<' in html
    assert "Update manually valued accounts." in html
    assert "Update balances for manually valued accounts." not in html
    assert "Update holdings or jump to manual balances when needed." in html

    assert 'href="#manual-accounts"' not in html
    assert "Update manual balances" not in html
    assert "No manual balances to update this month." in html
    assert "No manual balances to review this month." not in html
    assert "<a href=\"/accounts/?mode=create&amp;focus=first_account\" class=\"link-accent\">Add a manually valued account</a> and it’ll appear here for your Monthly Update." in html
    assert "If you add any manually valued accounts in <a href=\"/accounts/?mode=create&amp;focus=first_account\" class=\"link-accent\">Accounts</a>, they’ll appear here for your Monthly Update." not in html
    assert "If you add any manually valued accounts, they’ll appear here for your Monthly Update." not in html
    assert "If you add any manually valued accounts, they’ll appear here." not in html
    assert "If you add any manual-value accounts, they’ll appear here." not in html
    assert "No manual accounts to review this month." not in html
