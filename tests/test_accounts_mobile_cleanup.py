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

    hero_idx = html.index('class="hero-actions-col accounts-hero-actions"')
    add_idx = html.index('href="/accounts/?mode=create">+ Add account</a>')
    grid_idx = html.index('class="acct-grid"')

    assert hero_idx < add_idx < grid_idx
