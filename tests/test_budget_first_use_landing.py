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
