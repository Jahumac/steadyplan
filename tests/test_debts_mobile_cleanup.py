def test_debts_page_moves_primary_actions_into_hero_for_mobile_cleanup(app, client, make_user):
    _, username, password = make_user(username="debts-mobile", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/budget/debts/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'class="hero-actions-col debts-hero-actions"' in html
    assert 'class="badge-row debts-hero-badges"' in html
    assert 'href="/budget/debts/export.xlsx">↓ Export</a>' in html
    assert 'class="badge badge-meta" href="/budget/debts/export.xlsx">↓ Export</a>' in html
    assert 'href="/budget/debts/?mode=create">+ Add debt</a>' in html
    assert 'class="badge badge-primary-action" href="/budget/debts/?mode=create">+ Add debt</a>' in html
    assert '<div class="row-end">' not in html
    assert 'No debts tracked' in html

    css = open("/opt/data/steadyplan/app/static/css/styles.css").read()
    assert ".debts-hero-actions {" in css
    assert "align-items: stretch;" in css
    assert "justify-content: flex-start;" in css
    assert ".debts-hero-badges {" in css
    assert "grid-template-columns: 1fr;" in css
    assert ".debts-hero-badges .badge {" in css
    assert "width: 100%;" in css

    hero_idx = html.index('class="hero-actions-col debts-hero-actions"')
    add_idx = html.index('href="/budget/debts/?mode=create">+ Add debt</a>')
    empty_idx = html.index('No debts tracked')

    assert hero_idx < add_idx < empty_idx


def test_debt_edit_form_uses_plain_auto_tracking_copy(app, client, make_user):
    uid, username, password = make_user(username="debts-auto-copy", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            debt_id = conn.execute(
                """
                INSERT INTO debts (user_id, name, original_amount, current_balance, monthly_payment, apr, start_date, is_active)
                VALUES (?, 'Car loan', 12000, 9000, 250, 6.5, '2025-01-15', 1)
                """,
                (uid,),
            ).lastrowid
            conn.commit()

    detail_resp = client.get(f"/budget/debts/?debt_id={debt_id}")
    assert detail_resp.status_code == 200
    detail_html = detail_resp.get_data(as_text=True)
    assert 'title="Balance worked out from your first payment date and monthly payment schedule"' in detail_html
    assert "Interest left at this payment</span>" in detail_html
    assert "Interest left</span>" not in detail_html
    assert 'title="Balance estimated from your first payment date and monthly payment schedule"' not in detail_html
    assert 'title="Balance calculated automatically from your first payment date — updates each month"' not in detail_html

    edit_resp = client.get(f"/budget/debts/?mode=edit&debt_id={debt_id}")
    assert edit_resp.status_code == 200
    edit_html = edit_resp.get_data(as_text=True)
    assert "Shows how much you've paid off." in edit_html
    assert "Used to show how much you've paid off." not in edit_html
    assert "Add this to let SteadyPlan work out the current balance from the payment schedule." in edit_html
    assert "Add this if you want SteadyPlan to estimate the current balance from the payment schedule." not in edit_html
    assert "Set this to calculate the current balance automatically — no manual updates needed." not in edit_html

    create_resp = client.get("/budget/debts/?mode=create")
    assert create_resp.status_code == 200
    create_html = create_resp.get_data(as_text=True)
    assert "Shows how much you've paid off." in create_html
    assert "Used to show how much you've paid off." not in create_html


def test_debts_list_cards_use_plain_payoff_status_labels(app, client, make_user):
    uid, username, password = make_user(username="debts-list-status-copy", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO debts (user_id, name, original_amount, current_balance, monthly_payment, apr, start_date, is_active)
                VALUES (?, 'Card', 1200, 600, 100, 19.9, '2025-01-15', 1)
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/budget/debts/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Debt-free by:" in html
    assert "Interest left at this payment:" in html
    assert "auto-tracked</span>" in html
    assert "Free:" not in html
    assert "Interest left:" not in html
    assert ">auto</span>" not in html


def test_debts_list_cards_clarify_when_payment_does_not_cover_interest(app, client, make_user):
    uid, username, password = make_user(username="debts-interest-warning-copy", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO debts (user_id, name, original_amount, current_balance, monthly_payment, apr, is_active)
                VALUES (?, 'Problem debt', 1000, 1000, 5, 30, 1)
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/budget/debts/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Current payment does not cover interest" in html
    assert "Payment too low to cover interest" not in html
