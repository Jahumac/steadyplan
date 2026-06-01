def test_debts_page_moves_primary_actions_into_hero_for_mobile_cleanup(app, client, make_user):
    _, username, password = make_user(username="debts-mobile", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/budget/debts/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'class="hero-actions-col debts-hero-actions"' in html
    assert 'class="badge-row debts-hero-badges"' in html
    assert 'href="/budget/debts/export.xlsx">↓ Export</a>' in html
    assert 'class="badge badge-meta" href="/budget/debts/export.xlsx">↓ Export</a>' in html
    assert 'href="/budget/debts/?mode=create">+ Add debt</a>' in html
    assert 'class="badge badge-primary-action" href="/budget/debts/?mode=create">+ Add debt</a>' in html
    assert '<div class="row-end">' not in html
    assert 'No debts tracked' in html

    css = open("/opt/data/steadyplan/app/static/css/styles.css").read()
    assert ".debts-hero-actions {" in css
    assert "align-items: stretch;" in css
    assert "justify-content: flex-start;" in css
    assert ".debts-hero-badges {" in css
    assert "grid-template-columns: 1fr;" in css
    assert ".debts-hero-badges .badge {" in css
    assert "width: 100%;" in css

    hero_idx = html.index('class="hero-actions-col debts-hero-actions"')
    add_idx = html.index('href="/budget/debts/?mode=create">+ Add debt</a>')
    empty_idx = html.index('No debts tracked')

    assert hero_idx < add_idx < empty_idx
