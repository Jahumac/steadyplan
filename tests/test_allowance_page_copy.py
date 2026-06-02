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
