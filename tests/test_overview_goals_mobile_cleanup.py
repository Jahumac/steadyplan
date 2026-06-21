from datetime import date


from tests.path_helpers import STATIC_ROOT
def test_overview_marks_global_month_strip_for_mobile_hiding(app, client, make_user):
    _, username, password = make_user(username="overview-mobile", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert '<section class="budget-year-strip month-strip-global month-strip-mobile-hidden' in html


def test_goals_page_moves_primary_action_into_hero_for_mobile_cleanup(app, client, make_user):
    _, username, password = make_user(username="goals-mobile", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/goals/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert '<section class="budget-year-strip month-strip-global month-strip-mobile-hidden' in html
    assert '<section class="subnav-mobile-family subnav-mobile-family-goals" aria-label="Progress views">' in html
    assert 'class="subnav-mobile-current"' not in html
    assert 'href="/projections/">Future estimates</a>' in html
    assert 'href="/projections/">Projections</a>' not in html
    assert 'class="hero-actions-col goals-hero-actions"' in html
    assert 'class="badge-row goals-hero-badges"' in html
    assert 'href="/goals/?mode=create&amp;focus=first_goal">+ Create goal</a>' in html
    assert 'href="/goals/?mode=create">+ Create goal</a>' not in html
    assert '<div class="row-end">' not in html

    css = STATIC_ROOT.joinpath("css/styles.css").read_text()
    assert ".goals-hero-actions {" in css
    assert "flex-direction: column;" in css
    assert ".goals-hero-badges .badge {" in css
    assert ".subnav-mobile-family-goals .subnav-mobile-panel .badge {" in css
    assert ".empty-state-icon {" not in css

    hero_idx = html.index('class="hero-actions-col goals-hero-actions"')
    create_idx = html.index('href="/goals/?mode=create&amp;focus=first_goal">+ Create goal</a>')
    empty_state_idx = html.index('No goals yet')

    assert hero_idx < create_idx < empty_state_idx
    empty_state_block = html.split('class="empty-state"', 1)[1].split('</div>', 1)[0]
    assert 'empty-state-icon' not in empty_state_block
    assert 'shelly-inline-icon' not in empty_state_block


def test_goals_page_uses_two_column_goal_grid_on_larger_mobile_widths(app, client, make_user):
    uid, username, password = make_user(username="goals-tablet-grid", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes) VALUES (?, 'Retirement Goal', 1000000, '', '', '')",
                (uid,),
            )
            conn.execute(
                "INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes) VALUES (?, 'Emergency Fund', 20000, '', '', '')",
                (uid,),
            )
            conn.commit()

    resp = client.get("/goals/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'class="card-grid goal-grid"' in html
    assert html.count('class="card goal-link-card"') == 2
    assert 'Retirement Goal' in html
    assert 'Emergency Fund' in html

    css = STATIC_ROOT.joinpath("css/styles.css").read_text()
    assert ".goal-grid {" in css
    assert "grid-template-columns: repeat(auto-fit, minmax(260px, 320px));" in css
    assert "@media (min-width: 600px) and (max-width: 900px) {" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in css
    assert "justify-content: stretch;" in css


def test_goals_page_uses_compact_summary_first_cards(app, client, make_user):
    uid, username, password = make_user(username="goals-summary-first", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO accounts (user_id, name, wrapper_type, tags, current_value, monthly_contribution, is_active) VALUES (?, 'ISA', 'Stocks & Shares ISA', 'goal-tag,second-tag,third-tag', 1200, 100, 1)",
                (uid,),
            )
            conn.execute(
                "INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes) VALUES (?, 'Emergency Fund', 5000, 'Tagged Goal', 'goal-tag,second-tag,third-tag', 'This note should stay visible.')",
                (uid,),
            )
            conn.commit()

    resp = client.get("/goals/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'class="goal-progress-summary"' in html
    assert 'class="goal-status-line"' in html
    assert 'class="goal-status-label"' in html
    assert 'class="goal-status-detail"' in html
    assert 'class="goal-chip-row"' in html
    assert 'class="goal-card-note helper-text"' in html
    assert 'class="goal-chip-overflow badge badge-tag"' in html
    assert '>+1 more<' in html

    css = STATIC_ROOT.joinpath("css/styles.css").read_text()
    assert ".goal-link-card {" in css
    assert "display: grid;" in css
    assert ".goal-progress-summary {" in css
    assert ".goal-status-line {" in css
    assert ".goal-status-label {" in css
    assert ".goal-status-detail {" in css
    assert ".goal-chip-row {" in css
    assert ".goal-chip-overflow {" in css
    assert ".goal-card-note {" in css


def test_overview_moves_portfolio_value_up_and_uses_mobile_details_sections(app, client, make_user):
    uid, username, password = make_user(username="overview-mobile-details", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01' WHERE user_id = ?",
                (uid,),
            )
            conn.executemany(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, ?, ?, ?, 1, 'manual')
                """,
                [
                    (uid, 'ISA', 'Stocks & Shares ISA', 1000),
                    (uid, 'Pension', 'SIPP', 2000),
                ],
            )
            conn.executemany(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, ?, ?, '', '', '')
                """,
                [
                    (uid, 'Emergency fund', 5000),
                    (uid, 'House deposit', 20000),
                ],
            )
            conn.execute(
                """
                INSERT INTO portfolio_daily_snapshots (user_id, snapshot_date, total_value)
                VALUES (?, date('now'), ?)
                """,
                (uid, 3000),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'class="card mb-1 overview-portfolio-card"' in html
    assert '<details class="overview-compact-details overview-compact-only mb-1" open>' in html
    assert '<summary>Where you stand now</summary>' in html
    assert html.count('<details class="overview-compact-details overview-compact-only mb-1" open>') == 2
    assert html.count('<h2>Where you stand now</h2>') == 2
    assert 'Accessible vs locked' not in html
    assert '<summary>Goal progress</summary>' in html
    assert '<details class="overview-compact-details overview-compact-only mb-1" open>\n  <summary>Goal progress</summary>' in html
    assert '<summary>Goals</summary>' not in html
    assert '<summary>Tax allowance progress</summary>' in html
    assert '<details class="overview-compact-details overview-compact-only mb-1">\n  <summary>Tax allowance progress</summary>' in html
    assert '<summary>Tax allowances</summary>' not in html
    assert '<summary>Allowances</summary>' not in html
    assert html.count('includes Lifetime ISA') == 2
    assert 'includes LISA' not in html
    assert html.count('<h2>Pension annual allowance ') == 2
    assert '<h2>Pension allowance ' not in html
    assert html.count('aria-label="Pension annual allowance used"') == 2
    assert 'aria-label="Pension allowance used"' not in html
    assert '<summary>Accounts breakdown</summary>' in html
    assert '<details class="overview-compact-details overview-compact-only mb-1">\n  <summary>Accounts breakdown</summary>' in html
    assert html.count('<p class="eyebrow">Accounts breakdown</p>') == 2
    assert html.count('<h2>Accounts breakdown</h2>') == 2
    assert '<h2>Accounts</h2>' not in html
    assert '<p class="eyebrow">Breakdown</p>' not in html
    assert html.count('<p class="eyebrow">Goal progress</p>') == 2
    assert html.count('<h2>Goal progress</h2>') == 2
    assert 'goal-track-label' in html
    assert 'goal-track-detail' in html
    assert '<p class="eyebrow">Goals</p>' not in html
    assert 'class="card mb-1 overview-access-card overview-desktop-detail"' in html
    assert 'class="card-grid allowance-grid mb-1 overview-desktop-detail"' in html

    css = STATIC_ROOT.joinpath("css/styles.css").read_text()
    assert ".goal-track-status {" in css
    assert "flex-wrap: wrap;" in css
    assert ".goal-track-label {" in css
    assert ".goal-track-detail {" in css
    assert "@media (max-width: 480px) {" in css
    assert "gap: 0.6rem;" in css

    hero_idx = html.index('class="card highlight mb-1 month-accent-')
    access_idx = html.index('class="card mb-1 overview-access-card overview-desktop-detail"')
    accounts_idx = html.index('<h2>Accounts breakdown</h2>')
    portfolio_idx = html.index('class="card mb-1 overview-portfolio-card"')

    assert hero_idx < access_idx < accounts_idx < portfolio_idx
    assert 'overview-focus-card' not in html

    css = STATIC_ROOT.joinpath("css/styles.css").read_text()
    assert ".overview-compact-only {" in css
    assert ".overview-desktop-detail {" in css
    assert ".overview-compact-details," in css
    assert ".overview-compact-details summary::after" in css
    assert "display: block !important;" in css


def test_overview_lifetime_isa_review_cta_stays_aligned_in_mobile_details(app, client, make_user):
    uid, username, password = make_user(username="overview-mobile-lifetime-isa-review-cta", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")
    today_str = date.today().strftime("%Y-%m-%d")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE assumptions
                SET date_of_birth = '1990-01-01', salary_day = 1, isa_allowance = 20000, lisa_allowance = 4000
                WHERE user_id = ?
                """,
                (uid,),
            )
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'LISA', 'Cash LISA', 1000, 1, 'manual')
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Emergency fund', 5000, '', '', '')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key)
                VALUES (?, ?, ?, ?)
                """,
                (today_str, account_id, 1000, month_key),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert html.count('>Review Lifetime ISA allowance</a>') == 2
    assert '>Review LISA allowance</a>' not in html
    assert html.count('>Record Lifetime ISA top-up</a>') == 2
    assert '>Record LISA top-up</a>' not in html
    assert html.count('aria-label="Lifetime ISA allowance used"') == 2
    assert 'aria-label="LISA allowance used"' not in html
    assert html.count('<h2>Lifetime ISA allowance ') == 2
    assert html.count('<summary>Tax allowance progress</summary>') == 1
