def test_overview_first_account_cta_targets_focused_accounts_wizard(app, client, make_user):
    _, username, password = make_user(username="accounts-first-use-overview", password="password123")

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "/accounts/?mode=create&focus=first_account" in html


def test_accounts_empty_state_cta_targets_focused_accounts_wizard(app, client, make_user):
    _, username, password = make_user(username="accounts-first-use-empty-state", password="password123")

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get("/accounts/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'href="/accounts/?mode=create&amp;focus=first_account"' in html
    assert 'href="/accounts/?mode=create"' not in html
    assert "+ Add your first account" in html
    assert "Start with one real account to get your picture started and give Monthly Update somewhere real to work from." in html
    assert "Everything you&#39;re tracking — tap any account for the full picture" not in html
    assert "Add your first account — ISA, pension, savings, anything you want to track — and you&#39;ll start seeing your overall picture take shape. Monthly Update will also have somewhere real to work from." in html
    assert "Add your first account — ISA, pension, savings, anything you want to track — and you&#39;ll start seeing your overall picture take shape.</p>" not in html


def test_accounts_first_use_focus_surfaces_calm_start_here_guidance(app, client, make_user):
    _, username, password = make_user(username="accounts-first-use-focus", password="password123")

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get("/accounts/?mode=create&focus=first_account")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'aria-label="First account guidance"' in html
    assert "Start here" in html
    assert "Add one real account" in html
    assert "One real account is enough to get your picture started and gives Monthly Update somewhere real to work from." in html
    assert "Use one of the quick templates if it fits, or type your own account name and type below. You only need enough detail to recognise the account later and get Monthly Update ready for real balances." in html
    assert "One real account is enough to get your picture started." not in html
    assert "Use one of the quick templates if it fits, or type your own account name and type below. You only need enough detail to recognise the account later." not in html
    assert "Can wait until later" in html
    assert "Just used for grouping. The default is fine if you're not sure." in html
    assert "Start typing or pick from the list. You can leave this blank for now." in html
    assert "Every penny needs a home." not in html
    assert 'data-first-account-focus="true"' in html
    assert "Your new account is ready. You'll see it in Accounts straight away, and Monthly Update now has somewhere real to work from." in html
    assert "Your new account is ready. You'll see it in Accounts and it will be included in scenario estimates straight away." not in html
