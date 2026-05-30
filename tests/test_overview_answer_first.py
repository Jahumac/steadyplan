from datetime import date


def test_overview_getting_started_card_prioritises_basics_and_defers_deeper_steps(app, client, make_user):
    _, username, password = make_user(username="overview-onboarding-new", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Start here" in html
    assert "You only need the basics to begin." in html
    assert "Essential to start" in html
    assert "Do later" in html
    assert "Complete your profile" in html
    assert "Add your first account" in html
    assert "Set a goal once you know what you want to aim for." in html
    assert "Do your first monthly update after your first contribution or balance change settles." in html
    assert 'href="/settings/?mode=edit"' in html
    assert "Monthly review" not in html
    assert "Status:" not in html
    assert "Nothing in the shell yet" not in html
    assert "<h2>Accounts</h2>" not in html
    assert "Total Net Worth" not in html
    assert "Accessible vs locked" not in html
    assert "Portfolio Value" not in html
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
    assert "Start with one real account so Overview has something concrete to show." in html
    assert "Add account" in html
    assert 'href="/accounts/?mode=create"' in html
    assert "Nothing in the shell yet" not in html
    assert "<h2>Accounts</h2>" not in html
    assert "Total Net Worth" not in html
    assert "Accessible vs locked" not in html
    assert "Portfolio Value" not in html


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

    assert "Set a first goal" in html
    assert "Accessible vs locked" in html
    assert "Portfolio Value" not in html
    assert "ISA Allowance" not in html
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

    assert "Accessible vs locked" in html
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

    assert "<h2>Accounts</h2>" in html
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
    assert "ISA Allowance" in html
    assert "Pension Allowance" in html
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

    assert "<p class=\"eyebrow\">Goals</p>" in html
    assert "Emergency fund progress" in html
    assert "House deposit progress" in html



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

    assert "Set a first goal" in html
    assert "Accessible vs locked" in html
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

    assert "ISA Allowance" in html
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

    assert "Accessible vs locked" in html
    assert "Accessible now" in html
    assert "Locked later" in html
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

    assert "Accessible vs locked" in html
    assert "Open Planning" in html
    assert "Accessible now" in html
    assert "Restricted" in html
    assert "Locked later" in html
    assert html.count('class="overview-access-value"') == 1
    assert "£2,000" in html
    assert "17% of your current total is usually reachable before pension age" in html
    assert "The top summary keeps the headline locked amount visible." in html
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

    assert "Accessible vs locked" in html
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

    assert "Accessible now" in html
    assert "Locked later" in html
    assert "Monthly contributions" in html
    assert "Projected at retirement" in html
    assert "Goal progress" not in html
    assert "Tax Year " not in html



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
    assert "Locked later" in html
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
    assert "Projected at retirement" in html
    assert html.count("Locked later") == 1



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

    assert "Complete your profile" in html
    assert "Accessible now" in html
    assert "Locked later" in html
    assert "Monthly contributions" in html
    assert "Projected at retirement" not in html
    assert "Scenario estimate based on your current balances, contribution settings, and assumptions in Settings." not in html


def test_overview_review_due_does_not_repeat_monthly_update_nudge(app, client, make_user):
    uid, username, password = make_user(username="overview-review-due", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

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

    assert "Your investments should be settled by now" in html
    assert "Start monthly update" in html
    assert "Your next nudge" not in html
    assert "Status:" not in html


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
    assert "Go to Settings" in html
    assert "Your next nudge" not in html
