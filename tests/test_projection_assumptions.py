def _login(client, username, password):
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)


def _goal_projection_reference(accounts, assumptions, target):
    from app.calculations import projected_account_value_at_month

    month = 1
    while month <= 50 * 12:
        projected = sum(projected_account_value_at_month(account, assumptions, month) for account in accounts)
        if projected >= float(target):
            return month
        month += 1
    return None


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

    assert "<title>Future estimates · SteadyPlan</title>" in body
    assert "<title>Projections · SteadyPlan</title>" not in body
    assert '<p class="eyebrow">Future estimates</p>' in body
    assert '<p class="eyebrow">Projections</p>' not in body
    assert "Rough retirement estimate · age 60" in body
    assert "Current totals use your saved balances and regular payments. Future estimates use the planning numbers in Settings. They are not guarantees, and this is not financial advice." in body
    assert "Based on your current balances, contributions, and assumptions. Not a guarantee, and not financial advice." not in body
    assert "Retirement projection · age 60" not in body
    assert "Retirement projection estimate" not in body
    assert "Estimated total at retirement" in body
    assert "Scenario Estimate at Retirement" not in body
    assert "About this future estimate" in body
    assert "About this projection" not in body
    assert "About this estimate" not in body
    assert "estimate, not a promise" in body
    assert "assumptions-based forecast, not a promise" not in body
    assert "You can change the <a href=\"/settings/?mode=edit&amp;focus=scenario_estimate_assumptions\" class=\"link-accent\">planning numbers</a> behind it." in body
    assert "You can change those assumptions in" not in body
    assert "Edit the scenario estimate assumptions in" not in body
    assert "Edit the inputs in" not in body
    assert body.count("Edit planning numbers") == 3
    assert body.count('/settings/?mode=edit&amp;focus=scenario_estimate_assumptions') == 4
    assert 'href="/settings/?mode=edit"' not in body
    assert "Edit assumptions" not in body
    assert body.count("Planning numbers") == 3
    assert "<summary>Assumptions</summary>" not in body
    assert '<p class="eyebrow">Assumptions</p>' not in body
    assert body.count("Numbers used here") == 2
    assert "What drives this scenario estimate" not in body
    assert "What drives this projection" not in body
    assert "What drives this estimate" not in body
    assert "Current total" in body
    assert "Current Total" not in body
    assert body.count("<span>Current total</span>") == 1
    assert "<span>Today</span>" not in body
    assert "Years to retirement" in body
    assert "Years to Go" not in body
    assert body.count("<span>Years to retirement</span>") == 3
    assert "<span>Years to go</span>" not in body
    assert "Monthly payments in" in body
    assert "Monthly Contributions" not in body
    assert "<span>Monthly payments in</span>" in body
    assert "<span>Monthly contributions</span>" not in body
    assert "<span>Current age → retirement</span>" in body
    assert "<span>Your age</span>" not in body
    assert "Cost of fees over time" in body
    assert "Lifetime Cost of Fees" not in body
    assert body.count("<span>Cost of fees over time</span>") == 1
    assert "<span>Cost of fees</span>" not in body
    assert '<summary>Account future estimates</summary>' in body
    assert body.count('<p class="eyebrow">Account future estimates</p>') == 2
    assert "Account breakdown" not in body
    assert body.count("Estimated account totals at retirement") == 2
    assert "Each account at retirement (scenario estimate)" not in body
    assert "See how each account could look at age 60" in body
    assert "Scenario estimates for each account at age 60" not in body
    assert body.count("Change monthly payments by month") == 2
    assert "Change monthly payments by age" not in body
    assert "Change contributions at certain ages" not in body
    assert "Projected values for each account at age 60" not in body
    assert "Projection estimates for each account at age 60" not in body
    assert '<summary>Estimate over time</summary>' in body
    assert body.count('<p class="eyebrow">Estimate over time</p>') == 2
    assert "Growth curve" not in body
    assert body.count("Future estimate over time") == 2
    assert body.count("How your future estimate could change year by year using your current planning numbers and monthly payments.") == 2
    assert body.count("aria-label=\"Future estimate chart\"") == 2
    assert "Portfolio Trajectory" not in body
    assert "How your portfolio could grow year by year under your current assumptions and contributions." not in body
    assert "aria-label=\"Projected portfolio growth chart\"" not in body
    assert body.count("Try a different scenario") == 3
    assert body.count('<p class="eyebrow">Try changes</p>') == 2
    assert "Scenario planner" not in body
    assert body.count("Monthly payments by account") == 2
    assert body.count("Future estimate total") == 2
    assert body.count("Difference from your plan") == 2
    assert body.count("Total monthly payments") == 2
    assert "Scenario total" not in body
    assert "vs. your plan" not in body
    assert "Monthly payments in per account" not in body
    assert "Monthly total" not in body
    assert "Try different retirement ages, growth rates, or monthly payments to see how the future estimate changes. Nothing here is saved unless you save changes elsewhere." in body
    assert body.count("Add rows like “from September 2030 → £600 a month”. This saves to your plan and updates the future estimate.") == 2
    assert "Add rows like “from age 50 → £600 a month”. This saves to your plan and updates the future estimate." not in body
    assert "£600/mo" not in body
    assert "· £500 a month" in body
    assert "/mo into account" not in body
    assert "/mo reclaimable via self-assessment" not in body
    assert "/mo — £" not in body
    assert "/yr" not in body
    assert "Add rows like “from age 50 → £600/mo”. This saves to your plan and updates projections." not in body
    assert "What If?" not in body
    assert "Adjust inputs to see how the projection changes. Nothing here is saved unless you save changes elsewhere." not in body
    assert "Adjust inputs to see how the projection estimate changes. Nothing here is saved unless you save changes elsewhere." not in body
    assert "Adjust inputs to see how the scenario estimate changes. Nothing here is saved unless you save changes elsewhere." not in body
    assert "Adjust inputs to see how the scenario estimate changes. Nothing is saved unless you explicitly save it elsewhere." not in body
    assert "Inflation" in body
    assert "Retirement timing" in body
    assert "Payments in" in body
    assert "Pensions" in body
    assert "Fees" in body
    assert "Retirement spending" in body


def test_try_different_scenario_uses_exact_saved_plan_values_for_reset_state(app, client, make_user):
    uid, username, password = make_user(username="proj-whatif-plan-values", password="password123")

    with app.app_context():
        from app.calculations import projected_account_value
        from app.models import (
            create_account,
            create_contribution_override,
            fetch_account,
            fetch_assumptions,
            update_assumptions,
        )

        assumptions = dict(fetch_assumptions(uid))
        assumptions.update({
            "annual_growth_rate": 0.07,
            "retirement_age": 60,
            "date_of_birth": "1980-01-01",
            "salary_day": 25,
        })
        update_assumptions(assumptions, uid)
        account_id = create_account(
            {
                "name": "Scheduled ISA",
                "provider": "Provider",
                "wrapper_type": "Stocks & Shares ISA",
                "category": "Investment",
                "tags": "",
                "current_value": 7787,
                "monthly_contribution": 550,
                "pension_contribution_day": 0,
                "goal_value": None,
                "valuation_mode": "manual",
                "growth_mode": "default",
                "growth_rate_override": None,
                "owner": "Janusz",
                "is_active": 1,
                "notes": "",
                "last_updated": "2026-06-01",
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
            },
            uid,
        )
        create_contribution_override(
            {
                "account_id": account_id,
                "from_month": "2030-09",
                "to_month": "9999-12",
                "override_amount": 1500,
                "reason": "schedule",
            },
            uid,
        )
        account = dict(fetch_account(account_id, uid))
        account["_contribution_overrides"] = [
            {"from_month": "2030-09", "to_month": "9999-12", "override_amount": 1500, "reason": "schedule"}
        ]
        account["_projection_start_month"] = "2026-06"
        exact_projected = projected_account_value(account, assumptions)

    _login(client, username, password)
    resp = client.get("/projections/")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")

    assert 'data-projected-plan="' in body
    assert f'data-projected-plan="{exact_projected}"' in body


def test_projections_page_uses_lifetime_isa_bonus_wording(app, client, make_user):
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
    assert "Lifetime ISA bonus" in body
    assert "Lifetime ISA bonuses" in body
    assert "government bonus" not in body
    assert "government bonuses" not in body
    assert "govt bonus" not in body


def test_projections_goal_callout_uses_scenario_estimate_wording(app, client, make_user):
    uid, username, password = make_user(username="proj-goal-copy", password="password123")

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
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 50000, 500, 1)
                """,
                (uid,),
            )
            conn.execute(
                "INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes) VALUES (?, 'FI target', 100000, '', '', '')",
                (uid,),
            )
            conn.commit()

    _login(client, username, password)
    resp = client.get("/projections/")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert 'Future estimate meets "FI target"' in body or 'Future estimate is below "FI target"' in body
    assert 'Future estimate £' in body
    assert 'Projected £' not in body
    assert 'Projection meets "FI target"' not in body
    assert 'Projection is below "FI target"' not in body
    assert 'Projection estimate meets "FI target"' not in body
    assert 'Projection estimate is below "FI target"' not in body


def test_settings_growth_hint_no_longer_says_nominal_todays_money(app, client, make_user):
    uid, username, password = make_user(username="settings", password="password123")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01' WHERE user_id = ?",
                (uid,),
            )
            conn.commit()

    _login(client, username, password)

    resp = client.get("/settings/?mode=edit")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Edit plan settings" in body
    assert "Edit Assumptions" not in body
    assert '<p class="eyebrow">Plan settings</p>' in body
    assert '<p class="eyebrow">Global Settings</p>' not in body
    assert "These settings change the estimates and goal dates only." in body
    assert "These inputs feed Projections and goal timing estimates." not in body
    assert "These inputs feed Projections and goal ETAs." not in body
    assert "These inputs feed Projections and goal estimates." not in body
    assert "nominal (today's money)" not in body
    assert "Enter a simple yearly rate" in body
    assert "Projections are in nominal future pounds" not in body
    assert "Choose the date SteadyPlan should use for retirement estimates." in body
    assert "affects projections and years-to-go" not in body
    assert "If you want a cautious view, use a lower number." in body
    assert "cautious “today’s spending power” estimate" not in body
    assert "rough “today’s spending power” estimate" not in body
    assert "Used for pension tax top-ups and what you may be able to claim back." in body
    assert "Used to calculate pension tax relief and show what you can reclaim" not in body
    assert "Used to check how much personal pension tax top-up you can get." in body
    assert "Used when checking your personal pension tax-relief limit" not in body
    assert "Used to estimate your personal pension tax-relief limit" not in body
    assert "Shows your age" in body
    assert "Used to work out your age" not in body
    assert "Used to calculate your age automatically" not in body
    assert "— currently" in body
    assert "— you're currently" not in body



def test_settings_monthly_update_timing_helper_uses_monthly_update_wording(app, client, make_user):
    uid, username, password = make_user(username="settings-monthly-update-copy", password="password123")
    _login(client, username, password)

    resp = client.get("/settings/?mode=edit")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Investment day of month" in body
    assert "The usual day money leaves your bank for savings or investments." in body
    assert "SteadyPlan uses this for monthly update reminders and moves weekends automatically." in body
    assert "Monthly Update Timing" not in body
    assert "Helps decide when your investments have settled and it's time for your Monthly Update" not in body
    assert "Used to work out when your investments have settled and it's time for your Monthly Update" not in body
    assert "Used to estimate when your investments have settled and it's time for your Monthly Update" not in body
    assert "Weekend shifts are handled in the settlement timing." not in body
    assert "The day your ISA contributions and standing orders go out — usually when your salary arrives or a day after." not in body
    assert "Settlement timing accounts for weekends automatically." not in body
    assert "Used to estimate when your investments have settled and it's time to review" not in body


def test_settings_uses_lifetime_isa_wording(app, client, make_user):
    uid, username, password = make_user(username="settings-lifetime-isa-copy", password="password123")
    _login(client, username, password)

    edit_resp = client.get("/settings/?mode=edit")
    assert edit_resp.status_code == 200
    edit_body = edit_resp.data.decode("utf-8", errors="ignore")
    assert "<span>Lifetime ISA allowance</span>" in edit_body
    assert "The yearly ISA limit. Lifetime ISA counts inside this." in edit_body
    assert "<span>LISA allowance</span>" not in edit_body
    assert "Annual limit — includes LISA" not in edit_body

    view_resp = client.get("/settings/")
    assert view_resp.status_code == 200
    view_body = view_resp.data.decode("utf-8", errors="ignore")
    assert '<p class="eyebrow">Plan settings</p>' in view_body
    assert '<p class="eyebrow">Settings</p>' not in view_body
    assert "The simple settings behind your estimates, dates, and limits." in view_body
    assert "The numbers used behind the scenes — growth rates, ages, and allowances" not in view_body
    assert "Lifetime ISA allowance" in view_body
    assert "Edit plan settings" in view_body
    assert 'href="/settings/?mode=edit&amp;focus=scenario_estimate_assumptions"' in view_body
    assert 'href="/settings/?mode=edit"' not in view_body
    assert "Edit settings" not in view_body
    assert "LISA allowance" not in view_body


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
    assert "Estimated total at retirement" in body
    assert "Projected at retirement" not in body
    assert "<small>estimate</small>" not in body
    assert "Current totals use your saved balances." in body
    assert "Future estimates use the planning numbers in Settings. They are not guarantees." in body
    assert "Future estimate based on your current balances, regular payments, and planning numbers in Settings. It is not a guarantee." in body
    assert "Scenario estimate uses your current balances, contribution settings, and your scenario estimate assumptions. It is not a guarantee." not in body
    assert "Scenario estimate uses your current balances, contribution settings, and the assumptions you set in Settings. It is not a guarantee." not in body
    assert "Scenario estimate based on your current balances, contribution settings, and the assumptions you set in Settings. It is not a guarantee." not in body
    assert "Scenario estimate uses your current balances, contribution settings, and assumptions in Settings. It is not a guarantee." not in body
    assert "Scenario estimate based on your current balances, contribution settings, and assumptions in Settings. It is not a guarantee." not in body
    assert "You can change those assumptions in <a href=\"/settings/?mode=edit\" class=\"link-accent\">Settings</a>." not in body
    assert "Projection based on your current balances, contribution settings, and assumptions in Settings." not in body


def test_planning_page_uses_scenario_estimate_copy_for_retirement_outputs(app, client, make_user):
    uid, username, password = make_user(username="planning-estimate-copy", password="password123")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01', retirement_age = 60, annual_growth_rate = 0.07 WHERE user_id = ?",
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, category, current_value, monthly_contribution, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 'ISA', 1000, 10, 1, 'manual')
                """,
                (uid,),
            )
            conn.commit()

    _login(client, username, password)
    resp = client.get("/planning/")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")

    assert "Private pension/investment estimate at retirement" in body
    assert "Private pot estimate at retirement" not in body
    assert "Locked for later" in body
    assert "Locked later" not in body
    assert "Current totals use saved balances. Future estimates use the planning numbers in Settings. They are not guarantees." in body
    assert "Scenario estimate at age 60 under current balances, contributions and growth assumptions. For planning only, not a guarantee." not in body
    assert "Estimate at age 60 under current balances, contributions and growth assumptions." not in body
    assert "Private pension/investment estimate at age 60:" in body
    assert "Private pot estimate at age 60:" not in body
    assert body.count("Future estimate at 60:") == 2
    assert "Scenario estimate at 60:" not in body


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
    assert "Goal timing estimates use tagged accounts, planned payments, and your planning numbers. Not a guarantee." in body
    assert "Goal timing estimates use tagged accounts, Payment calendar overrides, and growth assumptions." not in body
    assert "Goal timing estimates use your current contributions and growth assumptions." not in body
    assert "Goal ETAs use your current contributions and growth assumptions." not in body
    assert "Goal ETAs are estimates based on your current contributions and growth assumptions." not in body
    assert "Goal ETAs are approximate scenario estimates based on your current contributions and growth assumptions." not in body
    assert "On course" in body
    assert "est. " in body
    assert "~" not in body


def test_goals_page_uses_action_copy_for_unlinked_and_out_of_range_goals(app, client, make_user):
    uid, username, password = make_user(username="goals-action-copy", password="password123")

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01', annual_growth_rate = 0.05 WHERE user_id = ?",
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO accounts (
                    user_id, name, wrapper_type, tags, current_value, monthly_contribution, is_active
                )
                VALUES (?, 'Tiny pot', 'Stocks & Shares ISA', 'tiny', 100, 1, 1)
                """,
                (uid,),
            )
            conn.executemany(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, ?, ?, 'Tagged Goal', ?, '')
                """,
                [
                    (uid, 'Big dream', 5000000, 'tiny'),
                    (uid, 'Missing link', 5000, 'missing'),
                ],
            )
            conn.commit()

    _login(client, username, password)
    resp = client.get("/goals/")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")

    assert "increase contributions to bring this within range" in body
    assert "link an account to this goal" in body
    assert "Needs attention" in body
    assert "More than 50 years at current rate" not in body
    assert "No contributions set" not in body


def test_goals_cards_show_tasteful_projection_source_details(app, client, make_user):
    uid, username, password = make_user(username="goals-source-detail", password="password123")

    with app.app_context():
        from app.models import create_contribution_override, get_connection

        with get_connection() as conn:
            conn.execute(
                """
                UPDATE assumptions
                SET date_of_birth = '1990-01-01', retirement_age = 60, annual_growth_rate = 0.05, salary_day = 28
                WHERE user_id = ?
                """,
                (uid,),
            )
            first_account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, tags, current_value, monthly_contribution, is_active)
                VALUES (?, 'Stocks ISA', 'Stocks & Shares ISA', 'retirement', 10000, 300, 1)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, tags, current_value, monthly_contribution, is_active)
                VALUES (?, 'SIPP', 'SIPP', 'retirement', 5000, 200, 1)
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Retirement goal', 100000, 'Retirement', 'retirement', '')
                """,
                (uid,),
            )
            conn.commit()

        create_contribution_override(
            {
                "account_id": first_account_id,
                "from_month": "2026-04",
                "to_month": "9999-12",
                "override_amount": 450,
                "reason": "schedule",
            },
            uid,
        )

    _login(client, username, password)
    resp = client.get("/goals/")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")

    assert 'class="goal-source-details"' in body
    assert '<summary>How this estimate is calculated</summary>' in body
    assert 'class="goal-source-panel"' in body
    assert "Projection basis" not in body
    assert "Tagged accounts" in body
    assert "2 accounts" in body
    assert "Payment calendar" in body
    assert "Overrides active" in body
    assert "Planning numbers" in body
    assert "Estimated total at retirement" in body
    assert "Same month-by-month future estimate as Planning." in body
    assert "Not a guarantee." in body
    assert "Goal timing estimates use tagged accounts, planned payments, and your planning numbers. Not a guarantee." in body
    assert "Goal timing estimates use tagged accounts, Payment calendar overrides, and growth assumptions." not in body
    assert "Goal timing estimates use your current contributions and growth assumptions." not in body


def test_goals_cards_collapse_projection_basis_behind_summary_first_disclosure(app, client, make_user):
    uid, username, password = make_user(username="goals-source-collapse", password="password123")

    with app.app_context():
        from app.models import create_contribution_override, get_connection

        with get_connection() as conn:
            conn.execute(
                """
                UPDATE assumptions
                SET date_of_birth = '1990-01-01', retirement_age = 60, annual_growth_rate = 0.05, salary_day = 28
                WHERE user_id = ?
                """,
                (uid,),
            )
            first_account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, tags, current_value, monthly_contribution, is_active)
                VALUES (?, 'Stocks ISA', 'Stocks & Shares ISA', 'retirement,long-term', 10000, 300, 1)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, tags, current_value, monthly_contribution, is_active)
                VALUES (?, 'SIPP', 'SIPP', 'retirement,long-term', 5000, 200, 1)
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Retirement goal', 100000, 'Retirement', 'retirement,long-term', 'Optional note')
                """,
                (uid,),
            )
            conn.commit()

        create_contribution_override(
            {
                "account_id": first_account_id,
                "from_month": "2026-04",
                "to_month": "9999-12",
                "override_amount": 450,
                "reason": "schedule",
            },
            uid,
        )

    _login(client, username, password)
    resp = client.get("/goals/")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")

    assert 'class="goal-source-details"' in body
    assert '<summary>How this estimate is calculated</summary>' in body
    assert '<details class="goal-source-details"' in body
    assert '<details class="goal-source-details" open' not in body
    assert 'class="goal-source-panel"' in body
    assert "Projection basis" not in body
    assert "Optional note" in body


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


def test_goal_projection_loop_matches_reference_projection_months(monkeypatch):
    import app.routes.goals as goals_route

    class _FixedDate:
        @staticmethod
        def today():
            from datetime import date
            return date(2026, 4, 1)

    monkeypatch.setattr(goals_route, "date", _FixedDate)

    assumptions = {
        "annual_growth_rate": 0.05,
        "retirement_age": 60,
        "date_of_birth": "1990-01-01",
        "retirement_date_mode": "birthday",
        "salary_day": 28,
        "tax_band": "basic",
    }
    accounts = [
        {
            "id": 1,
            "name": "LISA",
            "wrapper_type": "Lifetime ISA",
            "current_value": 5000,
            "monthly_contribution": 200,
            "employer_contribution": 0,
            "contribution_method": "standard",
            "contribution_fee_pct": 0,
            "growth_mode": "custom",
            "growth_rate_override": 0.05,
            "annual_fee_pct": 0,
            "platform_fee_pct": 0,
            "platform_fee_flat": 0,
            "platform_fee_cap": 0,
            "fund_fee_pct": 0,
            "_projection_start_month": "2026-04",
            "_contribution_overrides": [
                {"from_month": "2026-05", "to_month": "2026-05", "override_amount": 0},
                {"from_month": "2026-06", "to_month": "2026-07", "override_amount": 300},
            ],
        },
        {
            "id": 2,
            "name": "ISA",
            "wrapper_type": "Stocks & Shares ISA",
            "current_value": 4000,
            "monthly_contribution": 150,
            "employer_contribution": 0,
            "contribution_method": "standard",
            "contribution_fee_pct": 0,
            "growth_mode": "custom",
            "growth_rate_override": 0.04,
            "annual_fee_pct": 0,
            "platform_fee_pct": 0,
            "platform_fee_flat": 0,
            "platform_fee_cap": 0,
            "fund_fee_pct": 0,
            "_projection_start_month": "2026-04",
            "_contribution_overrides": [
                {"from_month": "2026-04", "to_month": "2026-04", "override_amount": 100},
            ],
        },
    ]
    target = 12000

    expected_months = _goal_projection_reference(accounts, assumptions, target)
    assert expected_months is not None
    result = goals_route._project_goal(accounts, target, assumptions)

    years, rem_months = divmod(expected_months, 12)
    if years == 0:
        expected_duration = f"{rem_months}m"
    elif rem_months == 0:
        expected_duration = f"{years}y"
    else:
        expected_duration = f"{years}y {rem_months}m"

    eta_month_num = 4 + expected_months
    eta_year = 2026 + (eta_month_num - 1) // 12
    eta_month_num = (eta_month_num - 1) % 12 + 1
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    expected_eta = f"{month_names[eta_month_num - 1]} {eta_year}"

    assert result == {
        "reached": False,
        "total_months": expected_months,
        "duration": expected_duration,
        "eta_label": expected_eta,
    }
