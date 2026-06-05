from datetime import date, timedelta


def test_overview_getting_started_card_prioritises_basics_and_defers_deeper_steps(app, client, make_user):
    _, username, password = make_user(username="overview-onboarding-new", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Next step" in html
    assert "Getting started" in html
    assert "Getting Started" not in html
    assert "You only need the basics to begin." in html
    assert "0/2 basics complete" in html
    assert "0/4 complete" not in html
    assert "Just these two basics first" in html
    assert "Can wait until later · 0/2 complete" in html
    assert "Finish the two basics first" in html
    assert "Open the first unfinished basic below. Goals and monthly updates can wait until you have something real to track." in html
    assert "Add your planning dates" in html
    assert "Date of birth and retirement age are enough to make later dates and scenario estimates meaningful." in html
    assert "Date of birth and retirement age are enough to make later dates and projections meaningful." not in html
    assert "Add your first account" in html
    assert "Set your first goal" in html
    assert "Set your first goal once you know what you want to aim for." in html
    assert "Set a first goal" not in html
    assert "Set a goal once you know what you want to aim for." not in html
    assert "Do your first monthly update after your first contribution or balance change settles." in html
    assert "Complete your profile" not in html
    assert "Complete profile" not in html
    assert 'href="/settings/?mode=edit&amp;focus=planning_dates"' in html
    assert '/goals/?mode=create&focus=first_goal' in html
    assert '/monthly-review/?focus=first_update' in html
    assert "No accounts set up" not in html
    assert "Data health" not in html
    assert "/accounts/?mode=create&focus=first_account" in html
    assert "Review" not in html
    assert "Monthly review" not in html
    assert "Status:" not in html
    assert html.index("budget-year-strip") < html.index("Welcome to SteadyPlan")
    assert "Nothing in the shell yet" not in html
    assert "<h2>Accounts</h2>" not in html
    assert "Total Net Worth" not in html
    assert '<h2>Where you stand now</h2>' not in html
    assert "Accessible vs locked" not in html
    assert "Portfolio Value" not in html
    assert "ISA allowance" not in html
    assert "ISA Allowance" not in html


def test_overview_getting_started_primary_action_moves_to_first_incomplete_basic_step(app, client, make_user):
    uid, username, password = make_user(username="overview-onboarding-profile", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01' WHERE user_id = ?",
                (uid,),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Add your first account" in html
    assert "Finish the two basics first" in html
    assert "You already added your planning dates. Now add one real account so Overview has something concrete to show." in html
    assert "1/2 basics complete" in html
    assert "0/4 complete" not in html
    assert "Add your first account" in html
    assert "Add first account" not in html
    assert "/accounts/?mode=create&focus=first_account" in html
    assert "No accounts set up" not in html
    assert "Data health" not in html
    assert "Nothing in the shell yet" not in html
    assert "<h2>Accounts</h2>" not in html
    assert "Total Net Worth" not in html
    assert '<h2>Where you stand now</h2>' not in html
    assert "Accessible vs locked" not in html
    assert "Portfolio Value" not in html
    assert "ISA allowance" not in html
    assert "ISA Allowance" not in html


def test_overview_first_account_state_hides_empty_portfolio_panel(app, client, make_user):
    uid, username, password = make_user(username="overview-first-account", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

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
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 1, 'manual')
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Start your first budget" in html
    assert "Useful once you want a simple monthly plan. Start with take-home pay and one or two essentials — the rest can wait." in html
    assert '/budget/items/?mode=create&amp;focus=first_budget' in html
    assert "Set your first goal" in html
    assert '/goals/?mode=create&focus=first_goal' in html
    assert "Set a first goal" not in html
    assert "Set first goal" not in html
    assert "Set your first goal or do your first monthly update" not in html
    assert "Start your first budget when you want a simple monthly plan. Goals and monthly updates can wait until later." in html
    assert html.count("<h2>Where you stand now</h2>") == 2
    assert html.count("Use this as the quick summary") == 2
    assert "Use this as the quick truth" not in html
    assert "Accessible vs locked" not in html
    assert "Portfolio Value" not in html
    assert "ISA Allowance" not in html
    assert "Pension allowance" not in html
    assert "Pension Allowance" not in html
    assert "No daily snapshots yet" not in html
    assert "Complete your first Monthly Update to start tracking net worth over time" not in html
    assert "<h2>Accounts</h2>" not in html



def test_overview_single_account_state_hides_accounts_breakdown_panel(app, client, make_user):
    uid, username, password = make_user(username="overview-single-account-breakdown", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

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
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 1, 'manual')
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

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert html.count("<h2>Where you stand now</h2>") == 2
    assert "Accessible vs locked" not in html
    assert "<h2>Accounts</h2>" not in html



def test_overview_multi_account_state_restores_accounts_breakdown_panel(app, client, make_user):
    uid, username, password = make_user(username="overview-multi-account-breakdown", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01' WHERE user_id = ?",
                (uid,),
            )
            conn.executemany(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, ?, ?, ?, 1, 'manual')
                """,
                [
                    (uid, 'ISA', 'Stocks & Shares ISA', 1000),
                    (uid, 'Pension', 'SIPP', 2000),
                ],
            )
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Emergency fund', 5000, '', '', '')
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "<p class=\"eyebrow\">Accounts breakdown</p>" in html
    assert "<p class=\"eyebrow\">Breakdown</p>" not in html
    assert html.count("<h2>Accounts breakdown</h2>") == 2
    assert "<h2>Accounts</h2>" not in html
    assert "Review accounts" in html
    assert "2 active" in html



def test_overview_first_goal_state_restores_allowance_panels(app, client, make_user):
    uid, username, password = make_user(username="overview-first-goal", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

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
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 1, 'manual')
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

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Do your first monthly update" in html
    assert '/monthly-review/?focus=first_update' in html
    assert "Start first monthly update" not in html
    assert "Keep going" in html
    assert "Getting Started" not in html
    assert "You already have the basics in place." in html
    assert "Do your first monthly update when you want SteadyPlan to start tracking progress." in html
    assert "Set your first goal or do your first monthly update" not in html
    assert "Set a first goal or do your first monthly update" not in html
    assert "Add a goal or do your first monthly update" not in html
    assert "You only need the basics to begin." not in html
    assert "Basics done" in html
    assert "Just these two basics first" not in html
    assert "1/2 later steps complete" in html
    assert "Helpful next steps · 1 remaining" in html
    assert "2/4 complete" not in html
    assert "Set your first goal once you know what you want to aim for." not in html
    assert "ISA allowance" in html
    assert "ISA Allowance" not in html
    assert "Tax allowance progress" in html
    assert "Tax allowances" not in html
    assert '<h2>Pension annual allowance ' in html
    assert '<h2>Pension allowance ' not in html
    assert "Pension Annual Allowance" not in html
    assert "<p class=\"eyebrow\">Goals</p>" not in html
    assert "Emergency fund progress" not in html



def test_overview_multi_goal_state_restores_goal_progress_panel(app, client, make_user):
    uid, username, password = make_user(username="overview-multi-goal", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

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
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 1, 'manual')
                """,
                (uid,),
            )
            conn.executemany(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, ?, ?, '', '', '')
                """,
                [
                    (uid, 'Emergency fund', 5000),
                    (uid, 'House deposit', 20000),
                ],
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert html.count("<p class=\"eyebrow\">Goal progress</p>") == 2
    assert html.count("<h2>Goal progress</h2>") == 2
    assert "<p class=\"eyebrow\">Goals</p>" not in html
    assert "Review goals" in html
    assert "Manage</a>" not in html
    assert "Emergency fund progress" in html
    assert "House deposit progress" in html
    assert "goal-track-status" in html
    assert "goal-track-label" in html
    assert "goal-track-detail" in html
    assert "set a monthly contribution" in html
    assert "est." in html



def test_overview_goal_progress_glance_statuses_cover_on_track_behind_and_ahead(app, client, make_user):
    uid, username, password = make_user(username="overview-goal-track-statuses", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01', annual_growth_rate = 0.05 WHERE user_id = ?",
                (uid,),
            )
            conn.executemany(
                """
                INSERT INTO accounts (
                    user_id, name, wrapper_type, current_value, monthly_contribution,
                    employer_contribution, tags, is_active, valuation_mode
                )
                VALUES (?, ?, 'Stocks & Shares ISA', ?, ?, 0, ?, 1, 'manual')
                """,
                [
                    (uid, 'Steady pot', 1200, 180, 'steady'),
                    (uid, 'Paused pot', 900, 0, 'paused'),
                    (uid, 'Done pot', 5000, 0, 'done'),
                ],
            )
            conn.executemany(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, ?, ?, 'Tagged Goal', ?, '')
                """,
                [
                    (uid, 'House deposit', 5000, 'steady'),
                    (uid, 'Kitchen fund', 5000, 'paused'),
                    (uid, 'Emergency fund', 3000, 'done'),
                ],
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert ">On track<" in html
    assert "est. " in html
    assert ">Behind<" in html
    assert "set a monthly contribution" in html
    assert ">Ahead<" in html
    assert "target already reached" in html



def test_overview_goal_progress_glance_statuses_flag_unlinked_and_too_low_goals(app, client, make_user):
    uid, username, password = make_user(username="overview-goal-track-edge-states", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

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
                    user_id, name, wrapper_type, current_value, monthly_contribution,
                    employer_contribution, tags, is_active, valuation_mode
                )
                VALUES (?, 'Tiny pot', 'Stocks & Shares ISA', 100, 1, 0, 'tiny', 1, 'manual')
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

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "increase contributions to bring this within range" in html
    assert "link an account to this goal" in html
    assert "More than 50 years at current rate" not in html
    assert "No contributions set" not in html



def test_overview_goal_progress_uses_same_projection_copy_as_goals_page(app, client, make_user):
    uid, username, password = make_user(username="overview-goal-projection-unified", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.calculations import effective_account_value, projection_start_month_key
        from app.models import fetch_all_accounts, fetch_assumptions, fetch_contribution_overrides, get_connection
        from app.services.goal_projection import project_goal

        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01', annual_growth_rate = 0.05 WHERE user_id = ?",
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO accounts (
                    user_id, name, wrapper_type, current_value, monthly_contribution,
                    employer_contribution, tags, is_active, valuation_mode
                )
                VALUES (?, 'House ISA', 'Stocks & Shares ISA', 1200, 180, 0, 'deposit', 1, 'manual')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'House deposit', 5000, 'Tagged Goal', 'deposit', '')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Emergency fund', 3000, 'Tagged Goal', 'deposit', '')
                """,
                (uid,),
            )
            conn.commit()

        assumptions = fetch_assumptions(uid)
        start_month = projection_start_month_key(assumptions)
        account = dict(fetch_all_accounts(uid)[0])
        account["current_value"] = effective_account_value(account, {})
        account["_contribution_overrides"] = fetch_contribution_overrides(account["id"])
        account["_projection_start_month"] = start_month
        projection = project_goal([account], 5000, assumptions)

    overview = client.get("/")
    goals = client.get("/goals/")
    assert overview.status_code == 200
    assert goals.status_code == 200
    overview_html = overview.get_data(as_text=True)
    goals_html = goals.get_data(as_text=True)

    assert projection is not None
    assert projection["total_months"]
    expected = f"~ {projection['duration']} to go · {projection['eta_label']}"

    assert expected in goals_html
    assert expected in overview_html
    assert f"~{date.today().year}" not in overview_html



def test_overview_pre_goal_multi_holding_state_hides_allocation_panel(app, client, make_user):
    uid, username, password = make_user(username="overview-pre-goal-multi-holding", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01' WHERE user_id = ?",
                (uid,),
            )
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 0, 1, 'holdings')
                """,
                (uid,),
            ).lastrowid
            conn.executemany(
                """
                INSERT INTO holdings (account_id, holding_name, value)
                VALUES (?, ?, ?)
                """,
                [
                    (account_id, 'Vanguard FTSE Global All Cap', 1234),
                    (account_id, 'iShares Core S&P 500', 567),
                ],
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Set your first goal" in html
    assert "Set a first goal" not in html
    assert html.count("<h2>Where you stand now</h2>") == 2
    assert "Accessible vs locked" not in html
    assert "id=\"allocationChart\"" not in html
    assert "Asset allocation doughnut chart" not in html



def test_overview_single_holding_state_hides_allocation_panel(app, client, make_user):
    uid, username, password = make_user(username="overview-single-holding", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01' WHERE user_id = ?",
                (uid,),
            )
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 0, 1, 'holdings')
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Emergency fund', 5000, '', '', '')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO holdings (account_id, holding_name, value)
                VALUES (?, 'Vanguard FTSE Global All Cap', 1234)
                """,
                (account_id,),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "ISA allowance" in html
    assert "ISA Allowance" not in html
    assert "id=\"allocationChart\"" not in html
    assert "Asset allocation doughnut chart" not in html



def test_overview_multi_holding_state_restores_allocation_panel(app, client, make_user):
    uid, username, password = make_user(username="overview-multi-holding", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01' WHERE user_id = ?",
                (uid,),
            )
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 0, 1, 'holdings')
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Emergency fund', 5000, '', '', '')
                """,
                (uid,),
            )
            conn.executemany(
                """
                INSERT INTO holdings (account_id, holding_name, value)
                VALUES (?, ?, ?)
                """,
                [
                    (account_id, 'Vanguard FTSE Global All Cap', 1234),
                    (account_id, 'iShares Core S&P 500', 567),
                ],
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "id=\"allocationChart\"" in html
    assert "Asset allocation doughnut chart" in html
    assert "<p class=\"eyebrow m-0\">Asset allocation</p>" in html
    assert "<p class=\"eyebrow m-0\">Holdings</p>" not in html
    assert "Review accounts" in html
    assert ">Manage</a>" not in html



def test_overview_hides_restricted_summary_when_there_is_no_restricted_money(app, client, make_user):
    uid, username, password = make_user(username="overview-no-restricted", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 1, 'manual')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'Pension', 'SIPP', 3000, 1, 'manual')
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert html.count("<h2>Where you stand now</h2>") == 2
    assert "Accessible vs locked" not in html
    assert "Accessible now" in html
    assert "Locked for later" in html
    assert "Locked later" not in html
    assert "Restricted" not in html
    assert 'class="overview-access-value"' not in html



def test_overview_surfaces_accessible_vs_locked_summary(app, client, make_user):
    uid, username, password = make_user(username="overview-access", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 1, 'manual')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'LISA', 'Lifetime ISA', 2000, 1, 'manual')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'Pension', 'SIPP', 3000, 1, 'manual')
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert html.count("<h2>Where you stand now</h2>") == 2
    assert "Accessible vs locked" not in html
    assert "Review planning" in html
    assert "Open Planning" not in html
    assert "Where you stand now" in html
    assert "Where are you standing now" not in html
    assert "Accessible now" in html
    assert "Restricted" in html
    assert "Locked for later" in html
    assert "Locked later" not in html
    assert html.count('class="overview-access-value"') >= 1
    assert "£2,000" in html
    assert "17% of your current total is usually reachable before pension age" in html
    assert "When you have locked money, the top summary keeps the headline amount visible." in html
    assert "Next accessible milestone:" in html
    assert "£20,000" in html



def test_overview_hides_completed_accessible_milestone_nudge(app, client, make_user):
    uid, username, password = make_user(username="overview-milestone-complete", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'Cash ISA', 'Cash ISA', 100000, 1, 'manual')
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert html.count("<h2>Where you stand now</h2>") == 2
    assert "Accessible vs locked" not in html
    assert "Accessible now" in html
    assert "Next accessible milestone:" not in html
    assert "£0 to go" not in html



def test_overview_hero_prioritises_access_labels_over_secondary_stats(app, client, make_user):
    uid, username, password = make_user(username="overview-hero", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")

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
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 10000, 250, 1, 'manual')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO monthly_reviews (user_id, month_key, status)
                VALUES (?, ?, 'complete')
                """,
                (uid, month_key),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Assets" in html
    assert "After debts" not in html
    assert "Active debts kept separate:" not in html
    assert "Active debts" not in html
    assert "Accessible now" in html
    assert "Locked for later" in html
    assert "Locked later" not in html
    assert "Monthly contributions" in html
    assert "Scenario estimate at retirement" in html
    assert "Scenario estimate uses your current balances, contribution settings, and your scenario estimate assumptions. It is not a guarantee." in html
    assert "Scenario estimate uses your current balances, contribution settings, and the assumptions you set in Settings. It is not a guarantee." not in html
    assert "Scenario estimate uses your current balances, contribution settings, and assumptions in Settings. It is not a guarantee." not in html
    assert "Projected at retirement" not in html
    assert "Goal progress" not in html
    assert "Tax Year " not in html



def test_overview_shows_assets_after_debts_toggle_when_active_debts_exist(app, client, make_user):
    uid, username, password = make_user(username="overview-debt-toggle", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

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
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 10000, 1, 'manual')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO debts (user_id, name, current_balance, monthly_payment, is_active)
                VALUES (?, 'Loan', 1234.56, 100, 1)
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'aria-label="Overview headline view"' in html
    assert 'href="/" class="period-btn active">Assets<' in html
    assert 'href="/?position=after_debts" class="period-btn">After debts<' in html
    assert "Active debts kept separate: £1,234.56." in html
    assert "Subtracting £1,234.56 in active debts." not in html
    assert "Active debts" in html
    assert "£1,235" in html
    assert "£10,000.00" in html
    assert "Total net worth" not in html



def test_overview_after_debts_view_updates_headline_value_and_helper(app, client, make_user):
    uid, username, password = make_user(username="overview-after-debts-view", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

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
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 10000, 1, 'manual')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO debts (user_id, name, current_balance, monthly_payment, is_active)
                VALUES (?, 'Loan', 1234.56, 100, 1)
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get('/?position=after_debts')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'href="/?position=after_debts" class="period-btn active">After debts<' in html
    assert 'href="/" class="period-btn">Assets<' in html
    assert "<p class=\"eyebrow\">After debts</p>" in html
    assert "Subtracting £1,234.56 in active debts." in html
    assert "Active debts kept separate: £1,234.56." not in html
    assert "Active debts" in html
    assert "£1,235" in html
    assert "£8,765.44" in html



def test_overview_hides_zero_monthly_contribution_hero_stat(app, client, make_user):
    uid, username, password = make_user(username="overview-zero-contribution", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

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
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 10000, 0, 1, 'manual')
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Accessible now" in html
    assert "Locked for later" in html
    assert "Locked later" not in html
    assert "Monthly contributions" not in html



def test_overview_hides_zero_locked_hero_stat(app, client, make_user):
    uid, username, password = make_user(username="overview-zero-locked", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

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
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 10000, 1, 'manual')
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Accessible now" in html
    assert "Monthly contributions" not in html
    assert "Scenario estimate at retirement" in html
    assert "Scenario estimate uses your current balances, contribution settings, and your scenario estimate assumptions. It is not a guarantee." in html
    assert "Scenario estimate uses your current balances, contribution settings, and the assumptions you set in Settings. It is not a guarantee." not in html
    assert "Scenario estimate uses your current balances, contribution settings, and assumptions in Settings. It is not a guarantee." not in html
    assert "Projected at retirement" not in html
    assert html.count("Locked for later") >= 1
    assert "Locked later" not in html
    assert "When you have locked money, the top summary keeps the headline amount visible." not in html
    assert "Pension-style money will appear here once you start building it." in html
    assert "Pension-style money will show up here once you start building it." not in html



def test_overview_hides_retirement_projection_until_profile_exists(app, client, make_user):
    uid, username, password = make_user(username="overview-no-profile-projection", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 10000, 250, 1, 'manual')
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Add your planning dates" in html
    assert "Accessible now" in html
    assert "Locked for later" in html
    assert "Locked later" not in html
    assert "Monthly contributions" in html
    assert "Projected at retirement" not in html
    assert "Scenario estimate at retirement" not in html
    assert "Scenario estimate uses your current balances, contribution settings, and the assumptions you set in Settings. It is not a guarantee." not in html
    assert "Scenario estimate uses your current balances, contribution settings, and assumptions in Settings. It is not a guarantee." not in html
    assert "Scenario estimate based on your current balances, contribution settings, and the assumptions you set in Settings." not in html
    assert "Scenario estimate based on your current balances, contribution settings, and assumptions in Settings." not in html


def test_overview_payday_banner_uses_specific_budget_cta(app, client, make_user, monkeypatch):
    uid, username, password = make_user(username="overview-payday-banner-budget-cta", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")
    today_str = date.today().strftime("%Y-%m-%d")

    import app.routes.overview as overview_route
    monkeypatch.setattr(overview_route, "is_salary_day", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(overview_route, "is_review_due", lambda *_args, **_kwargs: False)

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01', salary_day = 15 WHERE user_id = ?",
                (uid,),
            )
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 250, 1, 'manual')
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Emergency fund', 5000, '', '', '')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key)
                VALUES (?, ?, ?, ?)
                """,
                (today_str, account_id, 1000, month_key),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "investment day" in html
    assert "check the budget, then do your monthly update" in html
    assert "check the budget, then do your Monthly Update" not in html
    assert '>Review budget</a>' in html
    assert '>Open budget</a>' not in html
    assert 'href="/budget/"' in html
    payday_banner = html.split('<section class="card payday-banner mb-1">', 1)[1].split('</section>', 1)[0]
    assert 'shelly-inline-icon' not in payday_banner


def test_overview_review_due_does_not_repeat_monthly_update_nudge(app, client, make_user, monkeypatch):
    uid, username, password = make_user(username="overview-review-due", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    import app.routes.overview as overview_route

    monkeypatch.setattr(overview_route, "is_review_due", lambda *_args, **_kwargs: True)

    month_key = date.today().strftime("%Y-%m")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01', salary_day = 1 WHERE user_id = ?",
                (uid,),
            )
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 1, 'manual')
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Emergency fund', 5000, '', '', '')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key)
                VALUES (?, ?, ?, ?)
                """,
                (f"{month_key}-01", account_id, 1000, month_key),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "What to do next" in html
    assert "Monthly update ready" in html
    assert "Best once this month's money has settled." in html
    assert "Complete it to confirm balances and contributions, and keep goal and performance tracking based on confirmed numbers." in html
    assert "Your investments should be settled by now" not in html
    assert "Time to check your holdings and lock in this month's numbers." not in html
    assert "Complete it to confirm this month's balances and improve goal and performance tracking." not in html
    assert "Open monthly update" in html
    assert "Start monthly update" not in html
    assert "Your next nudge" not in html
    assert "Status:" not in html
    review_nudge = html.split('<section class="card review-nudge mb-1">', 1)[1].split('</section>', 1)[0]
    assert 'shelly-inline-icon' not in review_nudge


def test_overview_drops_resting_monthly_update_focus_card(app, client, make_user):
    uid, username, password = make_user(username="overview-monthly-review-card-cta", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01', salary_day = 31 WHERE user_id = ?",
                (uid,),
            )
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 250, 1, 'manual')
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Emergency fund', 5000, '', '', '')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key)
                VALUES (?, ?, ?, ?)
                """,
                (f"{month_key}-01", account_id, 1000, month_key),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'overview-focus-card' not in html
    assert f'/monthly-review/?month={month_key}' not in html
    assert 'Status: In progress' not in html
    assert 'Status: Complete' not in html
    assert 'class="card mb-1 overview-access-card overview-desktop-detail"' in html
    assert 'class="card mb-1 overview-portfolio-card"' in html
    assert html.index('class="card mb-1 overview-access-card overview-desktop-detail"') < html.index('class="card mb-1 overview-portfolio-card"')
    assert 'Assets' in html
    assert 'After debts' not in html
    assert 'Total net worth' not in html
    assert 'Total Net Worth' not in html

def test_overview_missed_review_alert_uses_specific_monthly_update_cta(app, client, make_user):
    uid, username, password = make_user(username="overview-missed-review-alert", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    today = date.today()
    if today.month == 1:
        last_month_key = f"{today.year - 1}-12"
    else:
        last_month_key = f"{today.year}-{today.month - 1:02d}"

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01', salary_day = 1 WHERE user_id = ?",
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 1, 'manual')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO monthly_reviews (user_id, month_key, status)
                VALUES (?, ?, 'started')
                """,
                (uid, last_month_key),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert '/monthly-review/?month=' in html
    assert "monthly update is still open" in html
    assert "balances, contributions, and tracking stay based on confirmed numbers" in html
    assert "monthly update hasn't been completed yet" not in html
    assert "Open monthly update" in html
    assert "Do it now" not in html


def test_overview_unconfirmed_contributions_alert_uses_monthly_update_cta(app, client, make_user):
    uid, username, password = make_user(username="overview-unconfirmed-contributions", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01' WHERE user_id = ?",
                (uid,),
            )
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 250, 1, 'manual')
                """,
                (uid,),
            ).lastrowid
            review_id = conn.execute(
                """
                INSERT INTO monthly_reviews (user_id, month_key, status)
                VALUES (?, ?, 'complete')
                """,
                (uid, month_key),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO monthly_review_items (review_id, account_id, expected_contribution, contribution_confirmed)
                VALUES (?, ?, ?, 0)
                """,
                (review_id, account_id, 250),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Open monthly update" in html
    assert "Check contributions" not in html
    assert '/monthly-review/?month=' in html


def test_overview_missing_salary_day_uses_single_settings_nudge(app, client, make_user):
    uid, username, password = make_user(username="overview-no-salary-day", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01', salary_day = 0 WHERE user_id = ?",
                (uid,),
            )
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 1, 'manual')
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Emergency fund', 5000, '', '', '')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key)
                VALUES (?, ?, ?, ?)
                """,
                (f"{month_key}-01", account_id, 1000, month_key),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Set your investment day in Settings" in html
    assert "do your monthly update" in html
    assert "do your Monthly Update" not in html
    assert "Set your investment day" in html
    assert "Open settings" not in html
    assert "Go to Settings" not in html
    assert "Your next nudge" not in html


def test_overview_unlinked_holdings_alert_uses_specific_price_source_cta(app, client, make_user):
    uid, username, password = make_user(username="overview-unlinked-holdings", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01', salary_day = 1, auto_update_prices = 1 WHERE user_id = ?",
                (uid,),
            )
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 1, 'holdings')
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO holdings (account_id, holding_name, ticker, value)
                VALUES (?, 'Global ETF', 'VWRP', 1000)
                """,
                (account_id,),
            )
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Emergency fund', 5000, '', '', '')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key)
                VALUES (?, ?, ?, ?)
                """,
                (f"{month_key}-01", account_id, 1000, month_key),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "no price source linked" in html
    assert "price won&#39;t refresh here" in html
    assert "price won&#39;t update automatically" not in html
    assert "Link price sources" in html
    assert "Review holdings" not in html


def test_overview_stale_price_alert_uses_specific_refresh_prices_cta(app, client, make_user):
    uid, username, password = make_user(username="overview-stale-prices", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01', salary_day = 1, auto_update_prices = 1 WHERE user_id = ?",
                (uid,),
            )
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 1, 'holdings')
                """,
                (uid,),
            ).lastrowid
            catalogue_id = conn.execute(
                """
                INSERT INTO holding_catalogue (user_id, holding_name, ticker, is_active, price_updated_at)
                VALUES (?, 'Global ETF', 'VWRP', 1, '2000-01-01 00:00:00')
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO holdings (account_id, holding_catalogue_id, holding_name, ticker, value)
                VALUES (?, ?, 'Global ETF', 'VWRP', 1000)
                """,
                (account_id, catalogue_id),
            )
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Emergency fund', 5000, '', '', '')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key)
                VALUES (?, ?, ?, ?)
                """,
                (f"{month_key}-01", account_id, 1000, month_key),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "scheduler may have missed a window" in html
    assert "Refresh prices now" in html
    assert "↻ Refresh now" not in html


def test_overview_portfolio_card_uses_specific_refresh_prices_cta(app, client, make_user):
    uid, username, password = make_user(username="overview-portfolio-refresh-cta", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01', auto_update_prices = 1 WHERE user_id = ?",
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 1, 'manual')
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
            conn.execute(
                """
                INSERT INTO portfolio_daily_snapshots (user_id, snapshot_date, total_value)
                VALUES (?, ?, ?)
                """,
                (uid, f"{month_key}-01", 1000),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Portfolio history" in html
    assert "Portfolio value" not in html
    assert "Portfolio Value" not in html
    assert "Latest value" in html
    assert "Latest Value" not in html
    assert 'id="changeLabel" class="text-muted m-0">Change since start<' in html
    assert 'id="changeLabel" class="text-muted m-0">Change<' not in html
    assert "Complete your first monthly update to start tracking net worth over time" in html
    assert "Complete your first Monthly Update to start tracking net worth over time" not in html
    assert "slow and steady wins the race" not in html
    assert "Refresh prices now" in html
    assert "↻ Refresh</button>" not in html


def test_overview_first_baseline_helper_uses_calm_trend_line_copy(app, client, make_user):
    uid, username, password = make_user(username="overview-first-baseline-copy", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    current_month = date.today().replace(day=1)

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01' WHERE user_id = ?",
                (uid,),
            )
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 1, 'manual')
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Emergency fund', 5000, '', '', '')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key)
                VALUES (?, ?, ?, ?)
                """,
                (current_month.strftime('%Y-%m-%d'), account_id, 1000, current_month.strftime('%Y-%m')),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Your first baseline is saved. Complete next month's monthly update and the net worth trend line will appear." in html
    assert "One snapshot down — slow and steady." not in html
    assert "Remember: slow and steady wins the race." not in html


def test_overview_fallback_net_worth_chart_uses_history_wording(app, client, make_user):
    uid, username, password = make_user(username="overview-net-worth-history-copy", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    current_month = date.today().replace(day=1)
    previous_month = (current_month - timedelta(days=1)).replace(day=1)

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01' WHERE user_id = ?",
                (uid,),
            )
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 1, 'manual')
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Emergency fund', 5000, '', '', '')
                """,
                (uid,),
            )
            conn.executemany(
                """
                INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (previous_month.strftime('%Y-%m-%d'), account_id, 900, previous_month.strftime('%Y-%m')),
                    (current_month.strftime('%Y-%m-%d'), account_id, 1000, current_month.strftime('%Y-%m')),
                ],
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Net worth history" in html
    assert 'aria-label="Net worth history chart"' in html
    assert 'aria-label="Net worth growth chart"' not in html


def test_overview_portfolio_pending_review_helper_uses_sentence_case_monthly_update_link(app, client, make_user, monkeypatch):
    uid, username, password = make_user(username="overview-pending-review-helper-copy", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    import app.routes.overview as overview_route

    monkeypatch.setattr(overview_route, "is_review_due", lambda *_args, **_kwargs: False)

    previous_month_date = date.today().replace(day=1) - timedelta(days=1)
    previous_month_str = previous_month_date.strftime("%Y-%m-%d")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01', salary_day = 1 WHERE user_id = ?",
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 250, 1, 'manual')
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
            conn.execute(
                """
                INSERT INTO portfolio_daily_snapshots (user_id, snapshot_date, total_value)
                VALUES (?, ?, ?)
                """,
                (uid, previous_month_str, 1000),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "still waiting for confirmation — complete the" in html
    assert "history and performance use confirmed balances and contributions" in html
    assert "still using defaults — confirm in" not in html
    assert "estimated from defaults — confirm in" not in html
    assert 'href="/monthly-review/" class="link-accent">monthly update</a>' in html
    assert 'href="/monthly-review/" class="link-accent">Monthly Update</a>' not in html


def test_overview_premium_bonds_cap_alert_uses_specific_premium_bonds_cta(app, client, make_user):
    uid, username, password = make_user(username="overview-premium-bonds-cap", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")
    today_str = date.today().strftime("%Y-%m-%d")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                "UPDATE assumptions SET date_of_birth = '1990-01-01', salary_day = 1 WHERE user_id = ?",
                (uid,),
            )
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'PB', 'Premium Bonds', 51000, 1, 'manual')
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Emergency fund', 5000, '', '', '')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key)
                VALUES (?, ?, ?, ?)
                """,
                (today_str, account_id, 51000, month_key),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "NS&amp;I&#39;s current maximum eligible holding is £50,000" in html
    assert "Review Premium Bonds" in html
    assert "Review accounts" not in html
    assert 'href="/accounts/"' in html


def test_overview_isa_allowance_alert_uses_specific_isa_cta(app, client, make_user):
    uid, username, password = make_user(username="overview-isa-allowance-alert", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")
    today_str = date.today().strftime("%Y-%m-%d")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE assumptions
                SET date_of_birth = '1990-01-01', salary_day = 1, isa_allowance = 1000
                WHERE user_id = ?
                """,
                (uid,),
            )
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 500, 1, 'manual')
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Emergency fund', 5000, '', '', '')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key)
                VALUES (?, ?, ?, ?)
                """,
                (today_str, account_id, 1000, month_key),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "At your current contribution pace, you&#39;re estimated to exceed your ISA allowance" in html
    assert "You&#39;re on track to exceed your ISA allowance" not in html
    assert "Review ISA allowance" in html
    assert "View allowance" not in html
    assert 'href="/allowance/"' in html


def test_overview_pension_allowance_alert_uses_specific_pension_cta(app, client, make_user):
    uid, username, password = make_user(username="overview-pension-allowance-alert", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")
    today_str = date.today().strftime("%Y-%m-%d")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE assumptions
                SET date_of_birth = '1990-01-01', salary_day = 1, pension_annual_allowance = 1000
                WHERE user_id = ?
                """,
                (uid,),
            )
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active, valuation_mode)
                VALUES (?, 'SIPP', 'SIPP', 1000, 500, 1, 'manual')
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Retirement', 5000, '', '', '')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key)
                VALUES (?, ?, ?, ?)
                """,
                (today_str, account_id, 1000, month_key),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "At your current contribution pace, you&#39;re estimated to exceed your pension annual allowance" in html
    assert "You&#39;re on track to exceed your pension annual allowance" not in html
    assert "Review pension annual allowance" in html
    assert "Review pension allowance" not in html
    assert "View allowance" not in html
    assert 'href="/allowance/#pension"' in html


def test_overview_pension_allowance_alert_respects_carry_forward(app, client, make_user):
    uid, username, password = make_user(username="overview-pension-carry-forward-alert", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")
    today_str = date.today().strftime("%Y-%m-%d")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE assumptions
                SET date_of_birth = '1990-01-01', salary_day = 1, pension_annual_allowance = 1000
                WHERE user_id = ?
                """,
                (uid,),
            )
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active, valuation_mode)
                VALUES (?, 'SIPP', 'SIPP', 1000, 500, 1, 'manual')
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Retirement', 5000, '', '', '')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key)
                VALUES (?, ?, ?, ?)
                """,
                (today_str, account_id, 1000, month_key),
            )
            conn.execute(
                """
                INSERT INTO pension_carry_forward (user_id, tax_year, unused_allowance)
                VALUES (?, '2024-25', 10000)
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "At your current contribution pace, you&#39;re estimated to exceed your pension annual allowance" not in html
    assert "At your current contribution pace, you&#39;re estimated to exceed your pension annual allowance by" not in html


def test_overview_isa_allowance_card_uses_specific_topup_cta(app, client, make_user):
    uid, username, password = make_user(username="overview-isa-card-topup-cta", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")
    today_str = date.today().strftime("%Y-%m-%d")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE assumptions
                SET date_of_birth = '1990-01-01', salary_day = 1, isa_allowance = 20000
                WHERE user_id = ?
                """,
                (uid,),
            )
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 1, 'manual')
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Emergency fund', 5000, '', '', '')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key)
                VALUES (?, ?, ?, ?)
                """,
                (today_str, account_id, 1000, month_key),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "ISA allowance" in html
    assert "ISA Allowance" not in html
    assert html.count("includes Lifetime ISA") == 2
    assert "includes LISA" not in html
    assert html.count("days left in the tax year") == 2
    assert "days left in tax year" not in html
    assert 'href="/allowance/#isa-log-panel"' in html
    assert '>Record ISA top-up</a>' in html
    assert '>Record top-up</a>' not in html


def test_overview_allowance_cards_use_estimated_tax_year_end_copy(app, client, make_user):
    uid, username, password = make_user(username="overview-allowance-estimated-copy", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")
    today_str = date.today().strftime("%Y-%m-%d")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE assumptions
                SET date_of_birth = '1990-01-01', salary_day = 1, isa_allowance = 20000, pension_annual_allowance = 60000
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
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active, valuation_mode)
                VALUES (?, 'Pension', 'SIPP', 1000, 300, 1, 'manual')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Retirement', 5000, '', '', '')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key)
                SELECT ?, id, 1000, ? FROM accounts WHERE user_id = ?
                """,
                (today_str, month_key, uid),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert html.count("Tax year-end estimate:") == 4
    assert "Estimated by tax year end:" not in html
    assert "On track:" not in html


def test_overview_isa_allowance_card_uses_specific_review_cta(app, client, make_user):
    uid, username, password = make_user(username="overview-isa-card-review-cta", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")
    today_str = date.today().strftime("%Y-%m-%d")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE assumptions
                SET date_of_birth = '1990-01-01', salary_day = 1, isa_allowance = 20000
                WHERE user_id = ?
                """,
                (uid,),
            )
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 1, 'manual')
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Emergency fund', 5000, '', '', '')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key)
                VALUES (?, ?, ?, ?)
                """,
                (today_str, account_id, 1000, month_key),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "ISA allowance" in html
    assert "ISA Allowance" not in html
    assert 'href="/allowance/#isa"' in html
    assert '>Review ISA allowance</a>' in html
    assert 'href="/allowance/#isa" class="badge badge-sm">View breakdown</a>' not in html


def test_overview_lisa_allowance_card_uses_specific_review_cta(app, client, make_user):
    uid, username, password = make_user(username="overview-lisa-card-topup-cta", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")
    today_str = date.today().strftime("%Y-%m-%d")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

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
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'LISA', 'Cash LISA', 1000, 1, 'manual')
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Emergency fund', 5000, '', '', '')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key)
                VALUES (?, ?, ?, ?)
                """,
                (today_str, account_id, 1000, month_key),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert '<h2>Lifetime ISA allowance ' in html
    assert '<h2>LISA allowance ' not in html
    assert "Lifetime ISA Allowance" not in html
    assert 'href="/allowance/#isa"' in html
    assert '>Review Lifetime ISA allowance</a>' in html
    assert '>Review LISA allowance</a>' not in html
    assert '>Record Lifetime ISA top-up</a>' in html
    assert '>Record LISA top-up</a>' not in html
    assert 'aria-label="Lifetime ISA allowance used"' in html
    assert 'aria-label="LISA allowance used"' not in html
    assert 'href="/allowance/#isa" class="badge badge-sm">View breakdown</a>' not in html
    assert '>Record top-up</a>' not in html


def test_overview_pension_allowance_card_uses_specific_review_cta(app, client, make_user):
    uid, username, password = make_user(username="overview-pension-card-review-cta", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")
    today_str = date.today().strftime("%Y-%m-%d")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE assumptions
                SET date_of_birth = '1990-01-01', salary_day = 1, pension_annual_allowance = 60000
                WHERE user_id = ?
                """,
                (uid,),
            )
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'Pension', 'Pension', 1000, 1, 'manual')
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Retirement', 500000, '', '', '')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key)
                VALUES (?, ?, ?, ?)
                """,
                (today_str, account_id, 1000, month_key),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert '<h2>Pension annual allowance ' in html
    assert '<h2>Pension allowance ' not in html
    assert "Pension Annual Allowance" not in html
    assert html.count("personal limit:") == 2
    assert "Personal limit:" not in html
    assert 'href="/allowance/#pension"' in html
    assert '>Review pension annual allowance</a>' in html
    assert '>Review pension allowance</a>' not in html
    assert '>Record pension contribution</a>' in html
    assert 'aria-label="Pension annual allowance used"' in html
    assert 'aria-label="Pension allowance used"' not in html
    assert 'href="/allowance/#pension" class="badge badge-sm">View breakdown</a>' not in html
    assert '>Record contribution</a>' not in html


def test_overview_unused_isa_allowance_alert_uses_specific_topup_cta(app, client, make_user, monkeypatch):
    uid, username, password = make_user(username="overview-unused-isa-allowance-alert", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")
    today_str = date.today().strftime("%Y-%m-%d")

    import app.routes.overview as overview_route
    monkeypatch.setattr(overview_route, "days_until_tax_year_end", lambda _date: 14)

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE assumptions
                SET date_of_birth = '1990-01-01', salary_day = 1, isa_allowance = 20000
                WHERE user_id = ?
                """,
                (uid,),
            )
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active, valuation_mode)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 1000, 1, 'manual')
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Emergency fund', 5000, '', '', '')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key)
                VALUES (?, ?, ?, ?)
                """,
                (today_str, account_id, 1000, month_key),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "days left in the tax year" in html
    assert 'href="/allowance/#isa-log-panel"' in html
    assert '>Record ISA top-up</a>' in html
