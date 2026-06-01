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
    assert '<details class="subnav-mobile-menu subnav-mobile-menu-goals">' in html
    assert '<span class="subnav-mobile-current">Goals</span>' in html
    assert '<span class="subnav-mobile-toggle">More views</span>' in html
    assert 'href="/projections/">Projections</a>' in html
    assert 'class="hero-actions-col goals-hero-actions"' in html
    assert 'class="badge-row goals-hero-badges"' in html
    assert 'href="/goals/?mode=create">+ Create goal</a>' in html
    assert '<div class="row-end">' not in html

    css = open("/opt/data/steadyplan/app/static/css/styles.css").read()
    assert ".goals-hero-actions {" in css
    assert "flex-direction: column;" in css
    assert ".goals-hero-badges .badge {" in css

    hero_idx = html.index('class="hero-actions-col goals-hero-actions"')
    create_idx = html.index('href="/goals/?mode=create">+ Create goal</a>')
    empty_state_idx = html.index('No goals yet')

    assert hero_idx < create_idx < empty_state_idx
