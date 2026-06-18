from pathlib import Path


def _login(client, username, password):
    resp = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302)


def test_temporary_plan_create_is_scoped_to_owned_accounts(app, make_user):
    alice_uid, _, _ = make_user(username="temp-plan-alice", password="password123")
    bob_uid, _, _ = make_user(username="temp-plan-bob", password="password123")

    with app.app_context():
        from app.models import create_temporary_contribution_plan, get_connection

        with get_connection() as conn:
            bob_account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, monthly_contribution, current_value, valuation_mode, is_active)
                VALUES (?, 'Bob Cash ISA', 'Cash ISA', 100, 0, 'manual', 1)
                """,
                (bob_uid,),
            ).lastrowid
            conn.commit()

        result = create_temporary_contribution_plan(
            alice_uid,
            "Sneaky plan",
            [{
                "account_id": bob_account_id,
                "from_month": "2026-06",
                "to_month": "2026-08",
                "override_amount": 250,
            }],
        )

        assert result["created_count"] == 0
        with get_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM contribution_overrides"
            ).fetchone()["c"]
        assert count == 0


def test_temporary_plan_fetch_and_delete_are_owner_scoped(app, make_user):
    alice_uid, _, _ = make_user(username="temp-fetch-alice", password="password123")
    bob_uid, _, _ = make_user(username="temp-fetch-bob", password="password123")

    with app.app_context():
        from app.models import (
            create_contribution_override,
            create_temporary_contribution_plan,
            delete_temporary_contribution_plan,
            fetch_contribution_calendar,
            fetch_temporary_contribution_plans,
            get_connection,
        )

        with get_connection() as conn:
            alice_account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, monthly_contribution, current_value, valuation_mode, is_active)
                VALUES (?, 'Alice ISA', 'Stocks & Shares ISA', 100, 0, 'manual', 1)
                """,
                (alice_uid,),
            ).lastrowid
            bob_account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, monthly_contribution, current_value, valuation_mode, is_active)
                VALUES (?, 'Bob ISA', 'Stocks & Shares ISA', 100, 0, 'manual', 1)
                """,
                (bob_uid,),
            ).lastrowid
            conn.commit()

        create_temporary_contribution_plan(
            alice_uid,
            "Alice plan",
            [{
                "account_id": alice_account_id,
                "from_month": "2026-06",
                "to_month": "2026-07",
                "override_amount": 150,
            }],
        )
        create_temporary_contribution_plan(
            bob_uid,
            "Bob plan",
            [{
                "account_id": bob_account_id,
                "from_month": "2026-06",
                "to_month": "2026-07",
                "override_amount": 300,
            }],
        )
        create_contribution_override(
            {
                "account_id": bob_account_id,
                "from_month": "2026-06",
                "to_month": "2026-06",
                "override_amount": 50,
                "reason": "from budget",
            },
            bob_uid,
        )

        alice_plans = fetch_temporary_contribution_plans(alice_uid)
        assert len(alice_plans) == 1
        assert alice_plans[0]["plan_name"] == "Alice plan"
        assert {row["account_id"] for row in alice_plans[0]["rows"]} == {alice_account_id}

        alice_calendar = fetch_contribution_calendar(alice_uid, "2026-06", "2026-07")
        assert [account["name"] for account in alice_calendar["accounts"]] == ["Alice ISA"]

        assert delete_temporary_contribution_plan(alice_uid, "Bob plan") == 0

        bob_plans = fetch_temporary_contribution_plans(bob_uid)
        assert len(bob_plans) == 1
        assert bob_plans[0]["plan_name"] == "Bob plan"

        with get_connection() as conn:
            bob_reasons = [
                row["reason"]
                for row in conn.execute(
                    """
                    SELECT co.reason
                    FROM contribution_overrides co
                    JOIN accounts a ON a.id = co.account_id
                    WHERE a.user_id = ?
                    ORDER BY co.id ASC
                    """,
                    (bob_uid,),
                ).fetchall()
            ]
        assert bob_reasons == ["temporary_plan:Bob plan", "from budget"]


def test_delete_temporary_plan_only_removes_matching_reason(app, make_user):
    uid, _, _ = make_user(username="temp-delete-scope", password="password123")

    with app.app_context():
        from app.models import (
            create_contribution_override,
            create_temporary_contribution_plan,
            delete_temporary_contribution_plan,
            get_connection,
        )

        with get_connection() as conn:
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, monthly_contribution, current_value, valuation_mode, is_active)
                VALUES (?, 'Cash ISA', 'Cash ISA', 100, 0, 'manual', 1)
                """,
                (uid,),
            ).lastrowid
            conn.commit()

        create_temporary_contribution_plan(
            uid,
            "Cash buffer build-up",
            [{
                "account_id": account_id,
                "from_month": "2026-06",
                "to_month": "2026-08",
                "override_amount": 250,
            }],
        )
        create_contribution_override(
            {
                "account_id": account_id,
                "from_month": "2026-07",
                "to_month": "2026-07",
                "override_amount": 90,
                "reason": "from budget",
            },
            uid,
        )

        assert delete_temporary_contribution_plan(uid, "Cash buffer build-up") == 1
        with get_connection() as conn:
            reasons = [
                row["reason"]
                for row in conn.execute(
                    "SELECT reason FROM contribution_overrides WHERE account_id = ? ORDER BY id ASC",
                    (account_id,),
                ).fetchall()
            ]
        assert reasons == ["from budget"]


def test_projection_override_applies_inside_range_then_default_resumes(app, make_user):
    uid, _, _ = make_user(username="temp-projection", password="password123")

    with app.app_context():
        from app.calculations import projected_account_value_at_month, projection_monthly_contribution
        from app.models import create_temporary_contribution_plan, fetch_contribution_overrides, get_connection

        with get_connection() as conn:
            account_id = conn.execute(
                """
                INSERT INTO accounts (
                    user_id, name, wrapper_type, category, monthly_contribution,
                    current_value, valuation_mode, growth_mode, growth_rate_override, is_active
                )
                VALUES (?, 'General account', 'General Investment Account', 'Investment', 100, 1000, 'manual', 'custom', 0, 1)
                """,
                (uid,),
            ).lastrowid
            conn.commit()

        create_temporary_contribution_plan(
            uid,
            "Short boost",
            [{
                "account_id": account_id,
                "from_month": "2026-05",
                "to_month": "2026-06",
                "override_amount": 250,
            }],
        )

        with get_connection() as conn:
            account = dict(
                conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
            )
        overrides = fetch_contribution_overrides(account_id)
        account["_projection_start_month"] = "2026-04"
        account["_contribution_overrides"] = overrides

        assert float(account["monthly_contribution"]) == 100.0
        assert projection_monthly_contribution(account, None, 0) == 100.0
        assert projection_monthly_contribution(account, None, 1) == 250.0
        assert projection_monthly_contribution(account, None, 2) == 250.0
        assert projection_monthly_contribution(account, None, 3) == 100.0
        assert projected_account_value_at_month(account, None, 4) == 1700.0


def test_lifetime_isa_one_off_projection_override_gets_full_bonus(app, make_user):
    uid, _, _ = make_user(username="temp-lisa-one-off", password="password123")

    with app.app_context():
        from app.calculations import projected_account_value_at_month, projection_monthly_contribution
        from app.models import create_temporary_contribution_plan, fetch_contribution_overrides, get_connection

        with get_connection() as conn:
            account_id = conn.execute(
                """
                INSERT INTO accounts (
                    user_id, name, wrapper_type, category, monthly_contribution,
                    current_value, valuation_mode, growth_mode, growth_rate_override, is_active
                )
                VALUES (?, 'Lifetime ISA', 'Lifetime ISA', 'ISA', 0, 1000, 'manual', 'custom', 0, 1)
                """,
                (uid,),
            ).lastrowid
            conn.commit()

        create_temporary_contribution_plan(
            uid,
            "LISA lump sum",
            [{
                "account_id": account_id,
                "from_month": "2027-03",
                "to_month": "2027-03",
                "override_amount": 4000,
            }],
        )

        with get_connection() as conn:
            account = dict(
                conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
            )
        account["_projection_start_month"] = "2027-03"
        account["_contribution_overrides"] = fetch_contribution_overrides(account_id)

        assert projection_monthly_contribution(account, None, 0) == 5000.0
        assert projected_account_value_at_month(account, None, 1) == 6000.0


def test_budget_route_uses_active_override_for_linked_account_month(app, client, make_user):
    uid, username, password = make_user(username="temp-budget-route", password="password123")
    _login(client, username, password)

    with app.app_context():
        from app.models import create_temporary_contribution_plan, get_connection

        with get_connection() as conn:
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, monthly_contribution, current_value, valuation_mode, is_active)
                VALUES (?, 'Calendar ISA', 'Stocks & Shares ISA', 1000, 0, 'manual', 1)
                """,
                (uid,),
            ).lastrowid
            conn.commit()

        create_temporary_contribution_plan(
            uid,
            "Route plan",
            [{
                "account_id": account_id,
                "from_month": "2026-06",
                "to_month": "2026-06",
                "override_amount": 812.34,
            }],
        )

    resp = client.get("/budget/?month=2026-06")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Calendar ISA" in html
    assert 'value="812.34"' in html
    assert "contribution calendar" in html


def test_contribution_calendar_can_create_annual_pot_fill_pattern(app, client, make_user):
    uid, username, password = make_user(username="temp-calendar-annual-pattern", password="password123")
    _login(client, username, password)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, monthly_contribution, current_value, valuation_mode, is_active)
                VALUES (?, 'Lifetime ISA', 'Lifetime ISA', 0, 0, 'manual', 1)
                """,
                (uid,),
            ).lastrowid
            conn.commit()

    resp = client.post(
        "/budget/contribution-calendar?from_month=2027-04&to_month=2028-07",
        data={
            "form_name": "create_annual_pot_fill_plan",
            "plan_name": "Yearly LISA fill",
            "pattern_account_id": str(account_id),
            "pattern_start_month": "2027-04",
            "pattern_months_per_year": "4",
            "pattern_years": "2",
            "pattern_monthly_amount": "1000",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Saved yearly pot-fill plan" in html
    assert "Yearly LISA fill" in html
    assert "2027-04 to 2027-07" in html
    assert "2028-04 to 2028-07" in html
    assert "£1,000.00" in html


def test_contribution_calendar_can_create_variable_annual_pattern(app, client, make_user):
    uid, username, password = make_user(username="temp-calendar-variable-pattern", password="password123")
    _login(client, username, password)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, monthly_contribution, current_value, valuation_mode, is_active)
                VALUES (?, 'Lifetime ISA', 'Lifetime ISA', 0, 0, 'manual', 1)
                """,
                (uid,),
            ).lastrowid
            conn.commit()

    resp = client.post(
        "/budget/contribution-calendar?from_month=2027-04&to_month=2027-06",
        data={
            "form_name": "create_annual_pot_fill_plan",
            "plan_name": "Three-month LISA fill",
            "pattern_account_id": str(account_id),
            "pattern_start_month": "2027-04",
            "pattern_months_per_year": "3",
            "pattern_years": "1",
            "pattern_monthly_amount": "1000",
            "pattern_monthly_amounts": "1500, 1500, 1000",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Saved yearly pot-fill plan" in html
    assert "Three-month LISA fill" in html
    assert "2027-04 to 2027-04" in html
    assert "2027-05 to 2027-05" in html
    assert "2027-06 to 2027-06" in html
    assert "£1,500.00" in html
    assert "£1,000.00" in html


def test_contribution_calendar_page_loads(app, client, make_user):
    uid, username, password = make_user(username="temp-calendar-page", password="password123")
    _login(client, username, password)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, monthly_contribution, current_value, valuation_mode, is_active)
                VALUES (?, 'Page ISA', 'Stocks & Shares ISA', 200, 0, 'manual', 1)
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/budget/contribution-calendar")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Contribution calendar" in html
    assert "Temporary contribution plan" in html
    assert "month-accent-" not in html
    assert "contribution-calendar-hero" in html
    assert "settings-form contribution-calendar-form" in html
    assert 'data-label="Temporary amount"' in html


def test_contribution_calendar_has_mobile_style_safeguards():
    css = (Path(__file__).resolve().parents[1] / "app" / "static" / "css" / "styles.css").read_text()

    assert ".contribution-calendar-form input[type=\"month\"]" in css
    assert "color-scheme: dark;" in css
    assert "@media (max-width: 640px)" in css
    assert ".contribution-plan-table td::before" in css
