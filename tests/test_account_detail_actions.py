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


def test_account_detail_actions_are_direct_not_overflow_menu(app, client, make_user):
    uid, username, password = make_user()
    with app.app_context():
        account_id = create_account(_account_payload(), uid)

    client.post("/login", data={"username": username, "password": password})
    resp = client.get(f"/accounts/{account_id}")

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "account-detail-actions" in html
    assert "data-overflow" not in html
    assert "acct-overflow" not in html
    assert "More actions" not in html
    assert "?mode=edit" in html
    assert "+ Add holding" in html
    assert "Delete" in html
