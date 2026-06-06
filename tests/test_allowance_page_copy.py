from datetime import date

from app.models import fetch_assumptions, get_connection


def test_allowance_page_uses_lifetime_isa_heading(app, client, make_user):
    uid, username, password = make_user(username="allowance-lifetime-isa-heading", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE assumptions
                SET date_of_birth = '1990-01-01', salary_day = 1, isa_allowance = 20000, lisa_allowance = 4000
                WHERE user_id = ?
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'LISA', 'Cash LISA', 1000, 1, 'manual')
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/allowance/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Your UK tax allowances at a glance — ISA, Lifetime ISA, pension, and taxable account limits" in html
    assert ">Lifetime ISA used<" in html
    assert "<h3>ISA &amp; Lifetime ISA</h3>" in html
    assert "· includes Lifetime ISA</small>" in html
    assert "Your UK tax allowances at a glance — ISA, LISA, pension, and taxable account limits" not in html
    assert ">LISA used<" not in html
    assert "<h3>ISA &amp; LISA</h3>" not in html
    assert ">includes LISA<" not in html
    assert "<h2>Lifetime ISA allowance</h2>" in html
    assert "<h2>LISA Allowance</h2>" not in html
    assert "Lifetime ISA Allowance" not in html
    assert 'aria-label="Lifetime ISA allowance used"' in html
    assert 'aria-label="LISA allowance used"' not in html


def test_allowance_page_uses_pension_annual_progress_label(app, client, make_user):
    uid, username, password = make_user(username="allowance-pension-progress-label", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE assumptions
                SET date_of_birth = '1990-01-01', salary_day = 1
                WHERE user_id = ?
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active, valuation_mode)
                VALUES (?, 'Pension', 'SIPP', 1000, 200, 1, 'manual')
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/allowance/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert '<h2>Annual Allowance</h2>' in html
    assert 'aria-label="Pension annual allowance used"' in html
    assert 'aria-label="Pension allowance used"' not in html
    assert "Tax year-end estimate:" in html
    assert "Estimated by tax year end:" not in html
    assert "On track:" not in html


def test_allowance_page_uses_plain_basic_rate_relief_copy(app, client, make_user):
    uid, username, password = make_user(username="allowance-basic-relief-copy", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE assumptions
                SET date_of_birth = '1990-01-01', salary_day = 1, tax_band = 'basic'
                WHERE user_id = ?
                """,
                (uid,),
            )
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active, valuation_mode)
                VALUES (?, 'Pension', 'SIPP', 1000, 100, 1, 'manual')
                """,
                (uid,),
            ).lastrowid
            conn.commit()

    client.post(
        "/allowance/pension/add",
        data={"account_id": account_id, "amount": "100", "kind": "personal", "contribution_date": "2026-04-10"},
        follow_redirects=False,
    )

    resp = client.get("/allowance/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Your provider adds 20% basic-rate tax relief." in html
    assert "Your provider adds 20% basic-rate tax relief automatically." not in html
    assert "Applied automatically by your provider at 20%." not in html
    assert "Regular contributions are already included." in html
    assert "Regular contributions are counted automatically." not in html


def test_allowance_page_uses_plain_monthly_column_helper_copy(app, client, make_user):
    uid, username, password = make_user(username="allowance-monthly-helper-copy", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE assumptions
                SET date_of_birth = '1990-01-01', salary_day = 1, isa_allowance = 20000, lisa_allowance = 4000
                WHERE user_id = ?
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 250, 1, 'manual')
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/allowance/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Tax year-end estimate:" in html
    assert "Estimated by tax year end:" not in html
    assert "On track:" not in html
    assert "Where your ISA usage figure comes from" in html
    assert "Scheduled monthly contributions" in html
    assert "One-off top-ups" in html
    assert "Cash-flow adjustments" in html
    assert "Net tracked ISA usage" in html
    assert "This explains the ISA Allowance figure above. It only changes when you set a regular contribution, log a one-off top-up, or mark a cash transfer as using this tax year's ISA allowance." in html
    assert "No cash movements have been labelled as changing tracked ISA room yet." in html
    assert 'href="/accounts/" class="badge badge-meta">Review cash-flow events</a>' in html
    assert "Regular to date" in html
    assert "Monthly uses each account's regular contribution setting. Regular to date is that monthly amount multiplied by the months elapsed. Cash-flow adjustments only count when you label a movement as using ISA allowance." in html
    assert "Monthly column uses each account's monthly contribution setting × months elapsed. Cash-flow adjustments are only counted when you label a cash movement as affecting tracked ISA usage." not in html
    assert "Monthly column is estimated from each account's contribution setting × months elapsed." not in html
    assert 'href="/accounts/" class="link-accent">monthly contribution setting</a>' in html


def test_allowance_page_uses_plain_taxable_account_labels(app, client, make_user):
    uid, username, password = make_user(username="allowance-taxable-account-labels", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE assumptions
                SET date_of_birth = '1990-01-01', salary_day = 1, dividend_allowance = 500
                WHERE user_id = ?
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/allowance/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "<h3>Taxable account limits</h3>" in html
    assert "GIA Annual Limits" not in html
    assert "taxable accounts only" in html
    assert "GIA accounts only" not in html
    assert "only log dividends from taxable accounts." in html
    assert "only log GIA dividends." not in html
    assert "No taxable investment accounts found." in html
    assert "No taxable (GIA) accounts found." not in html
    assert "Log asset sales from your taxable accounts" in html
    assert "Log asset sales from your GIA" not in html


def test_allowance_page_shows_cash_flow_adjustment_column_for_explicit_isa_effects(app, client, make_user):
    uid, username, password = make_user(username="allowance-cash-flow-adjustment", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE assumptions
                SET date_of_birth = '1990-01-01', salary_day = 1, isa_allowance = 20000, lisa_allowance = 4000
                WHERE user_id = ?
                """,
                (uid,),
            )
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active, valuation_mode)
                VALUES (?, 'Cash ISA', 'Cash ISA', 1000, 0, 1, 'manual')
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO cash_flow_events (user_id, account_id, event_date, amount, kind, note, allowance_effect, created_at)
                VALUES (?, ?, '2026-04-10', -150, 'withdrawal', 'Room restored', 'flexible_withdrawal', datetime('now'))
                """,
                (uid, account_id),
            )
            conn.execute(
                """
                INSERT INTO cash_flow_events (user_id, account_id, event_date, amount, kind, note, allowance_effect, created_at)
                VALUES (?, ?, '2026-04-18', 200, 'deposit', 'Replacement', 'flexible_replacement', datetime('now'))
                """,
                (uid, account_id),
            )
            conn.commit()

    resp = client.get("/allowance/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Cash-flow adj." in html
    assert "Only set this when the cash movement changed your real tax-year ISA room." not in html
    assert "£-150" not in html
    assert "£50" in html
    assert "£200 used more room from labelled subscriptions or replacements" in html
    assert "£150 restored room from labelled flexible withdrawals." in html


def test_allowance_page_uses_plain_higher_rate_relief_copy(app, client, make_user):
    uid, username, password = make_user(username="allowance-higher-relief-copy", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE assumptions
                SET date_of_birth = '1990-01-01', salary_day = 1, tax_band = 'higher'
                WHERE user_id = ?
                """,
                (uid,),
            )
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active, valuation_mode)
                VALUES (?, 'Pension', 'SIPP', 1000, 100, 1, 'manual')
                """,
                (uid,),
            ).lastrowid
            conn.commit()

    client.post(
        "/allowance/pension/add",
        data={"account_id": account_id, "amount": "100", "kind": "personal", "contribution_date": "2026-04-10"},
        follow_redirects=False,
    )

    resp = client.get("/allowance/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Claim the extra relief through Self Assessment." in html
    assert "Claim any extra relief through Self Assessment." not in html
    assert "Claim extra relief via Self Assessment." not in html


def test_allowance_page_spells_out_lifetime_isa_age_warning(app, client, make_user):
    uid, username, password = make_user(username="allowance-lifetime-isa-age-warning", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    today = date.today()
    dob = date(today.year - 49, 1, 1).isoformat()

    with app.app_context():
        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE assumptions
                SET date_of_birth = ?, salary_day = 1, isa_allowance = 20000, lisa_allowance = 4000
                WHERE user_id = ?
                """,
                (dob, uid),
            )
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'Lifetime ISA', 'Lifetime ISA', 1000, 1, 'manual')
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/allowance/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "⚠ Lifetime ISA contributions stop at age 50." in html
    assert "⚠ Contributions stop at age 50." not in html


def test_allowance_page_spells_out_lifetime_isa_withdrawal_penalty_copy(app, client, make_user):
    uid, username, password = make_user(username="allowance-lifetime-isa-penalty-copy", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE assumptions
                SET date_of_birth = '1990-01-01', salary_day = 1, isa_allowance = 20000, lisa_allowance = 4000
                WHERE user_id = ?
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active, valuation_mode)
                VALUES (?, 'Lifetime ISA', 'Lifetime ISA', 1000, 100, 1, 'manual')
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/allowance/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "⚠ Early withdrawal penalty: 25% — you'd lose more than the Lifetime ISA bonus." in html
    assert "⚠ Early withdrawal penalty: 25% — you'd lose more than the bonus." not in html
