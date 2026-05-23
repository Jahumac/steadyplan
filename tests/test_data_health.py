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
            "dashboard_name": "Shelly",
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

def test_missing_goal_produces_warning(app, setup_missing_goal_user):
    with app.app_context():
        summary = build_data_health_summary(setup_missing_goal_user)
        assert summary["overall_status"] == HEALTH_STATUS_WARNING
        titles = [item["title"] for item in summary["health_items"]]
        assert "Some goals are missing a target amount" in titles

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
    assert "Download a JSON backup" in html
    assert "Check a backup file" in html


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
                "VALUES (?, 0.07, 65, 40, 1500000, 20000, 4000, 500, 0.9, 0.1, 3000, 'Shelly', datetime('now'))",
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
    assert "Data Health" not in html
    assert "Looks good" not in html


def test_overview_data_health_visible_when_warnings_exist(app, client, make_user):
    _, username, password = make_user(username="dh-warn", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Data Health" in html
    assert "Needs attention" in html
    assert "/settings#accounts" in html
    assert ">Review<" in html
    assert "alert-warning" in html
