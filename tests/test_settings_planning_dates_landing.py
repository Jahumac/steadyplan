def test_overview_planning_dates_cta_targets_focused_settings_landing(app, client, make_user):
    _, username, password = make_user(username="settings-focus-overview", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'href="/settings/?mode=edit&amp;focus=planning_dates"' in html
    assert html.count('/settings/?mode=edit&amp;focus=planning_dates') >= 1
    assert 'href="/settings/?mode=edit"' not in html



def test_settings_focus_landing_prioritises_planning_dates_for_first_use(app, client, make_user):
    _, username, password = make_user(username="settings-focus-first-use", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/settings/?mode=edit&focus=planning_dates")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Start here" in html
    assert "Add your planning dates" in html
    assert "Just these basics first" in html
    assert "Can wait until later" in html
    assert "Save and continue" in html
    assert "You only need these basics to get the timeline started. Add your investment day too if you want monthly update reminders at the right time." in html
    assert "You only need these basics to get timelines and scenario estimates started. Everything else here can wait until later." not in html
    assert "You only need these basics to get timelines and projections started." not in html
    assert "Date of birth and retirement age are enough to start. Add your investment day too if you want monthly update reminders at the right time." in html
    assert "Date of birth and retirement age are enough to start. You can come back for growth rate, allowances, and update timing later." not in html
    assert "These extra settings make estimates more accurate, but you can finish the basics without them." in html
    assert "These assumptions refine projections and reporting, but you do not need them to finish the basics." not in html

    dob_idx = html.index("Date of birth")
    retirement_age_idx = html.index("Retirement age")
    dashboard_name_idx = html.index("Dashboard name")
    annual_growth_idx = html.index("Expected yearly growth (%)")
    investment_day_idx = html.index("Investment day of month")

    assert dob_idx < dashboard_name_idx
    assert retirement_age_idx < annual_growth_idx
    assert investment_day_idx < dashboard_name_idx
    assert html.index("Can wait until later") < dashboard_name_idx


def test_settings_focus_landing_prioritises_scenario_estimate_assumptions_when_requested(app, client, make_user):
    _, username, password = make_user(username="settings-focus-assumptions", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/settings/?mode=edit&focus=scenario_estimate_assumptions")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Plan settings" in html
    assert "Edit plan settings" in html
    assert "These settings change the estimates and goal dates only. They do not change your saved balances or Monthly Update history." in html
    assert "Start here" not in html
    assert "Add your planning dates" not in html
    assert "Just these basics first" not in html
    assert "Can wait until later" not in html
    assert "Save settings" in html
    assert "Save and continue" not in html


