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
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'Pension', 'SIPP', 1000, 1, 'manual')
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/allowance/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "<h2>Annual Allowance</h2>" in html
    assert 'aria-label="Pension annual allowance used"' in html
    assert 'aria-label="Pension allowance used"' not in html


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
