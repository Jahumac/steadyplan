def _login(client, make_user, username):
    _, username, password = make_user(username=username, password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    return username


def _insert_debt(app, uid, *, name, balance, payment, apr):
    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO debts (user_id, name, original_amount, current_balance, monthly_payment, apr, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (uid, name, balance, balance, payment, apr),
            )
            conn.commit()


def test_debts_page_renders_payoff_guidance_card_with_strategy_controls(app, client, make_user):
    uid, username, password = make_user(username="debt-guidance-card", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    _insert_debt(app, uid, name="Card", balance=1200, payment=90, apr=24)
    _insert_debt(app, uid, name="Loan", balance=4000, payment=180, apr=7)
    _insert_debt(app, uid, name="Store", balance=300, payment=50, apr=0)

    resp = client.get("/budget/debts/?strategy=snowball&extra_monthly=75")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Suggested payoff order" in html
    assert "Where extra debt money could go first" in html
    assert "All debts keep their minimum payment in this estimate." in html
    assert "Payoff strategy" in html
    assert "Highest APR first (usually cheaper overall)" in html
    assert "Smallest balance first (quick wins)" in html
    assert "Extra overpayment per month (£)" in html
    assert "Update payoff estimate" in html
    assert 'value="75.0"' in html or 'value="75"' in html
    assert "Estimated payoff time" in html
    assert "Estimated total interest" in html
    assert "Debts ranked" in html
    assert "Estimated monthly payment while prioritised:" in html
    assert "/mo." in html
    assert "Based on the balances, rates, and payments entered." in html
    assert "Smallest balance first can give earlier pay-off milestones." in html
    assert "Highest APR first usually costs less in interest." in html
    assert "Strategy" not in html
    assert "Cheapest overall" not in html
    assert "Quick wins first" not in html
    assert "Extra debt payment per month (£)" not in html
    assert "Update estimate" not in html
    assert "Estimated outcome" not in html
    assert "Estimated interest" not in html
    assert "Debts included" not in html
    assert "Estimated focus payment" not in html
    assert "Best strategy" not in html
    assert "Optimal" not in html

    section_idx = html.index("Suggested payoff order")
    store_idx = html.index("Store", section_idx)
    card_idx = html.index("Card", section_idx)
    loan_idx = html.index("Loan", section_idx)
    assert store_idx < card_idx < loan_idx
    assert "Smallest balance first" in html
    assert "Gets the rolled payment after earlier debts clear" in html


def test_debts_page_payoff_guidance_shows_excluded_debt_reasons(app, client, make_user):
    uid, username, password = make_user(username="debt-guidance-excluded", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    _insert_debt(app, uid, name="Card", balance=1500, payment=100, apr=22)
    _insert_debt(app, uid, name="Problem debt", balance=1000, payment=5, apr=30)
    _insert_debt(app, uid, name="Cleared", balance=0, payment=50, apr=0)

    resp = client.get("/budget/debts/?strategy=avalanche&extra_monthly=50")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Some debts are not included in this estimate yet." in html
    assert "Problem debt" in html
    assert "Minimum payment does not currently cover interest" in html
    assert "Cleared" in html
    assert "Balance already cleared" in html
    assert "All debts are included automatically" not in html


def test_debts_page_payoff_guidance_empty_state_explains_how_to_get_a_ranked_estimate(app, client, make_user):
    uid, username, password = make_user(username="debt-guidance-empty-state", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    _insert_debt(app, uid, name="Missing payment", balance=900, payment=0, apr=19)
    _insert_debt(app, uid, name="Problem debt", balance=1000, payment=5, apr=30)
    _insert_debt(app, uid, name="Cleared", balance=0, payment=50, apr=0)

    resp = client.get("/budget/debts/?strategy=avalanche&extra_monthly=40")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "No debts are ready for a ranked estimate yet." in html
    assert "Add a monthly payment to at least one debt, and make sure its minimum payment covers interest." in html
    assert "Set up all debts first" not in html
    assert "Nothing to rank yet" not in html
    assert "Missing payment" in html
    assert "No monthly payment set" in html
    assert "Problem debt" in html
    assert "Minimum payment does not currently cover interest" in html
    assert "Cleared" in html
    assert "Balance already cleared" in html
