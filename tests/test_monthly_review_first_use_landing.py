def test_monthly_review_first_use_focus_surfaces_baseline_reassurance(app, client, make_user):
    uid, username, password = make_user(username="monthly-review-first-use", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, valuation_mode, monthly_contribution, current_value, is_active)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 'manual', 150, 1000, 1)
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Emergency fund', 5000, '', '', '')
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/monthly-review/?focus=first_update&month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "<p class=\"eyebrow\">Start here</p>" in html
    assert "Do your first monthly update" in html
    assert "One pass is enough to create your first snapshot." in html
    assert "This screen is just for creating that first honest baseline." in html
    assert "If nothing changed yet, you can come back after your first contribution or balance change has settled." in html
    assert "If nothing changed yet, you can come back after your first contribution or balance move settles." not in html
    assert "<p class=\"eyebrow\">Monthly Update</p>" not in html
    assert "Three short steps: confirm contributions, update balances, then finish with your note." in html
    assert "How to finish this month" in html
    assert "Confirm contributions, update balances, then finish with your note." not in html
    assert "Start here this month" in html
    assert "Use these three checks to create a clean first baseline." in html
    assert "1 expected contribution to confirm for this month." in html
    assert "1 account balance to check across holdings, manual balances, or Premium Bonds." in html
    assert "No ISA allowance changes logged in " in html
    assert "Only review this if you moved money in or out of an ISA and it changed your tracked room." in html
    assert 'href="#expected-contributions" class="badge badge-primary-action">Confirm contributions</a>' in html
    assert 'href="#update-balances" class="badge badge-primary-action">Update account balances</a>' in html
    assert 'href="/allowance/#isa" class="badge badge-meta">Review ISA allowance changes</a>' in html


def test_monthly_review_first_use_focus_summarises_logged_isa_allowance_changes(app, client, make_user):
    uid, username, password = make_user(username="monthly-review-allowance-summary", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.calculations import uk_tax_year_label, uk_tax_year_start
        from app.models import get_connection

        ty_start = uk_tax_year_start().isoformat()
        tax_year_label = uk_tax_year_label()
        with get_connection() as conn:
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, valuation_mode, monthly_contribution, current_value, is_active)
                VALUES (?, 'Cash buffer ISA', 'Cash ISA', 'manual', 0, 2500, 1)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO cash_flow_events (user_id, account_id, event_date, amount, kind, note, allowance_effect, created_at)
                VALUES (?, ?, ?, -300, 'withdrawal', 'Flexible withdrawal', 'flexible_withdrawal', datetime('now'))
                """,
                (uid, account_id, ty_start),
            )
            conn.commit()

    resp = client.get("/monthly-review/?focus=first_update&month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert f"1 explicit ISA allowance change logged in {tax_year_label}." in html
    assert f"No ISA allowance changes logged in {tax_year_label}." not in html


def test_monthly_review_first_use_focus_ignores_performance_only_isa_movements(app, client, make_user):
    uid, username, password = make_user(username="monthly-review-performance-only-allowance", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.calculations import uk_tax_year_label, uk_tax_year_start
        from app.models import get_connection

        ty_start = uk_tax_year_start().isoformat()
        tax_year_label = uk_tax_year_label()
        with get_connection() as conn:
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, valuation_mode, monthly_contribution, current_value, is_active)
                VALUES (?, 'Cash ISA audit trail', 'Cash ISA', 'manual', 0, 2500, 1)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO cash_flow_events (user_id, account_id, event_date, amount, kind, note, allowance_effect, created_at)
                VALUES (?, ?, ?, 775, 'deposit', 'Historical performance top-up', 'performance_only', datetime('now'))
                """,
                (uid, account_id, ty_start),
            )
            conn.commit()

    resp = client.get("/monthly-review/?focus=first_update&month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert f"No ISA allowance changes logged in {tax_year_label}." in html
    assert "explicit ISA allowance change logged" not in html
    assert "Only review this if you moved money in or out of an ISA and it changed your tracked room." in html


def test_monthly_review_first_use_focus_links_empty_balance_setup_to_first_account(app, client, make_user):
    _, username, password = make_user(username="monthly-review-first-use-empty-balances", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/monthly-review/?focus=first_update&month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "No account balances need checking yet." in html
    assert 'href="/accounts/?mode=create&amp;focus=first_account" class="link-accent">Add one real account</a> to give Monthly Update somewhere real to work from.' in html
    assert 'href="/accounts/?mode=create&amp;focus=first_account" class="link-accent">Add an account</a> when you have something real to track.' not in html
    assert "No account balances need checking yet. Add an account when you have something real to track." not in html


def test_monthly_review_without_first_use_focus_keeps_regular_hero(app, client, make_user):
    uid, username, password = make_user(username="monthly-review-regular-hero", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, valuation_mode, monthly_contribution, current_value, is_active)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 'manual', 150, 1000, 1)
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/monthly-review/?month=2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "<p class=\"eyebrow\">Monthly Update</p>" in html
    assert "<h2 class=\"hero-value\">April 2026</h2>" in html
    assert "Do your first monthly update" not in html
    assert "This screen is just for creating that first honest baseline." not in html
    assert "Start here this month" not in html
