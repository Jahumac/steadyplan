def test_goals_first_use_landing_surfaces_basics_first(app, client, make_user):
    _, username, password = make_user(username="goals-first-use", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/goals/?mode=create&focus=first_goal")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Start here" in html
    assert "Add your first goal" in html
    assert "Just these basics first" in html
    assert "One clear target is enough to begin." in html
    assert "Add one goal name you care about" in html
    assert "Set the target amount you want to reach" in html
    assert "Pick the account tag that should count toward it" in html
    assert "Account tag to include" in html
    assert "One tag is enough to start." in html
    assert "Can wait until later" in html
    assert "Create and continue" in html
    assert "Goal Detail" not in html
    assert ">Create goal<" not in html
