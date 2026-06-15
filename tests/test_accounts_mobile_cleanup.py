from datetime import date

from app.models import create_account, get_connection


from tests.path_helpers import STATIC_ROOT

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
    assert 'href="/accounts/?mode=create&amp;focus=first_account"' not in html
    assert 'href="/accounts/balances/bulk?month_key=' in html
    assert '<span>Into pots monthly</span>' in html
    assert '<span>Monthly in</span>' not in html
    assert 'You pay monthly £1,300' in html
    assert '£1,300/mo' not in html
    assert '<div class="row-end">' not in html

    css = STATIC_ROOT.joinpath("css/styles.css").read_text()
    assert ".accounts-hero-actions {" in css
    assert "flex: 1 0 100%;" in css
    assert "display: grid;" in css
    assert ".accounts-hero-badges .badge {" in css
    assert "width: 100%;" in css

    hero_idx = html.index('class="hero-actions-col accounts-hero-actions"')
    add_idx = html.index('href="/accounts/?mode=create">+ Add account</a>')
    grid_idx = html.index('class="acct-grid"')

    assert hero_idx < add_idx < grid_idx


def test_accounts_page_uses_plan_line_copy_for_account_comparison(app, client, make_user):
    uid, username, password = make_user(username="accounts-plan-line-copy", password="password123")

    with app.app_context():
        payload = _account_payload()
        payload["goal_value"] = 10000
        account_id = create_account(payload, uid)
        today = date.today()
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key) VALUES (?, ?, ?, ?)",
                (today.replace(day=1).isoformat(), account_id, 6000, today.strftime("%Y-%m")),
            )
            prev_month = today.month - 1 or 12
            prev_year = today.year - 1 if today.month == 1 else today.year
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key) VALUES (?, ?, ?, ?)",
                (date(prev_year, prev_month, 1).isoformat(), account_id, 5500, f"{prev_year:04d}-{prev_month:02d}"),
            )
            conn.commit()

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get(f"/accounts/{account_id}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Comparison line @7%" in html
    assert "Should be @7%" not in html
    assert "Goal timing estimate" in html
    assert "Goal ETA" not in html
    assert "Recorded balance uses saved account history. The comparison line uses your assumptions, contribution settings and recorded cash-flow adjustments; it is not a guarantee." in html
    assert "This compares your recorded balance with an assumptions-based comparison line for this account." not in html
    assert "investment day (shifted for weekends, plus settlement)" in html
    assert "monthly update due date" not in html
    assert "salary day shifted for weekends" not in html
    assert "Use it as a planning guide, not a guarantee." not in html
    assert "comparison line treating transfers out as “being behind”" in html
    assert "Actual vs plan for this account." not in html
    assert "Plan line @7%" not in html
    assert "assumptions-based plan line for this account" not in html
    assert "plan line treating transfers out as “being behind”" not in html


def test_account_detail_mobile_hero_uses_clearer_monthly_labels(app, client, make_user):
    uid, username, password = make_user(username="accounts-mobile-monthly-labels", password="password123")

    with app.app_context():
        payload = _account_payload()
        payload["monthly_contribution"] = 200
        payload["employer_contribution"] = 50
        account_id = create_account(payload, uid)

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get(f"/accounts/{account_id}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<span class="acct-hero-label">Into pot monthly</span>' in html
    assert '<small class="text-muted">you pay £200.00</small>' in html
    assert '<span class="acct-hero-label">Into pot / mo</span>' not in html
    assert '<span class="acct-hero-label">Monthly</span>' not in html


def test_accounts_list_card_uses_clearer_into_pot_monthly_copy(app, client, make_user):
    uid, username, password = make_user(username="accounts-list-monthly-copy", password="password123")

    with app.app_context():
        payload = _account_payload()
        payload["monthly_contribution"] = 200
        payload["employer_contribution"] = 50
        create_account(payload, uid)

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get("/accounts/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Into pots monthly £250' in html
    assert 'title="You pay £200 → £250 goes into pot"' in html
    assert '£250/mo' not in html
    assert '£200/mo' not in html


def test_account_detail_contribution_adjustments_panel_uses_per_month_wording(app, client, make_user):
    uid, username, password = make_user(username="accounts-adjustments-monthly-copy", password="password123")

    with app.app_context():
        payload = _account_payload()
        payload["monthly_contribution"] = 200
        account_id = create_account(payload, uid)
        current_month = date.today().strftime("%Y-%m")
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO contribution_overrides (account_id, from_month, to_month, override_amount, reason, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                (account_id, current_month, current_month, 250, "Bonus month"),
            )
            conn.execute(
                """
                INSERT INTO contribution_overrides (account_id, from_month, to_month, override_amount, reason, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                (account_id, "2026-01", "2026-02", 150, "Holiday dip"),
            )
            conn.commit()

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get(f"/accounts/{account_id}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Contribution Adjustments" in html
    assert "£250.00 per month" in html
    assert "£150.00 per month" in html
    assert "£250.00/mo" not in html
    assert "£150.00/mo" not in html


def test_account_detail_standard_contribution_panel_uses_per_month_wording(app, client, make_user):
    uid, username, password = make_user(username="accounts-standard-adjustment-copy", password="password123")

    with app.app_context():
        payload = _account_payload()
        payload["monthly_contribution"] = 125
        account_id = create_account(payload, uid)

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get(f"/accounts/{account_id}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Contribution Adjustments" in html
    assert "£125.00 per month" in html
    assert "Standard contribution from Budget" in html
    assert "£125.00/mo" not in html


def test_account_detail_shows_ongoing_for_open_ended_schedule_adjustments(app, client, make_user):
    uid, username, password = make_user(username="accounts-ongoing-schedule-copy", password="password123")

    with app.app_context():
        payload = _account_payload()
        payload["monthly_contribution"] = 500
        account_id = create_account(payload, uid)
        current_month = date.today().strftime("%Y-%m")
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO contribution_overrides (account_id, from_month, to_month, override_amount, reason, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                (account_id, current_month, "9999-12", 500, "schedule"),
            )
            conn.commit()

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get(f"/accounts/{account_id}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert f"Adjustment · {current_month} → Ongoing · schedule" in html
    assert "9999-12" not in html


def test_accounts_create_form_includes_junior_isa_wrapper_option(app, client, make_user):
    uid, username, password = make_user(username="accounts-jisa", password="password123")

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get("/accounts/?mode=create")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<option value="Junior ISA">Junior ISA</option>' in html
    assert 'Use default growth rate from your scenario estimate assumptions' in html
    assert 'Use default growth rate (from Settings)' not in html
    assert 'Set 0 to use the investment day from your scenario estimate assumptions.' in html
    assert 'Set 0 to use salary day from Settings.' not in html


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


def test_accounts_edit_form_uses_assumptions_wording_for_pension_posting_day(app, client, make_user):
    uid, username, password = make_user(username="accounts-pension-posting-day", password="password123")
    payload = _account_payload()
    payload["name"] = "Workplace Pension"
    payload["wrapper_type"] = "Workplace Pension"
    payload["category"] = "Pension"

    with app.app_context():
        account_id = create_account(payload, uid)

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get(f"/accounts/{account_id}?mode=edit")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Use if workplace pension invests later than your investment day' in html
    assert 'Set 0 to use the investment day from your scenario estimate assumptions.' in html
    assert 'Use if workplace pension invests later than salary day' not in html
    assert 'Set 0 to use salary day from Settings.' not in html


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
    assert '25% Lifetime ISA bonus, age limits' in html
    assert '25% government top-up, age limits' not in html
    assert "25% gov't top-up, age limits" not in html
    assert 'How much goes into this account each month? This feeds into scenario estimates. You can update it later.' in html
    assert 'How much goes into this account each month? This feeds into projections. You can update it later.' not in html
    assert 'How much goes into this account each month? This feeds into projections — an estimate is fine.' not in html
    assert 'How much goes into this account each month? This is used for projections — even an estimate helps.' not in html
    assert 'How much goes into this account each month? This is used for projections — even a rough number helps.' not in html


def test_accounts_page_uses_lifetime_isa_bonus_wording(app, client, make_user):
    uid, username, password = make_user(username="accounts-government-copy", password="password123")

    payload = _account_payload()
    payload["name"] = "Lifetime ISA"
    payload["wrapper_type"] = "Lifetime ISA"

    with app.app_context():
        account_id = create_account(payload, uid)

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    response = client.get("/accounts/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Lifetime ISA bonus and employer top-ups' in html
    assert 'government bonus and employer top-ups' not in html
    assert "gov't bonus and employer top-ups" not in html

    edit_response = client.get(f"/accounts/{account_id}?mode=edit")
    assert edit_response.status_code == 200
    edit_html = edit_response.get_data(as_text=True)
    assert 'Your Lifetime ISA bonus adds 25% on top (up to £4,000/year contributions).' in edit_html
    assert 'The government adds a 25% bonus (up to £4,000/year contributions).' not in edit_html

    sipp_payload = _account_payload()
    sipp_payload["name"] = "Pension"
    sipp_payload["wrapper_type"] = "SIPP"
    sipp_payload["category"] = "Pension"

    with app.app_context():
        sipp_id = create_account(sipp_payload, uid)

    sipp_edit_response = client.get(f"/accounts/{sipp_id}?mode=edit")
    assert sipp_edit_response.status_code == 200
    sipp_html = sipp_edit_response.get_data(as_text=True)
    assert 'Your provider adds 25% basic-rate tax relief on top.' in sipp_html
    assert 'Your provider adds 25% basic-rate tax relief on top automatically.' not in sipp_html
    assert 'your provider claims it from HMRC automatically.' not in sipp_html


def test_accounts_edit_form_uses_cautious_premium_bonds_estimate_copy(app, client, make_user):
    uid, username, password = make_user(username="accounts-premium-bonds-copy", password="password123")
    payload = _account_payload()
    payload["name"] = "Premium Bonds"
    payload["wrapper_type"] = "Premium Bonds"
    payload["category"] = "Savings"
    payload["valuation_mode"] = "premium_bonds"
    payload["growth_mode"] = "custom"
    payload["growth_rate_override"] = 0.033

    with app.app_context():
        account_id = create_account(payload, uid)

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get(f"/accounts/{account_id}?mode=edit")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Used as a planning assumption for scenario estimates only.' in html
    assert 'Used as a planning assumption for projections only.' not in html
    assert 'Used as a planning estimate for projections only.' not in html
    assert 'Used as a cautious estimate for projections only.' not in html
    assert 'Used as a rough estimate for projections only.' not in html


def test_accounts_edit_form_uses_plain_pension_method_wording(app, client, make_user):
    uid, username, password = make_user(username="accounts-pension-method-copy", password="password123")
    payload = _account_payload()
    payload["name"] = "Workplace pension"
    payload["wrapper_type"] = "Workplace Pension"
    payload["category"] = "Pension"
    payload["contribution_method"] = "relief_at_source"

    with app.app_context():
        account_id = create_account(payload, uid)

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get(f"/accounts/{account_id}?mode=edit")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Salary sacrifice = pre-tax, nothing extra to claim.' in html
    assert 'Relief at source = your provider adds 20% basic-rate tax relief for you.' in html
    assert 'Salary sacrifice = pre-tax, no relief to claim.' not in html
    assert 'your provider claims 20% back from HMRC for you.' not in html


def test_accounts_edit_form_uses_plain_contribution_guidance_copy(app, client, make_user):
    uid, username, password = make_user(username="accounts-contrib-guidance-copy", password="password123")
    payload = _account_payload()
    payload["name"] = "ISA"
    payload["wrapper_type"] = "Stocks & Shares ISA"
    payload["category"] = "ISA"

    with app.app_context():
        account_id = create_account(payload, uid)

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get(f"/accounts/{account_id}?mode=edit")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'If you link a budget item to this account, it can feed into your budget.' in html
    assert 'If you link a budget item to this account, it can be used in your budget automatically.' not in html
