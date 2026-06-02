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
    assert '<section class="subnav-mobile-family subnav-mobile-family-goals" aria-label="Goals views">' in html
    assert 'class="subnav-mobile-current"' not in html
    assert 'href="/projections/">Projections</a>' in html
    assert 'class="hero-actions-col goals-hero-actions"' in html
    assert 'class="badge-row goals-hero-badges"' in html
    assert 'href="/goals/?mode=create">+ Create goal</a>' in html
    assert '<div class="row-end">' not in html

    css = open("/opt/data/steadyplan/app/static/css/styles.css").read()
    assert ".goals-hero-actions {" in css
    assert "flex-direction: column;" in css
    assert ".goals-hero-badges .badge {" in css
    assert ".subnav-mobile-family-goals .subnav-mobile-panel .badge {" in css
    assert ".empty-state-icon {" not in css

    hero_idx = html.index('class="hero-actions-col goals-hero-actions"')
    create_idx = html.index('href="/goals/?mode=create">+ Create goal</a>')
    empty_state_idx = html.index('No goals yet')

    assert hero_idx < create_idx < empty_state_idx
    empty_state_block = html.split('class="empty-state"', 1)[1].split('</div>', 1)[0]
    assert 'empty-state-icon' not in empty_state_block
    assert 'shelly-inline-icon' not in empty_state_block


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
    assert '<summary>Where you stand now</summary>' in html
    assert '<summary>Goal progress</summary>' in html
    assert '<summary>Goals</summary>' not in html
    assert '<summary>Tax allowance progress</summary>' in html
    assert '<summary>Tax allowances</summary>' not in html
    assert '<summary>Allowances</summary>' not in html
    assert '<summary>Accounts breakdown</summary>' in html
    assert html.count('<p class="eyebrow">Accounts breakdown</p>') == 2
    assert '<p class="eyebrow">Breakdown</p>' not in html
    assert html.count('<p class="eyebrow">Goal progress</p>') == 2
    assert '<p class="eyebrow">Goals</p>' not in html
    assert 'class="card mb-1 overview-access-card overview-desktop-detail"' in html
    assert 'class="card-grid allowance-grid mb-1 overview-desktop-detail"' in html

    hero_idx = html.index('class="card highlight mb-1 month-accent-')
    portfolio_idx = html.index('class="card mb-1 overview-portfolio-card"')
    access_idx = html.index('class="card mb-1 overview-access-card overview-desktop-detail"')

    assert hero_idx < portfolio_idx < access_idx

    css = open("/opt/data/steadyplan/app/static/css/styles.css").read()
    assert ".overview-compact-only {" in css
    assert ".overview-desktop-detail {" in css
    assert ".overview-compact-details," in css
    assert ".overview-compact-details summary::after" in css
    assert "display: block !important;" in css
