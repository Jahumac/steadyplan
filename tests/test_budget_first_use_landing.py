def test_budget_first_use_landing_surfaces_basics_first(app, client, make_user):
    uid, username, password = make_user(username="budget-first-use", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/budget/items/?mode=create&focus=first_budget&month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Start here" in html
    assert "Add your first budget lines" in html
    assert "Just these basics first" in html
    assert "Add enough to get started" in html
    assert "Add take-home pay" in html
    assert "Add one or two essentials" in html
    assert "Can wait until later" in html
    assert "Save and continue" in html
    assert "Edit your budget items" not in html
    assert ">Add item<" not in html


def test_budget_empty_pages_use_first_budget_focus_links(app, client, make_user):
    _, username, password = make_user(username="budget-first-focus-links", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    budget_resp = client.get("/budget/?month=2026-04")
    assert budget_resp.status_code == 200
    budget_html = budget_resp.get_data(as_text=True)

    assert 'href="/budget/items/?mode=create&amp;focus=first_budget&amp;month=2026-04">Budget Setup</a>' in budget_html
    assert budget_html.count('focus=first_budget') >= 3
    assert 'href="/budget/items/?month=2026-04">Budget Setup</a>' not in budget_html
    assert 'href="/budget/items/?mode=create&amp;section=' in budget_html
    assert 'href="/budget/items/?mode=create&amp;section=' in budget_html and 'focus=first_budget' in budget_html

    setup_resp = client.get("/budget/items/?month=2026-04")
    assert setup_resp.status_code == 200
    setup_html = setup_resp.get_data(as_text=True)

    assert 'href="/budget/items/?mode=create&amp;focus=first_budget&amp;month=2026-04">+ Add Item</a>' in setup_html
    assert setup_html.count('focus=first_budget') >= 2
    assert 'href="/budget/items/?mode=create&amp;month=2026-04">+ Add Item</a>' not in setup_html
