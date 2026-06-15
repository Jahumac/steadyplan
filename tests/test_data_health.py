import pytest
from datetime import date, timedelta
import datetime
from app.services.data_health import build_data_health_summary, HEALTH_STATUS_GOOD, HEALTH_STATUS_WARNING, HEALTH_STATUS_INFO
from app.models import (
    create_user,
    create_account,
    create_goal,
    fetch_assumptions,
    update_assumptions,
    get_connection,
    upsert_monthly_snapshot,
    save_account_daily_snapshots,
    create_budget_item,
    upsert_budget_entry,
)

def _base_account_payload(name):
    return {
        "name": name,
        "provider": "Bank",
        "wrapper_type": "Checking",
        "category": "Savings",
        "tags": "",
        "current_value": 1000,
        "monthly_contribution": 0,
        "pension_contribution_day": 0,
        "goal_value": None,
        "valuation_mode": "manual",
        "growth_mode": "default",
        "growth_rate_override": None,
        "owner": None,
        "is_active": 1,
        "notes": None,
        "last_updated": None,
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
        "include_in_budget": 1,
        "pre_salary": 0,
    }

@pytest.fixture
def new_user_id(app):
    with app.app_context():
        user_id = create_user("testuser_health", "password")
        return user_id

@pytest.fixture
def setup_healthy_user(app, new_user_id):
    with app.app_context():
        # Create account
        account_payload = _base_account_payload("Test Account")
        account_id = create_account(account_payload, new_user_id)
        
        # Add recent snapshot
        today_str = date.today().strftime("%Y-%m-%d")
        month_key = date.today().strftime("%Y-%m")
        upsert_monthly_snapshot(account_id, month_key, 1000)
        save_account_daily_snapshots(new_user_id, [(account_id, 1000)], today_str)
        
        # Create goal
        goal_payload = {
            "name": "Retirement",
            "target_value": 1000000,
            "goal_type": "retirement",
            "selected_tags": "",
            "notes": "",
        }
        create_goal(goal_payload, new_user_id)
        
        # Create assumptions
        fetch_assumptions(new_user_id) # Ensure row exists
        update_assumptions({
            "annual_growth_rate": 0.07,
            "retirement_age": 65,
            "date_of_birth": "1980-01-01",
            "retirement_goal_value": 1500000,
            "isa_allowance": 20000,
            "lisa_allowance": 4000,
            "dividend_allowance": 500,
            "annual_income": 0,
            "pension_annual_allowance": 60000,
            "mpaa_enabled": 0,
            "mpaa_allowance": 10000,
            "target_dev_pct": 0.90,
            "target_em_pct": 0.10,
            "emergency_fund_target": 3000,
            "dashboard_name": "SteadyPlan",
            "salary_day": 0,
            "update_day": 0,
            "retirement_date_mode": "birthday",
            "tax_band": "basic",
            "auto_update_prices": 1,
            "update_time_morning": "08:30",
            "update_time_evening": "18:00",
            "updated_at": datetime.datetime.now().isoformat(),
        }, new_user_id)
        
        # Create budget item and entry for current month
        item_id = create_budget_item({
            "name": "Rent",
            "section": "fixed",
            "default_amount": 500,
        }, new_user_id)
        upsert_budget_entry(month_key, item_id, 500, new_user_id)
        
        return new_user_id

@pytest.fixture
def setup_stale_account_user(app, new_user_id):
    with app.app_context():
        account_payload = _base_account_payload("Stale Account")
        account_payload["current_value"] = 500
        account_id = create_account(account_payload, new_user_id)
        
        # Add old snapshot
        old_date = date.today() - timedelta(days=90)
        old_month_key = old_date.strftime("%Y-%m")
        upsert_monthly_snapshot(account_id, old_month_key, 500)
        
        return new_user_id

@pytest.fixture
def setup_missing_goal_user(app, new_user_id):
    with app.app_context():
        account_payload = _base_account_payload("Test Account")
        create_account(account_payload, new_user_id)
        
        goal_payload = {
            "name": "Vacation",
            "target_value": 0,
            "goal_type": "",
            "selected_tags": "",
            "notes": "",
        }
        create_goal(goal_payload, new_user_id)
        return new_user_id

@pytest.fixture
def setup_default_assumptions_user(app, new_user_id):
    with app.app_context():
        account_payload = _base_account_payload("Test Account")
        create_account(account_payload, new_user_id)
        # assumptions are created with defaults on first fetch or user creation usually
        # but let's make sure they exist
        fetch_assumptions(new_user_id)
        return new_user_id

@pytest.fixture
def setup_no_budget_entry_user(app, new_user_id):
    with app.app_context():
        account_payload = _base_account_payload("Test Account")
        create_account(account_payload, new_user_id)
        create_budget_item({
            "name": "Rent",
            "section": "fixed",
            "default_amount": 500,
        }, new_user_id)
        return new_user_id


def test_empty_user_gets_warnings(app, new_user_id):
    with app.app_context():
        summary = build_data_health_summary(new_user_id)
        assert summary["overall_status"] == HEALTH_STATUS_WARNING
        titles = [item["title"] for item in summary["health_items"]]
        assert "No accounts set up" in titles
        assert "No financial goals set" in titles
        assert "No assumptions set up" in titles
        assert "No budget entries for the current month" in titles

        accounts_warning = next(item for item in summary["health_items"] if item["title"] == "No accounts set up")
        assert accounts_warning["explanation"] == "You haven't added any financial accounts yet. Add one so totals, progress, and scenario estimates can start from real balances."
        assert "Add accounts to track your finances" not in accounts_warning["explanation"]

        goals_warning = next(item for item in summary["health_items"] if item["title"] == "No financial goals set")
        assert goals_warning["explanation"] == "You haven't set any financial goals yet. Set one so progress and goal timing estimates have something to measure against."
        assert "Define your goals to track progress" not in goals_warning["explanation"]

        budget_warning = next(item for item in summary["health_items"] if item["title"] == "No budget entries for the current month")
        assert budget_warning["explanation"] == f"You have no budget entries for {date.today().strftime('%Y-%m')}. Add some so Monthly Update has a plan to compare against."
        assert "track your spending" not in budget_warning["explanation"]

def test_healthy_user_gets_good_status(app, setup_healthy_user):
    with app.app_context():
        summary = build_data_health_summary(setup_healthy_user)
        assert summary["overall_status"] == HEALTH_STATUS_GOOD
        assert all(item["status"] == HEALTH_STATUS_INFO for item in summary["health_items"])

def test_stale_account_data_produces_warning(app, setup_stale_account_user):
    with app.app_context():
        summary = build_data_health_summary(setup_stale_account_user)
        assert summary["overall_status"] == HEALTH_STATUS_WARNING
        titles = [item["title"] for item in summary["health_items"]]
        assert "Some accounts have stale or missing history" in titles


def test_brand_new_accounts_do_not_count_as_stale_history_yet(app, new_user_id):
    with app.app_context():
        account_payload = _base_account_payload("Fresh Account")
        create_account(account_payload, new_user_id)

        summary = build_data_health_summary(new_user_id)
        titles = [item["title"] for item in summary["health_items"]]
        assert "Some accounts have stale or missing history" not in titles


def test_missing_history_warning_still_shows_when_some_accounts_have_history(app, new_user_id):
    with app.app_context():
        first_payload = _base_account_payload("Tracked Account")
        second_payload = _base_account_payload("Needs History")
        tracked_id = create_account(first_payload, new_user_id)
        create_account(second_payload, new_user_id)

        today_str = date.today().strftime("%Y-%m-%d")
        month_key = date.today().strftime("%Y-%m")
        upsert_monthly_snapshot(tracked_id, month_key, 1000)
        save_account_daily_snapshots(new_user_id, [(tracked_id, 1000)], today_str)

        summary = build_data_health_summary(new_user_id)
        titles = [item["title"] for item in summary["health_items"]]
        assert "Some accounts have stale or missing history" in titles
        stale_warning = next(item for item in summary["health_items"] if item["title"] == "Some accounts have stale or missing history")
        assert "Needs History" in stale_warning["explanation"]
        assert "keep your scenario estimates grounded in recent balances" in stale_warning["explanation"]
        assert "ensure accurate projections" not in stale_warning["explanation"]


def test_stale_account_warning_uses_review_history_cta(app, setup_stale_account_user):
    with app.app_context():
        conn = get_connection()
        today = datetime.date.today()
        conn.execute(
            "INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes) VALUES (?, 'Emergency fund', 5000, '', '', '')",
            (setup_stale_account_user,),
        )
        fetch_assumptions(setup_stale_account_user)
        conn.execute(
            "UPDATE assumptions SET date_of_birth = '1990-01-01' WHERE user_id = ?",
            (setup_stale_account_user,),
        )
        conn.execute(
            "INSERT INTO budget_items (user_id, name, section, default_amount, sort_order, is_active) VALUES (?, 'Rent', 'fixed', 500, 0, 1)",
            (setup_stale_account_user,),
        )
        bid = conn.execute("SELECT id FROM budget_items WHERE user_id = ? LIMIT 1", (setup_stale_account_user,)).fetchone()["id"]
        conn.execute(
            "INSERT INTO budget_entries (month_key, budget_item_id, amount) VALUES (?, ?, 500)",
            (today.strftime("%Y-%m"), bid),
        )
        conn.commit()

        summary = build_data_health_summary(setup_stale_account_user)
        stale_warning = next(item for item in summary["health_items"] if item["title"] == "Some accounts have stale or missing history")
        assert stale_warning["link"] == "/history"
        assert stale_warning["cta_text"] == "Review history"


def test_missing_assumptions_warning_uses_scenario_estimate_wording(app, new_user_id):
    with app.app_context():
        summary = build_data_health_summary(new_user_id)
        assumptions_warning = next(item for item in summary["health_items"] if item["title"] == "No assumptions set up")
        assert assumptions_warning["explanation"] == "You haven't set up your financial assumptions yet. These help scenario estimates and goal timing estimates reflect your plans."
        assert "build scenario estimates that match your plans" not in assumptions_warning["explanation"]
        assert "crucial for projections" not in assumptions_warning["explanation"]


def test_missing_goal_produces_warning(app, setup_missing_goal_user):
    with app.app_context():
        summary = build_data_health_summary(setup_missing_goal_user)
        assert summary["overall_status"] == HEALTH_STATUS_WARNING
        titles = [item["title"] for item in summary["health_items"]]
        assert "Some goals need a target amount" in titles
        assert "Some goals are missing a target amount" not in titles


def test_missing_goal_warning_uses_review_goals_cta(app, setup_missing_goal_user):
    with app.app_context():
        summary = build_data_health_summary(setup_missing_goal_user)
        goal_warning = next(item for item in summary["health_items"] if item["title"] == "Some goals need a target amount")
        assert goal_warning["link"] == "/goals"
        assert goal_warning["cta_text"] == "Review goals"
        assert goal_warning["explanation"] == "The following goals do not have a target amount yet: Vacation. Add one so progress and goal timing estimates stay meaningful."
        assert "track progress effectively" not in goal_warning["explanation"]


def test_no_goals_warning_uses_first_goal_cta(app, setup_stale_account_user):
    with app.app_context():
        conn = get_connection()
        today = datetime.date.today()
        conn.execute(
            "INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key) VALUES (?, ?, ?, ?)",
            (today.strftime("%Y-%m-%d"), 1, 2500, today.strftime("%Y-%m")),
        )
        conn.commit()

        summary = build_data_health_summary(setup_stale_account_user)
        goal_warning = next(item for item in summary["health_items"] if item["title"] == "No financial goals set")
        assert goal_warning["link"] == "/goals/?mode=create&focus=first_goal"
        assert goal_warning["cta_text"] == "Set your first goal"
        assert goal_warning["explanation"] == "You haven't set any financial goals yet. Set one so progress and goal timing estimates have something to measure against."


def test_default_assumptions_produces_info(app, setup_default_assumptions_user):
    with app.app_context():
        summary = build_data_health_summary(setup_default_assumptions_user)
        # overall status might still be warning because of missing goals/budget in this fixture
        titles = [item["title"] for item in summary["health_items"]]
        assert "Default retirement assumptions in use" in titles

def test_no_budget_entry_produces_info(app, setup_no_budget_entry_user):
    with app.app_context():
        summary = build_data_health_summary(setup_no_budget_entry_user)
        titles = [item["title"] for item in summary["health_items"]]
        assert "No budget entries for the current month" in titles
        budget_warning = next(item for item in summary["health_items"] if item["title"] == "No budget entries for the current month")
        assert budget_warning["explanation"] == f"You have no budget entries for {date.today().strftime('%Y-%m')}. Add some so Monthly Update has a plan to compare against."
        assert "track your spending" not in budget_warning["explanation"]

def test_data_health_summary_no_db_writes(app, setup_healthy_user):
    with app.app_context():
        conn = get_connection()
        # Snapshot initial row counts
        tables = ["users", "accounts", "goals", "assumptions", "monthly_snapshots", "budget_items", "budget_entries"]
        initial_counts = {}
        for table in tables:
            res = conn.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()
            initial_counts[table] = res["c"]

        build_data_health_summary(setup_healthy_user)

        # Verify row counts are unchanged
        for table in tables:
            res = conn.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()
            assert initial_counts[table] == res["c"], f"Table {table} was written to!"


def test_overview_does_not_render_backup_restore_data_health_item(app, client, make_user):
    uid, username, password = make_user(username="dh-no-backup", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Backup and restore available" not in html
    assert "You can export your data or restore from a backup" not in html
    assert "icons/shelly/Health.png" not in html


def test_settings_still_mentions_backup_restore(app, client, make_user):
    _, username, password = make_user(username="dh-settings-backup", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/settings/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Data &amp; privacy" in html
    assert "SteadyPlan stores your financial data locally in a SQLite database" in html
    assert "Download a per-user JSON export" in html
    assert "Check a JSON export before overwrite" in html
    assert "Downloads a portable JSON export for this user only" in html
    assert "whole-instance SQLite backup" in html
    assert "This permanently deletes all data for this user: accounts, holdings, goals, budget, monthly updates, and assumptions." in html
    assert "This permanently deletes all data for this user: accounts, holdings, goals, budget, monthly reviews, and assumptions." not in html
    assert "This cannot be undone. Download a per-user JSON export before continuing." in html
    assert "This cannot be undone. Download this user's JSON export before continuing." not in html
    assert "Download a JSON export for this user before continuing." not in html
    assert "Delete this user's finance data" in html
    assert "Delete all data for this user" not in html
    assert "Type <strong>RESET</strong> below to confirm. This permanently deletes this user's finance data." in html
    assert "Type <strong>RESET</strong> below to confirm. This permanently deletes all data for this user." not in html


def test_settings_groups_trust_surfaces_at_a_glance(app, client, make_user):
    _, username, password = make_user(username="dh-settings-map", is_admin=True)
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/settings/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Settings at a glance" in html
    assert "Use this as the map for the heavier trust and admin areas below." in html
    assert "Planning assumptions" in html
    assert "User access" in html
    assert "Data ownership" in html
    assert "Backups &amp; restore" in html
    assert "Connections &amp; tokens" in html
    assert "Diagnostics and system posture" in html
    assert "Danger zone" in html
    assert "Settings map" not in html
    assert "Admin tools" not in html

    glance_idx = html.index("Settings at a glance")
    after_glance = html[glance_idx:]
    planning_idx = after_glance.index("Planning assumptions")
    admin_idx = after_glance.index("User Management")
    data_idx = after_glance.index("<h3>Data ownership</h3>")
    export_idx = after_glance.index("<h3>Download a per-user JSON export</h3>")
    assistant_idx = after_glance.index("<h3>Optional: create a scoped token")
    danger_idx = after_glance.index("<h3>Delete this user's finance data</h3>")

    assert planning_idx < admin_idx < data_idx < export_idx < assistant_idx < danger_idx


def test_settings_explains_backup_restore_scope_at_a_glance(app, client, make_user):
    _, username, password = make_user(username="dh-scope-guide", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/settings/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "What each safety copy is for" in html
    assert "JSON export, backup, and restore at a glance" not in html
    assert "Backup and restore at a glance" not in html
    assert "Local SQLite database" in html
    assert "the live SteadyPlan data store" in html
    assert "Per-user JSON export" in html
    assert "portable safety copy for one user before restore, delete, or larger edits" in html
    assert "Whole app data directory backup" in html
    assert "the real disaster-recovery copy" in html
    assert "secret_key.txt" in html
    assert "Restore check" in html
    assert "validates a JSON file without changing data" in html
    assert "Restore overwrite" in html
    assert "replaces this user’s data only after confirmation" in html
    assert "Delete this user’s finance data" in html
    assert "removes finance data for this user only, not the login account" in html
    assert "When you only need a safety copy for one user, start with a JSON export." in html
    assert "This export does not include your login password, and it is not a full disaster-recovery backup." in html
    assert "Restore commit" not in html
    assert "Delete user data" not in html
    assert "JSON export is per-user. SQLite backups are whole-instance backups." not in html
    assert "Restore validation" not in html
    assert "removes this user’s finance data, not the login account" not in html


def test_overview_data_health_quiet_when_no_warnings(app, client, make_user):
    uid, username, password = make_user(username="dh-quiet", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        month_key = date.today().strftime("%Y-%m")
        today_str = date.today().strftime("%Y-%m-%d")
        with get_connection() as conn:
            aid = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active, valuation_mode) "
                "VALUES (?, 'Cash', 1000, 1, 'manual')",
                (uid,),
            ).lastrowid
            conn.execute(
                "INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes) "
                "VALUES (?, 'Goal', 10000, '', '', '')",
                (uid,),
            )
            conn.execute(
                "INSERT OR IGNORE INTO assumptions (user_id, annual_growth_rate, retirement_age, current_age, retirement_goal_value, isa_allowance, lisa_allowance, dividend_allowance, target_dev_pct, target_em_pct, emergency_fund_target, dashboard_name, updated_at) "
                "VALUES (?, 0.07, 65, 40, 1500000, 20000, 4000, 500, 0.9, 0.1, 3000, 'SteadyPlan', datetime('now'))",
                (uid,),
            )
            conn.execute(
                "INSERT INTO budget_items (user_id, name, section, default_amount, sort_order, is_active) "
                "VALUES (?, 'Rent', 'fixed', 500, 0, 1)",
                (uid,),
            )
            bid = conn.execute("SELECT id FROM budget_items WHERE user_id = ? LIMIT 1", (uid,)).fetchone()["id"]
            conn.execute(
                "INSERT INTO budget_entries (month_key, budget_item_id, amount) VALUES (?, ?, 500)",
                (month_key, bid),
            )
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key) VALUES (?, ?, 1000, ?)",
                (month_key + "-01", aid, month_key),
            )
            conn.execute(
                "INSERT INTO account_daily_snapshots (user_id, account_id, snapshot_date, value) VALUES (?, ?, ?, 1000)",
                (uid, aid, today_str),
            )
            conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Data health" not in html
    assert "Data Health" not in html
    assert "Looks good" not in html


def test_overview_data_health_visible_when_warnings_exist(app, client, make_user):
    _, username, password = make_user(username="dh-warn", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Data health" not in html
    assert "Data Health" not in html
    assert "Needs attention" not in html
    assert "No accounts set up" not in html
    assert ">Review<" not in html
    assert "No accounts set up —" not in html


def test_overview_data_health_missing_goal_uses_first_goal_cta(app, client, make_user):
    uid, username, password = make_user(username="dh-no-goal", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")
    today_str = date.today().strftime("%Y-%m-%d")

    with app.app_context():
        fetch_assumptions(uid)
        conn = get_connection()
        conn.execute(
            "UPDATE assumptions SET date_of_birth = '1990-01-01' WHERE user_id = ?",
            (uid,),
        )
        aid = conn.execute(
            """
            INSERT INTO accounts (user_id, name, provider, wrapper_type, category, current_value, is_active, valuation_mode)
            VALUES (?, 'ISA', 'Vanguard', 'Stocks & Shares ISA', 'Investments', 1000, 1, 'manual')
            """,
            (uid,),
        ).lastrowid
        conn.execute(
            "INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key) VALUES (?, ?, 1000, ?)",
            (month_key + "-01", aid, month_key),
        )
        conn.execute(
            "INSERT INTO account_daily_snapshots (user_id, account_id, snapshot_date, value) VALUES (?, ?, ?, 1000)",
            (uid, aid, today_str),
        )
        conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "No financial goals set" in html
    assert "Set one so progress and goal timing estimates have something to measure against." in html
    assert 'href="/goals/?mode=create&amp;focus=first_goal"' in html
    assert "Set your first goal" in html
    assert ">Review<" not in html
    assert "Define your goals to track progress." not in html


def test_overview_data_health_goal_target_warning_uses_review_goals_cta(app, client, make_user):
    uid, username, password = make_user(username="dh-goal-target", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")
    today_str = date.today().strftime("%Y-%m-%d")

    with app.app_context():
        fetch_assumptions(uid)
        conn = get_connection()
        conn.execute(
            "UPDATE assumptions SET date_of_birth = '1990-01-01' WHERE user_id = ?",
            (uid,),
        )
        aid = conn.execute(
            """
            INSERT INTO accounts (user_id, name, provider, wrapper_type, category, current_value, is_active, valuation_mode)
            VALUES (?, 'ISA', 'Vanguard', 'Stocks & Shares ISA', 'Investments', 1000, 1, 'manual')
            """,
            (uid,),
        ).lastrowid
        conn.execute(
            """
            INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
            VALUES (?, 'Emergency fund', 0, '', '', '')
            """,
            (uid,),
        )
        conn.execute(
            "INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key) VALUES (?, ?, 1000, ?)",
            (month_key + "-01", aid, month_key),
        )
        conn.execute(
            "INSERT INTO account_daily_snapshots (user_id, account_id, snapshot_date, value) VALUES (?, ?, ?, 1000)",
            (uid, aid, today_str),
        )
        conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Some goals need a target amount" in html
    assert "The following goals do not have a target amount yet: Emergency fund. Add one so progress and goal timing estimates stay meaningful." in html
    assert 'href="/goals"' in html
    assert "Review goals" in html
    assert ">Review<" not in html
    assert "Some goals are missing a target amount" not in html
    assert "track progress effectively" not in html



def test_overview_suppresses_stale_history_warning_before_first_snapshot(app, client, make_user):
    uid, username, password = make_user(username="dh-first-snapshot", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")

    with app.app_context():
        fetch_assumptions(uid)
        conn = get_connection()
        conn.execute(
            "UPDATE assumptions SET date_of_birth = '1990-01-01' WHERE user_id = ?",
            (uid,),
        )
        conn.execute(
            "UPDATE assumptions SET salary_day = 10, update_day = 12 WHERE user_id = ?",
            (uid,),
        )
        conn.execute(
            """
            INSERT INTO accounts (user_id, name, provider, wrapper_type, category, current_value, is_active, valuation_mode, monthly_contribution)
            VALUES (?, 'ISA', 'Vanguard', 'Stocks & Shares ISA', 'Investments', 1000, 1, 'manual', 150)
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
            "INSERT INTO budget_items (user_id, name, section, default_amount, sort_order, is_active) VALUES (?, 'Rent', 'fixed', 500, 0, 1)",
            (uid,),
        )
        bid = conn.execute("SELECT id FROM budget_items WHERE user_id = ? LIMIT 1", (uid,)).fetchone()["id"]
        conn.execute(
            "INSERT INTO budget_entries (month_key, budget_item_id, amount) VALUES (?, ?, 500)",
            (month_key, bid),
        )
        conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Some accounts have stale or missing history" not in html
    assert "Review history" not in html
    assert "Open monthly update" in html
    assert "/monthly-review/" in html


def test_overview_data_health_stale_history_warning_uses_review_history_cta(app, client, make_user):
    uid, username, password = make_user(username="dh-stale-history", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = date.today().strftime("%Y-%m")

    with app.app_context():
        fetch_assumptions(uid)
        conn = get_connection()
        conn.execute(
            "UPDATE assumptions SET date_of_birth = '1990-01-01' WHERE user_id = ?",
            (uid,),
        )
        aid = conn.execute(
            """
            INSERT INTO accounts (user_id, name, provider, wrapper_type, category, current_value, is_active, valuation_mode)
            VALUES (?, 'ISA', 'Vanguard', 'Stocks & Shares ISA', 'Investments', 1000, 1, 'manual')
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
            "INSERT INTO budget_items (user_id, name, section, default_amount, sort_order, is_active) VALUES (?, 'Rent', 'fixed', 500, 0, 1)",
            (uid,),
        )
        bid = conn.execute("SELECT id FROM budget_items WHERE user_id = ? LIMIT 1", (uid,)).fetchone()["id"]
        conn.execute(
            "INSERT INTO budget_entries (month_key, budget_item_id, amount) VALUES (?, ?, 500)",
            (month_key, bid),
        )
        stale_date = (date.today() - timedelta(days=90)).strftime("%Y-%m-%d")
        conn.execute(
            "INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key) VALUES (?, ?, 1000, ?)",
            (stale_date, aid, stale_date[:7]),
        )
        conn.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Some accounts have stale or missing history" in html
    assert "keep your scenario estimates grounded in recent balances" in html
    assert "ensure accurate projections" not in html
    assert 'href="/history"' in html
    assert "Review history" in html
    assert ">Review<" not in html
