def _login(client, username, password):
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)


def test_projections_page_shows_assumption_visibility(app, client, make_user):
    uid, username, password = make_user(username="proj", password="password123")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE assumptions
                SET annual_growth_rate = 0.07,
                    retirement_age = 60,
                    date_of_birth = '1980-01-01',
                    retirement_date_mode = 'end_of_tax_year'
                WHERE user_id = ?
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, fund_fee_pct, is_active)
                VALUES (?, 'Vanguard ISA', 'Stocks & Shares ISA', 10000, 500, 0.50, 1)
                """,
                (uid,),
            )
            conn.commit()

    _login(client, username, password)
    resp = client.get("/projections/")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")

    assert "Scenario estimate at retirement" in body
    assert "About this estimate" in body
    assert "assumptions-based forecast, not a promise" in body
    assert "Edit the inputs in" in body
    assert "What drives this estimate" in body
    assert "Inflation" in body
    assert "Retirement timing" in body
    assert "Contributions" in body
    assert "Pensions" in body
    assert "Fees" in body
    assert "Retirement spending" in body


def test_projections_page_uses_government_bonus_wording(app, client, make_user):
    uid, username, password = make_user(username="proj-government-bonus", password="password123")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection, update_assumptions

        assumptions = dict(fetch_assumptions(uid))
        assumptions.update({
            "annual_growth_rate": 0.05,
            "retirement_age": 60,
            "date_of_birth": "1990-01-01",
        })
        update_assumptions(assumptions, uid)
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, category, current_value, monthly_contribution, is_active)
                VALUES (?, 'LISA', 'Lifetime ISA', 'ISA', 5000, 400, 1)
                """,
                (uid,),
            )
            conn.commit()

    _login(client, username, password)
    resp = client.get("/projections/")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "government bonus" in body
    assert "govt bonus" not in body


def test_settings_growth_hint_no_longer_says_nominal_todays_money(app, client, make_user):
    uid, username, password = make_user(username="settings", password="password123")
    _login(client, username, password)

    resp = client.get("/settings/?mode=edit")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "These inputs feed Projections and goal estimates." in body
    assert "nominal (today's money)" not in body
    assert "nominal future pounds" in body



def test_settings_monthly_update_timing_helper_uses_monthly_update_wording(app, client, make_user):
    uid, username, password = make_user(username="settings-monthly-update-copy", password="password123")
    _login(client, username, password)

    resp = client.get("/settings/?mode=edit")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Monthly Update Timing" in body
    assert "Used to estimate when your investments have settled and it's time for your monthly update" in body
    assert "Used to estimate when your investments have settled and it's time to review" not in body


def test_overview_projected_retirement_stat_has_estimate_qualifier(app, client, make_user):
    uid, username, password = make_user(username="ov", password="password123")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01' WHERE user_id = ?",
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 10, 1)
                """,
                (uid,),
            )
            conn.commit()

    _login(client, username, password)
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Projected at retirement" in body
    assert "<small>estimate</small>" in body
    assert "Scenario estimate based on your current balances" in body


def test_goals_eta_helper_copy_present(app, client, make_user):
    uid, username, password = make_user(username="goals", password="password123")

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, tags, current_value, monthly_contribution, is_active)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 'goal-tag', 0, 100, 1)
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Test goal', 1000, 'Tagged Goal', 'goal-tag', '')
                """,
                (uid,),
            )
            conn.commit()

    _login(client, username, password)
    resp = client.get("/goals/")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Goal ETAs are approximate scenario estimates" in body
    assert "~" in body


def test_goals_route_fetches_contribution_overrides_in_one_batch(app, client, make_user, monkeypatch):
    uid, username, password = make_user(username="goals-batch", password="password123")

    with app.app_context():
        from app.models import create_contribution_override, get_connection

        with get_connection() as conn:
            first_account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, tags, current_value, monthly_contribution, is_active)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 'goal-tag', 500, 100, 1)
                """,
                (uid,),
            ).lastrowid
            second_account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, tags, current_value, monthly_contribution, is_active)
                VALUES (?, 'Cash ISA', 'Cash ISA', 'goal-tag', 250, 50, 1)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Holiday', 5000, 'Tagged Goal', 'goal-tag', '')
                """,
                (uid,),
            )
            conn.commit()

        create_contribution_override(
            {
                "account_id": first_account_id,
                "from_month": "2026-04",
                "to_month": "2026-04",
                "override_amount": 150,
                "reason": "bonus",
            },
            uid,
        )
        create_contribution_override(
            {
                "account_id": second_account_id,
                "from_month": "2026-05",
                "to_month": "2026-05",
                "override_amount": 0,
                "reason": "pause",
            },
            uid,
        )

    import app.routes.goals as goals_route

    original = goals_route.fetch_contribution_overrides_for_accounts
    calls = []

    def _tracked(account_ids):
        calls.append(list(account_ids))
        return original(account_ids)

    monkeypatch.setattr(goals_route, "fetch_contribution_overrides_for_accounts", _tracked)

    _login(client, username, password)
    resp = client.get("/goals/")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")

    assert "Holiday" in body
    assert calls == [[first_account_id, second_account_id]]
