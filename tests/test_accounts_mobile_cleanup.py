from app.models import create_account


def _account_payload():
    return {
        "name": "Stocks & Shares ISA",
        "provider": "Trading 212",
        "wrapper_type": "Stocks & Shares ISA",
        "category": "Investment",
        "tags": "",
        "current_value": 6265.79,
        "monthly_contribution": 1300,
        "pension_contribution_day": 0,
        "goal_value": None,
        "valuation_mode": "holdings",
        "growth_mode": "default",
        "growth_rate_override": None,
        "owner": "Janusz",
        "is_active": 1,
        "notes": "",
        "last_updated": "2026-05-25",
        "employer_contribution": 0,
        "contribution_method": "standard",
        "annual_fee_pct": 0,
        "platform_fee_pct": 0,
        "platform_fee_flat": 0,
        "platform_fee_cap": 0,
        "fund_fee_pct": 0,
        "contribution_fee_pct": 0,
        "uninvested_cash": 0,
        "cash_interest_rate": 0,
        "interest_payment_day": 0,
    }


def test_accounts_page_moves_primary_actions_into_hero_for_mobile_cleanup(app, client, make_user):
    uid, username, password = make_user(username="accounts-mobile", password="password123")

    with app.app_context():
        create_account(_account_payload(), uid)

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get("/accounts/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert '<section class="budget-year-strip month-strip-global month-strip-mobile-hidden' in html
    assert 'class="hero-actions-col accounts-hero-actions"' in html
    assert 'class="badge-row accounts-hero-badges"' in html
    assert 'href="/accounts/?mode=create">+ Add account</a>' in html
    assert 'href="/accounts/balances/bulk?month_key=' in html
    assert '<div class="row-end">' not in html

    css = open("/opt/data/steadyplan/app/static/css/styles.css").read()
    assert ".accounts-hero-actions {" in css
    assert "flex: 1 0 100%;" in css
    assert "display: grid;" in css
    assert ".accounts-hero-badges .badge {" in css
    assert "width: 100%;" in css

    hero_idx = html.index('class="hero-actions-col accounts-hero-actions"')
    add_idx = html.index('href="/accounts/?mode=create">+ Add account</a>')
    grid_idx = html.index('class="acct-grid"')

    assert hero_idx < add_idx < grid_idx


def test_accounts_create_form_includes_junior_isa_wrapper_option(app, client, make_user):
    uid, username, password = make_user(username="accounts-jisa", password="password123")

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get("/accounts/?mode=create")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<option value="Junior ISA">Junior ISA</option>' in html


def test_accounts_edit_form_preserves_selected_legacy_wrapper_label(app, client, make_user):
    uid, username, password = make_user(username="accounts-legacy-wrapper", password="password123")
    payload = _account_payload()
    payload["name"] = "Legacy ISA"
    payload["wrapper_type"] = "Stocks and Shares ISA"

    with app.app_context():
        account_id = create_account(payload, uid)

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get(f"/accounts/{account_id}?mode=edit")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<option value="Stocks and Shares ISA" selected>Stocks and Shares ISA</option>' in html


def test_accounts_create_form_includes_investment_category_option(app, client, make_user):
    uid, username, password = make_user(username="accounts-investment-category", password="password123")

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get("/accounts/?mode=create")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<option value="Investment">Investment</option>' in html


def test_accounts_edit_form_preserves_selected_legacy_category_label(app, client, make_user):
    uid, username, password = make_user(username="accounts-legacy-category", password="password123")
    payload = _account_payload()
    payload["name"] = "Legacy category account"
    payload["category"] = "Investments"

    with app.app_context():
        account_id = create_account(payload, uid)

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get(f"/accounts/{account_id}?mode=edit")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<option value="Investments" selected>Investments</option>' in html


def test_accounts_create_wizard_uses_general_investment_account_label(app, client, make_user):
    uid, username, password = make_user(username="accounts-gia-template", password="password123")

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get("/accounts/?mode=create")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<strong>General Investment Account</strong>' in html
    assert '<strong>General Investment</strong>' not in html
    assert '25% government top-up, age limits' in html
    assert "25% gov't top-up, age limits" not in html


def test_accounts_page_uses_government_bonus_wording(app, client, make_user):
    uid, username, password = make_user(username="accounts-government-copy", password="password123")

    with app.app_context():
        create_account(_account_payload(), uid)

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get("/accounts/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'government bonus and employer top-ups' in html
    assert "gov't bonus and employer top-ups" not in html
