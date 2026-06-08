"""DB schema + init_db.

Isolated here so app/models/__init__.py stays focused on CRUD functions
rather than 500 lines of CREATE TABLE + migration boilerplate.
"""
from flask import current_app

from ._conn import get_connection


def _log_migration_error(exc: Exception) -> None:
    """Log unexpected migration errors. Quietly ignores the expected
    'duplicate column' / 'already exists' errors that fire whenever a
    migration is re-run on a DB that already has the change applied —
    those are normal and would otherwise spam the log every startup.
    The SQLite exception message itself names the offending column/table.
    """
    msg = str(exc).lower()
    if "duplicate column" in msg or "already exists" in msg:
        return
    try:
        current_app.logger.warning("Migration step failed: %s", exc)
    except Exception:
        # current_app may not be available during very early init
        pass


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    provider TEXT,
    wrapper_type TEXT,
    category TEXT,
    tags TEXT DEFAULT '',
    current_value REAL DEFAULT 0,
    monthly_contribution REAL DEFAULT 0,
    pension_contribution_day INTEGER DEFAULT 0,
    goal_value REAL,
    valuation_mode TEXT DEFAULT 'manual',
    growth_mode TEXT DEFAULT 'default',
    growth_rate_override REAL,
    owner TEXT,
    is_active INTEGER DEFAULT 1,
    notes TEXT,
    last_updated TEXT
);

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    target_value REAL NOT NULL,
    goal_type TEXT,
    selected_tags TEXT DEFAULT '',
    notes TEXT
);

CREATE TABLE IF NOT EXISTS assumptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    annual_growth_rate REAL DEFAULT 0.07,
    retirement_age INTEGER DEFAULT 60,
    current_age INTEGER DEFAULT 43,
    retirement_goal_value REAL DEFAULT 1000000,
    isa_allowance REAL DEFAULT 20000,
    lisa_allowance REAL DEFAULT 4000,
    dividend_allowance REAL DEFAULT 500,
    target_dev_pct REAL DEFAULT 0.90,
    target_em_pct REAL DEFAULT 0.10,
    emergency_fund_target REAL DEFAULT 3000,
    dashboard_name TEXT DEFAULT 'SteadyPlan',
    auto_update_prices INTEGER DEFAULT 1,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS holding_catalogue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    holding_name TEXT NOT NULL,
    ticker TEXT,
    asset_type TEXT,
    bucket TEXT,
    notes TEXT,
    is_active INTEGER DEFAULT 1,
    last_price REAL,
    price_currency TEXT,
    price_change_pct REAL,
    price_updated_at TEXT
);

CREATE TABLE IF NOT EXISTS holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    holding_catalogue_id INTEGER,
    holding_name TEXT NOT NULL,
    ticker TEXT,
    asset_type TEXT,
    bucket TEXT,
    value REAL DEFAULT 0,
    units REAL,
    price REAL,
    book_cost REAL,
    notes TEXT,
    FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE,
    FOREIGN KEY(holding_catalogue_id) REFERENCES holding_catalogue(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS monthly_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    account_id INTEGER NOT NULL,
    balance REAL DEFAULT 0,
    contribution REAL DEFAULT 0,
    note TEXT,
    FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS allowance_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    tax_year TEXT NOT NULL,
    isa_used REAL DEFAULT 0,
    lisa_used REAL DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS monthly_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    month_key TEXT NOT NULL,
    status TEXT DEFAULT 'not_started',
    notes TEXT,
    completed_at TEXT,
    created_at TEXT,
    updated_at TEXT,
    UNIQUE(user_id, month_key)
);

CREATE TABLE IF NOT EXISTS monthly_review_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    expected_contribution REAL DEFAULT 0,
    contribution_confirmed INTEGER DEFAULT 0,
    holdings_updated INTEGER DEFAULT 0,
    balance_updated INTEGER DEFAULT 0,
    notes TEXT,
    FOREIGN KEY(review_id) REFERENCES monthly_reviews(id) ON DELETE CASCADE,
    FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS budget_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    section TEXT NOT NULL,
    default_amount REAL DEFAULT 0,
    linked_account_id INTEGER,
    linked_debt_id INTEGER,
    notes TEXT,
    sort_order INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    FOREIGN KEY(linked_account_id) REFERENCES accounts(id) ON DELETE SET NULL,
    FOREIGN KEY(linked_debt_id) REFERENCES debts(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS budget_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month_key TEXT NOT NULL,
    budget_item_id INTEGER NOT NULL,
    amount REAL DEFAULT 0,
    FOREIGN KEY(budget_item_id) REFERENCES budget_items(id) ON DELETE CASCADE,
    UNIQUE(month_key, budget_item_id)
);

CREATE TABLE IF NOT EXISTS budget_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    label TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0,
    UNIQUE(user_id, key)
);

CREATE TABLE IF NOT EXISTS contribution_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    from_month TEXT NOT NULL,
    to_month TEXT NOT NULL,
    override_amount REAL NOT NULL,
    reason TEXT,
    created_at TEXT,
    FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cash_flow_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    event_date TEXT NOT NULL,
    amount REAL NOT NULL,
    kind TEXT NOT NULL DEFAULT 'transfer',
    counterparty_account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
    note TEXT,
    allowance_effect TEXT NOT NULL DEFAULT 'none',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS isa_contributions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    amount REAL NOT NULL,
    contribution_date TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pension_contributions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    amount REAL NOT NULL,
    kind TEXT NOT NULL DEFAULT 'personal',
    contribution_date TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dividend_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    amount REAL NOT NULL,
    dividend_date TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cgt_disposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    disposal_date TEXT NOT NULL,
    asset_name TEXT NOT NULL,
    proceeds REAL NOT NULL,
    cost_basis REAL NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pension_carry_forward (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tax_year TEXT NOT NULL,
    unused_allowance REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, tax_year)
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    name TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scheduler_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    run_date TEXT NOT NULL,
    slot TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS portfolio_daily_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    snapshot_date TEXT NOT NULL,
    total_value REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, snapshot_date)
);

CREATE TABLE IF NOT EXISTS account_daily_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    snapshot_date TEXT NOT NULL,
    value REAL NOT NULL,
    UNIQUE(account_id, snapshot_date)
);

CREATE TABLE IF NOT EXISTS custom_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    UNIQUE(user_id, tag)
);

CREATE TABLE IF NOT EXISTS api_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token TEXT NOT NULL UNIQUE,
    label TEXT,
    token_kind TEXT NOT NULL DEFAULT 'general',
    scopes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_used_at TEXT
);

CREATE TABLE IF NOT EXISTS assistant_audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_id INTEGER REFERENCES api_tokens(id) ON DELETE SET NULL,
    token_label TEXT,
    token_kind TEXT NOT NULL DEFAULT 'assistant',
    action_type TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    target_type TEXT,
    target_id INTEGER,
    target_label TEXT,
    month_key TEXT,
    before_state TEXT NOT NULL DEFAULT '{}',
    after_state TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS broker_connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    label TEXT NOT NULL,
    environment TEXT NOT NULL DEFAULT 'live',
    access_mode TEXT NOT NULL DEFAULT 'read_only',
    api_key_ciphertext TEXT NOT NULL,
    api_secret_ciphertext TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unverified',
    last_error TEXT,
    last_tested_at TEXT,
    external_account_id TEXT,
    external_account_currency TEXT,
    external_total_value REAL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS debts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    original_amount REAL DEFAULT 0,
    current_balance REAL NOT NULL DEFAULT 0,
    monthly_payment REAL NOT NULL DEFAULT 0,
    apr REAL DEFAULT 0,
    notes TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _run_migrations(conn):
    """All incremental schema changes applied after the base SCHEMA is created.

    Safe to call on any DB — every statement is either idempotent or guarded
    by a schema_migrations version check. Split out of init_db() to keep that
    function short and easy to read.
    """
    # ── Legacy column additions (accounts) ───────────────────────────────
    existing_cols = {row['name'] for row in conn.execute("PRAGMA table_info(accounts)").fetchall()}
    for col_name, col_def in [
        ("goal_value", "REAL"),
        ("valuation_mode", "TEXT DEFAULT 'manual'"),
        ("growth_mode", "TEXT DEFAULT 'default'"),
        ("growth_rate_override", "REAL"),
        ("tags", "TEXT DEFAULT ''"),
        ("pension_contribution_day", "INTEGER DEFAULT 0"),
    ]:
        if col_name not in existing_cols:
            try:
                conn.execute(f"ALTER TABLE accounts ADD COLUMN {col_name} {col_def}")
            except Exception as e:
                current_app.logger.error(f"Migration error (accounts.{col_name}): {e}")

    # ── Legacy column additions (other tables) ───────────────────────────
    for col_sql in [
        "ALTER TABLE assumptions ADD COLUMN dashboard_name TEXT DEFAULT 'SteadyPlan'",
        "ALTER TABLE assumptions ADD COLUMN retirement_goal_value REAL DEFAULT 1000000",
        "ALTER TABLE assumptions ADD COLUMN dividend_allowance REAL DEFAULT 500",
        "ALTER TABLE holdings ADD COLUMN holding_catalogue_id INTEGER",
        "ALTER TABLE holdings ADD COLUMN book_cost REAL",
        "ALTER TABLE goals ADD COLUMN selected_tags TEXT DEFAULT ''",
        "ALTER TABLE monthly_snapshots ADD COLUMN month_key TEXT",
    ]:
        try:
            conn.execute(col_sql)
        except Exception:
            pass

    cash_flow_cols = {row['name'] for row in conn.execute("PRAGMA table_info(cash_flow_events)").fetchall()}
    if "allowance_effect" not in cash_flow_cols:
        try:
            conn.execute("ALTER TABLE cash_flow_events ADD COLUMN allowance_effect TEXT NOT NULL DEFAULT 'none'")
        except Exception as e:
            _log_migration_error(e)

    # ── Legacy table creation ─────────────────────────────────────────────
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contribution_overrides (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                from_month TEXT NOT NULL,
                to_month TEXT NOT NULL,
                override_amount REAL NOT NULL,
                reason TEXT,
                created_at TEXT,
                FOREIGN KEY(account_id) REFERENCES accounts(id)
            )
        """)
    except Exception as e:
        _log_migration_error(e)

    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS broker_connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                provider TEXT NOT NULL,
                label TEXT NOT NULL,
                environment TEXT NOT NULL DEFAULT 'live',
                access_mode TEXT NOT NULL DEFAULT 'read_only',
                api_key_ciphertext TEXT NOT NULL,
                api_secret_ciphertext TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'unverified',
                last_error TEXT,
                last_tested_at TEXT,
                external_account_id TEXT,
                external_account_currency TEXT,
                external_total_value REAL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
    except Exception as e:
        _log_migration_error(e)

    # ── broker_connections: drop env-level uniqueness to allow multiple live accounts ──
    if not conn.execute(
        "SELECT 1 FROM schema_migrations WHERE name = 'v11_broker_connections_multi_account'"
    ).fetchone():
        conn.execute("""
            CREATE TABLE IF NOT EXISTS broker_connections_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                provider TEXT NOT NULL,
                label TEXT NOT NULL,
                environment TEXT NOT NULL DEFAULT 'live',
                access_mode TEXT NOT NULL DEFAULT 'read_only',
                api_key_ciphertext TEXT NOT NULL,
                api_secret_ciphertext TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'unverified',
                last_error TEXT,
                last_tested_at TEXT,
                external_account_id TEXT,
                external_account_currency TEXT,
                external_total_value REAL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            INSERT INTO broker_connections_new (
                id, user_id, provider, label, environment, access_mode,
                api_key_ciphertext, api_secret_ciphertext, status, last_error,
                last_tested_at, external_account_id, external_account_currency,
                external_total_value, is_active, created_at, updated_at
            )
            SELECT
                id, user_id, provider, label, environment, access_mode,
                api_key_ciphertext, api_secret_ciphertext, status, last_error,
                last_tested_at, external_account_id, external_account_currency,
                external_total_value, is_active, created_at, updated_at
            FROM broker_connections
        """)
        conn.execute("DROP TABLE IF EXISTS broker_connections")
        conn.execute("ALTER TABLE broker_connections_new RENAME TO broker_connections")
        conn.execute(
            "INSERT INTO schema_migrations (name) VALUES ('v11_broker_connections_multi_account')"
        )

    for col in ["last_price REAL", "price_currency TEXT", "price_change_pct REAL", "price_updated_at TEXT"]:
        try:
            conn.execute(f"ALTER TABLE holding_catalogue ADD COLUMN {col}")
        except Exception as e:
            _log_migration_error(e)

    # ── Multi-user migrations ─────────────────────────────────────────────
    # Add user_id to accounts (default 1 = first user, safe for existing DBs)
    for tbl, col_sql in [
        ("accounts",         "ALTER TABLE accounts ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id)"),
        ("goals",            "ALTER TABLE goals ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id)"),
        ("holding_catalogue","ALTER TABLE holding_catalogue ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id)"),
        ("budget_items",     "ALTER TABLE budget_items ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id)"),
        ("budget_sections",  "ALTER TABLE budget_sections ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id)"),
        ("monthly_reviews",  "ALTER TABLE monthly_reviews ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id)"),
    ]:
        try:
            conn.execute(col_sql)
        except Exception as e:
            _log_migration_error(e)

    # ── Assumptions table: recreate without CHECK (id=1), add user_id ─────
    if not conn.execute(
        "SELECT 1 FROM schema_migrations WHERE name = 'v4_assumptions_multi_user'"
    ).fetchone():
        # Check if old single-row assumptions exist
        old_row = conn.execute("SELECT * FROM assumptions LIMIT 1").fetchone()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS assumptions_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
                annual_growth_rate REAL DEFAULT 0.07,
                retirement_age INTEGER DEFAULT 60,
                current_age INTEGER DEFAULT 43,
                retirement_goal_value REAL DEFAULT 1000000,
                isa_allowance REAL DEFAULT 20000,
                lisa_allowance REAL DEFAULT 4000,
                dividend_allowance REAL DEFAULT 500,
                target_dev_pct REAL DEFAULT 0.90,
                target_em_pct REAL DEFAULT 0.10,
                emergency_fund_target REAL DEFAULT 3000,
                dashboard_name TEXT DEFAULT 'SteadyPlan',
                updated_at TEXT
            )
        """)
        if old_row:
            # Try to copy old data — old table might have id=1 row
            cols = old_row.keys()
            # Map old id=1 row to user_id=1
            conn.execute("""
                INSERT OR IGNORE INTO assumptions_new
                    (user_id, annual_growth_rate, retirement_age, current_age,
                     retirement_goal_value, isa_allowance, lisa_allowance,
                     dividend_allowance, target_dev_pct, target_em_pct,
                     emergency_fund_target, dashboard_name, updated_at)
                SELECT
                    1,
                    COALESCE(annual_growth_rate, 0.07),
                    COALESCE(retirement_age, 60),
                    COALESCE(current_age, 43),
                    COALESCE(retirement_goal_value, 1000000),
                    COALESCE(isa_allowance, 20000),
                    COALESCE(lisa_allowance, 4000),
                    COALESCE(dividend_allowance, 500),
                    COALESCE(target_dev_pct, 0.90),
                    COALESCE(target_em_pct, 0.10),
                    COALESCE(emergency_fund_target, 3000),
                    COALESCE(dashboard_name, 'SteadyPlan'),
                    updated_at
                FROM assumptions
                LIMIT 1
            """)
        conn.execute("DROP TABLE IF EXISTS assumptions")
        conn.execute("ALTER TABLE assumptions_new RENAME TO assumptions")
        conn.execute(
            "INSERT INTO schema_migrations (name) VALUES ('v4_assumptions_multi_user')"
        )

    # ── Rename default dashboard name (SteadyPlan) ─────────────────────────
    if not conn.execute(
        "SELECT 1 FROM schema_migrations WHERE name = 'v10_dashboard_name_steadyplan'"
    ).fetchone():
        conn.execute(
            "UPDATE assumptions SET dashboard_name = 'SteadyPlan' WHERE dashboard_name = 'Shelly'"
        )
        conn.execute(
            "INSERT INTO schema_migrations (name) VALUES ('v10_dashboard_name_steadyplan')"
        )

    # ── monthly_reviews: fix UNIQUE(month_key) → UNIQUE(user_id, month_key) ─
    if not conn.execute(
        "SELECT 1 FROM schema_migrations WHERE name = 'v5_monthly_reviews_per_user'"
    ).fetchone():
        conn.execute("""
            CREATE TABLE IF NOT EXISTS monthly_reviews_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                month_key TEXT NOT NULL,
                status TEXT DEFAULT 'not_started',
                notes TEXT,
                completed_at TEXT,
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(user_id, month_key)
            )
        """)
        conn.execute("""
            INSERT OR IGNORE INTO monthly_reviews_new
                (id, user_id, month_key, status, notes, completed_at, created_at, updated_at)
            SELECT id, user_id, month_key, status, notes, completed_at, created_at, updated_at
            FROM monthly_reviews
        """)
        conn.execute("DROP TABLE IF EXISTS monthly_reviews")
        conn.execute("ALTER TABLE monthly_reviews_new RENAME TO monthly_reviews")
        conn.execute(
            "INSERT INTO schema_migrations (name) VALUES ('v5_monthly_reviews_per_user')"
        )

    # ── budget_sections: fix UNIQUE(key) → UNIQUE(user_id, key) ──────────
    if not conn.execute(
        "SELECT 1 FROM schema_migrations WHERE name = 'v5_budget_sections_per_user'"
    ).fetchone():
        conn.execute("""
            CREATE TABLE IF NOT EXISTS budget_sections_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                key TEXT NOT NULL,
                label TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                UNIQUE(user_id, key)
            )
        """)
        conn.execute("""
            INSERT OR IGNORE INTO budget_sections_new (id, user_id, key, label, sort_order)
            SELECT id, user_id, key, label, sort_order FROM budget_sections
        """)
        conn.execute("DROP TABLE IF EXISTS budget_sections")
        conn.execute("ALTER TABLE budget_sections_new RENAME TO budget_sections")
        conn.execute(
            "INSERT INTO schema_migrations (name) VALUES ('v5_budget_sections_per_user')"
        )

    # ── v9: allowance_tracking user ownership ────────────────────────────
    if not conn.execute(
        "SELECT 1 FROM schema_migrations WHERE name = 'v9_allowance_tracking_user'"
    ).fetchone():
        try:
            conn.execute("ALTER TABLE allowance_tracking ADD COLUMN user_id INTEGER REFERENCES users(id)")
        except Exception as e:
            _log_migration_error(e)

        try:
            users = conn.execute("SELECT id FROM users ORDER BY id ASC").fetchall()
            if len(users) == 1:
                conn.execute(
                    "UPDATE allowance_tracking SET user_id = ? WHERE user_id IS NULL",
                    (users[0]["id"],),
                )
        except Exception as e:
            _log_migration_error(e)

        try:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_allowance_tracking_user_tax_year "
                "ON allowance_tracking(user_id, tax_year)"
            )
        except Exception as e:
            _log_migration_error(e)

        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (name) VALUES ('v9_allowance_tracking_user')"
        )
        conn.commit()

    # ── Add salary_day and update_day to assumptions ────────────────────
    for col in [
        "salary_day INTEGER DEFAULT 0",
        "update_day INTEGER DEFAULT 0",
    ]:
        try:
            conn.execute(f"ALTER TABLE assumptions ADD COLUMN {col}")
        except Exception as e:
            _log_migration_error(e)

    # ── Migrate current_age → date_of_birth ─────────────────────────────
    # Add date_of_birth column (TEXT, ISO format YYYY-MM-DD)
    try:
        conn.execute("ALTER TABLE assumptions ADD COLUMN date_of_birth TEXT")
    except Exception as e:
        _log_migration_error(e)

    # One-time: convert existing current_age to approximate DOB
    if not conn.execute(
        "SELECT 1 FROM schema_migrations WHERE name = 'v6_dob_from_age'"
    ).fetchone():
        # For each user who has current_age but no DOB, estimate DOB as
        # today minus current_age years (assumes birthday is Jan 1 — user
        # can correct this in Settings).
        from datetime import date as _date
        rows = conn.execute(
            "SELECT user_id, current_age FROM assumptions WHERE date_of_birth IS NULL AND current_age IS NOT NULL"
        ).fetchall()
        for row in rows:
            approx_year = _date.today().year - int(row["current_age"])
            approx_dob = f"{approx_year}-01-01"
            conn.execute(
                "UPDATE assumptions SET date_of_birth = ? WHERE user_id = ?",
                (approx_dob, row["user_id"]),
            )
        conn.execute(
            "INSERT INTO schema_migrations (name) VALUES ('v6_dob_from_age')"
        )

    # ── Retirement date mode ───────────────────────────────────────────
    # Options: 'birthday', 'end_of_year', 'end_of_tax_year'
    try:
        conn.execute("ALTER TABLE assumptions ADD COLUMN retirement_date_mode TEXT DEFAULT 'birthday'")
    except Exception as e:
        _log_migration_error(e)

    # ── Tax band on assumptions ────────────────────────────────────────
    # Options: 'basic', 'higher', 'additional'
    try:
        conn.execute("ALTER TABLE assumptions ADD COLUMN tax_band TEXT DEFAULT 'basic'")
    except Exception as e:
        _log_migration_error(e)

    # ── Pension / contribution / fee fields on accounts ────────────────
    for col in [
        "employer_contribution REAL DEFAULT 0",
        "contribution_method TEXT DEFAULT 'standard'",
        "annual_fee_pct REAL DEFAULT 0",
        "platform_fee_pct REAL DEFAULT 0",
        "platform_fee_flat REAL DEFAULT 0",
        "platform_fee_cap REAL DEFAULT 0",
        "fund_fee_pct REAL DEFAULT 0",
        "contribution_fee_pct REAL DEFAULT 0",
        "uninvested_cash REAL DEFAULT 0",
        "cash_interest_rate REAL DEFAULT 0",
        "interest_payment_day INTEGER DEFAULT 0",
        "include_in_budget INTEGER DEFAULT 1",
        "pre_salary INTEGER DEFAULT 0",
    ]:
        try:
            conn.execute(f"ALTER TABLE accounts ADD COLUMN {col}")
        except Exception as e:
            _log_migration_error(e)

    # ── Migrate legacy annual_fee_pct → fund_fee_pct (one-time) ──────
    try:
        if not conn.execute(
            "SELECT 1 FROM schema_migrations WHERE name = 'v4_split_fees'"
        ).fetchone():
            conn.execute("""
                UPDATE accounts SET fund_fee_pct = annual_fee_pct
                WHERE annual_fee_pct > 0 AND fund_fee_pct = 0
            """)
            conn.execute(
                "INSERT INTO schema_migrations (name) VALUES ('v4_split_fees')"
            )
            conn.commit()
    except Exception as e:
        _log_migration_error(e)

    # ── One-time catalogue wipe ───────────────────────────────────────────
    if not conn.execute(
        "SELECT 1 FROM schema_migrations WHERE name = 'v3_clean_catalogue'"
    ).fetchone():
        conn.execute("DELETE FROM holding_catalogue")
        conn.execute(
            "INSERT INTO schema_migrations (name) VALUES ('v3_clean_catalogue')"
        )

    # ── Unique ticker index per user ──────────────────────────────────────
    # Drop old global unique index if it exists, then create per-user one
    try:
        conn.execute("DROP INDEX IF EXISTS idx_catalogue_ticker")
    except Exception as e:
        _log_migration_error(e)
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_catalogue_ticker_user "
            "ON holding_catalogue(user_id, ticker) WHERE ticker IS NOT NULL AND ticker != ''"
        )
    except Exception as e:
        _log_migration_error(e)

    # ── Auto-update prices toggle on assumptions ─────────────────────────
    try:
        conn.execute("ALTER TABLE assumptions ADD COLUMN auto_update_prices INTEGER DEFAULT 1")
    except Exception as e:
        _log_migration_error(e)

    # ── Scheduler run tracking ────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduler_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            run_date TEXT NOT NULL,
            slot TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(user_id, run_date, slot)
        )
    """)

    # ── Configurable price update times ──────────────────────────────────
    for col in [
        "update_time_morning TEXT DEFAULT '08:30'",
        "update_time_evening TEXT DEFAULT '18:00'",
    ]:
        try:
            conn.execute(f"ALTER TABLE assumptions ADD COLUMN {col}")
        except Exception as e:
            _log_migration_error(e)

    for col in [
        "annual_income REAL DEFAULT 0",
        "pension_annual_allowance REAL DEFAULT 60000",
        "mpaa_enabled INTEGER DEFAULT 0",
        "mpaa_allowance REAL DEFAULT 10000",
    ]:
        try:
            conn.execute(f"ALTER TABLE assumptions ADD COLUMN {col}")
        except Exception as e:
            _log_migration_error(e)
    try:
        conn.execute("ALTER TABLE assumptions ADD COLUMN benchmark_rate REAL DEFAULT NULL")
    except Exception as e:
        _log_migration_error(e)

    # ── Custom tags per user ─────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS custom_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            tag TEXT NOT NULL,
            UNIQUE(user_id, tag)
        )
    """)

    # ── Hidden default tags per user ─────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hidden_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            tag TEXT NOT NULL,
            UNIQUE(user_id, tag)
        )
    """)

    # ── Premium Bonds prize log ───────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS premium_bonds_prizes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            month_key TEXT NOT NULL,
            prize_amount REAL NOT NULL DEFAULT 0,
            logged_at TEXT,
            UNIQUE(account_id, month_key)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS pension_contributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            amount REAL NOT NULL,
            kind TEXT NOT NULL DEFAULT 'personal',
            contribution_date TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            token TEXT NOT NULL UNIQUE,
            label TEXT,
            token_kind TEXT NOT NULL DEFAULT 'general',
            scopes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            last_used_at TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS assistant_audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_id INTEGER REFERENCES api_tokens(id) ON DELETE SET NULL,
            token_label TEXT,
            token_kind TEXT NOT NULL DEFAULT 'assistant',
            action_type TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            target_type TEXT,
            target_id INTEGER,
            target_label TEXT,
            month_key TEXT,
            before_state TEXT NOT NULL DEFAULT '{}',
            after_state TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    for col_sql in [
        "ALTER TABLE api_tokens ADD COLUMN token_kind TEXT NOT NULL DEFAULT 'general'",
        "ALTER TABLE api_tokens ADD COLUMN scopes TEXT NOT NULL DEFAULT ''",
    ]:
        try:
            conn.execute(col_sql)
        except Exception as e:
            _log_migration_error(e)

    # ── cgt_disposals: add optional account_id ───────────────────────────
    try:
        conn.execute("ALTER TABLE cgt_disposals ADD COLUMN account_id INTEGER REFERENCES accounts(id)")
    except Exception as e:
        _log_migration_error(e)

    # ── Debts tracker ────────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS debts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            name TEXT NOT NULL,
            original_amount REAL DEFAULT 0,
            current_balance REAL NOT NULL DEFAULT 0,
            monthly_payment REAL NOT NULL DEFAULT 0,
            apr REAL DEFAULT 0,
            notes TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # ── Debts: add start_date column ─────────────────────────────────────
    try:
        conn.execute("ALTER TABLE debts ADD COLUMN start_date TEXT")
    except Exception as e:
        _log_migration_error(e)

    # ── budget_items: add linked_debt_id ─────────────────────────────────
    try:
        conn.execute("ALTER TABLE budget_items ADD COLUMN linked_debt_id INTEGER REFERENCES debts(id) ON DELETE SET NULL")
    except Exception as e:
        _log_migration_error(e)

    # ── account_daily_snapshots: per-account daily values ─────────────────
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS account_daily_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                account_id INTEGER NOT NULL REFERENCES accounts(id),
                snapshot_date TEXT NOT NULL,
                value REAL NOT NULL,
                UNIQUE(account_id, snapshot_date)
            )
        """)
    except Exception as e:
        _log_migration_error(e)


    # ── ON DELETE CASCADE migrations ──────────────────────────────────────
    if not conn.execute(
        "SELECT 1 FROM schema_migrations WHERE name = 'v7_cascading_deletes'"
    ).fetchone():
        # Disable foreign keys temporarily to allow dropping/recreating tables
        # that are part of a relationship.
        conn.execute("PRAGMA foreign_keys=OFF")
        
        try:
            # List of tables to recreate with ON DELETE CASCADE
            tables_to_cascade = [
                ("accounts", """
                    CREATE TABLE accounts_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        provider TEXT,
                        wrapper_type TEXT,
                        category TEXT,
                        tags TEXT DEFAULT '',
                        current_value REAL DEFAULT 0,
                        monthly_contribution REAL DEFAULT 0,
                        pension_contribution_day INTEGER DEFAULT 0,
                        goal_value REAL,
                        valuation_mode TEXT DEFAULT 'manual',
                        growth_mode TEXT DEFAULT 'default',
                        growth_rate_override REAL,
                        owner TEXT,
                        is_active INTEGER DEFAULT 1,
                        notes TEXT,
                        last_updated TEXT,
                        employer_contribution REAL DEFAULT 0,
                        contribution_method TEXT DEFAULT 'standard',
                        annual_fee_pct REAL DEFAULT 0,
                        platform_fee_pct REAL DEFAULT 0,
                        platform_fee_flat REAL DEFAULT 0,
                        platform_fee_cap REAL DEFAULT 0,
                        fund_fee_pct REAL DEFAULT 0,
                        contribution_fee_pct REAL DEFAULT 0,
                        uninvested_cash REAL DEFAULT 0,
                        cash_interest_rate REAL DEFAULT 0,
                        interest_payment_day INTEGER DEFAULT 0
                    )
                """),
                ("holding_catalogue", """
                    CREATE TABLE holding_catalogue_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        holding_name TEXT NOT NULL,
                        ticker TEXT,
                        asset_type TEXT,
                        bucket TEXT,
                        notes TEXT,
                        is_active INTEGER DEFAULT 1,
                        last_price REAL,
                        price_currency TEXT,
                        price_change_pct REAL,
                        price_updated_at TEXT
                    )
                """),
                ("holdings", """
                    CREATE TABLE holdings_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        account_id INTEGER NOT NULL,
                        holding_catalogue_id INTEGER,
                        holding_name TEXT NOT NULL,
                        ticker TEXT,
                        asset_type TEXT,
                        bucket TEXT,
                        value REAL DEFAULT 0,
                        units REAL,
                        price REAL,
                        book_cost REAL,
                        notes TEXT,
                        FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE,
                        FOREIGN KEY(holding_catalogue_id) REFERENCES holding_catalogue(id) ON DELETE CASCADE
                    )
                """),
            ]

            for table_name, create_sql in tables_to_cascade:
                # Clean up from any previous failed attempt
                conn.execute(f"DROP TABLE IF EXISTS {table_name}_new")
                
                # 1. Create new table
                conn.execute(create_sql)
                
                # 2. Copy data (only columns that exist in both)
                old_cols = [r['name'] for r in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]
                new_cols = [r['name'] for r in conn.execute(f"PRAGMA table_info({table_name}_new)").fetchall()]
                common_cols = [c for c in old_cols if c in new_cols]
                cols_str = ", ".join(common_cols)
                conn.execute(f"INSERT INTO {table_name}_new ({cols_str}) SELECT {cols_str} FROM {table_name}")
                
                # 3. Swap tables
                conn.execute(f"DROP TABLE {table_name}")
                conn.execute(f"ALTER TABLE {table_name}_new RENAME TO {table_name}")

            # Mark as finished — use OR IGNORE to handle multi-worker races
            conn.execute("INSERT OR IGNORE INTO schema_migrations (name) VALUES ('v7_cascading_deletes')")
            conn.commit()
            
        except Exception as e:
            current_app.logger.error(f"Migration error (v7_cascading_deletes): {e}")
            conn.rollback()
        finally:
            # Always re-enable foreign keys
            conn.execute("PRAGMA foreign_keys=ON")

    # ── Re-add columns lost by v7_cascading_deletes ─────────────────────
    # v7's accounts_new CREATE TABLE omits these two columns, so any DB
    # (including production) that ran v7 had them dropped. Add them back
    # idempotently — a no-op once the column exists.
    for col in [
        "include_in_budget INTEGER DEFAULT 1",
        "pre_salary INTEGER DEFAULT 0",
    ]:
        try:
            conn.execute(f"ALTER TABLE accounts ADD COLUMN {col}")
        except Exception as e:
            _log_migration_error(e)

    # ── v8: purge legacy soft-deleted accounts ──────────────────────────
    # Delete now means really-delete (see app/models/accounts.py). Old
    # soft-deleted accounts (is_active = 0) were still leaking their
    # snapshot rows into net-worth and performance charts because those
    # queries don't filter on is_active. Hard-delete them once so the
    # charts stop showing deleted accounts. Runs only on the first startup
    # after this migration is added; subsequent deletes go through the
    # accounts.delete_account hard-delete path.
    if not conn.execute(
        "SELECT 1 FROM schema_migrations WHERE name = 'v8_purge_soft_deleted_accounts'"
    ).fetchone():
        try:
            stale_ids = [
                row["id"] for row in conn.execute(
                    "SELECT id FROM accounts WHERE is_active = 0"
                ).fetchall()
            ]
            child_tables = (
                "holdings", "monthly_snapshots", "monthly_review_items",
                "contribution_overrides", "isa_contributions",
                "pension_contributions", "dividend_records",
                "premium_bonds_prizes", "account_daily_snapshots",
            )
            for aid in stale_ids:
                for tbl in child_tables:
                    try:
                        conn.execute(f"DELETE FROM {tbl} WHERE account_id = ?", (aid,))
                    except Exception:
                        pass  # table may not exist on older DBs
                try:
                    conn.execute(
                        "UPDATE cgt_disposals SET account_id = NULL WHERE account_id = ?",
                        (aid,),
                    )
                except Exception:
                    pass
                try:
                    conn.execute(
                        "UPDATE budget_items SET linked_account_id = NULL WHERE linked_account_id = ?",
                        (aid,),
                    )
                except Exception:
                    pass
                conn.execute("DELETE FROM accounts WHERE id = ?", (aid,))
            if stale_ids:
                current_app.logger.warning(
                    "Purged %d previously soft-deleted account(s): %s",
                    len(stale_ids), stale_ids,
                )
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations (name) VALUES ('v8_purge_soft_deleted_accounts')"
            )
            conn.commit()
        except Exception as e:
            _log_migration_error(e)


def _ensure_indexes(conn):
    """Create performance indexes. All statements are idempotent (IF NOT EXISTS)."""
    for stmt in [
        "CREATE INDEX IF NOT EXISTS idx_accounts_user_id ON accounts(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_accounts_active ON accounts(user_id, is_active)",
        "CREATE INDEX IF NOT EXISTS idx_goals_user_id ON goals(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_holding_catalogue_user_id ON holding_catalogue(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_holdings_account_id ON holdings(account_id)",
        "CREATE INDEX IF NOT EXISTS idx_holdings_catalogue_id ON holdings(holding_catalogue_id)",
        "CREATE INDEX IF NOT EXISTS idx_monthly_snapshots_account_id ON monthly_snapshots(account_id)",
        "CREATE INDEX IF NOT EXISTS idx_monthly_snapshots_date ON monthly_snapshots(snapshot_date)",
        "CREATE INDEX IF NOT EXISTS idx_monthly_snapshots_month_key ON monthly_snapshots(month_key)",
        "CREATE INDEX IF NOT EXISTS idx_monthly_reviews_user_month ON monthly_reviews(user_id, month_key)",
        "CREATE INDEX IF NOT EXISTS idx_monthly_review_items_review_id ON monthly_review_items(review_id)",
        "CREATE INDEX IF NOT EXISTS idx_monthly_review_items_account_id ON monthly_review_items(account_id)",
        "CREATE INDEX IF NOT EXISTS idx_budget_items_user_id ON budget_items(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_budget_items_linked_account ON budget_items(linked_account_id)",
        "CREATE INDEX IF NOT EXISTS idx_budget_entries_month ON budget_entries(month_key)",
        "CREATE INDEX IF NOT EXISTS idx_budget_entries_item ON budget_entries(budget_item_id)",
        "CREATE INDEX IF NOT EXISTS idx_budget_sections_user_id ON budget_sections(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_contribution_overrides_account ON contribution_overrides(account_id)",
        "CREATE INDEX IF NOT EXISTS idx_cash_flow_events_account_date ON cash_flow_events(account_id, event_date)",
        "CREATE INDEX IF NOT EXISTS idx_cash_flow_events_user_date ON cash_flow_events(user_id, event_date)",
        "CREATE INDEX IF NOT EXISTS idx_isa_contributions_user ON isa_contributions(user_id, contribution_date)",
        "CREATE INDEX IF NOT EXISTS idx_isa_contributions_account ON isa_contributions(account_id)",
        "CREATE INDEX IF NOT EXISTS idx_pension_contributions_user ON pension_contributions(user_id, contribution_date)",
        "CREATE INDEX IF NOT EXISTS idx_pension_contributions_account ON pension_contributions(account_id)",
        "CREATE INDEX IF NOT EXISTS idx_dividend_records_user ON dividend_records(user_id, dividend_date)",
        "CREATE INDEX IF NOT EXISTS idx_dividend_records_account ON dividend_records(account_id)",
        "CREATE INDEX IF NOT EXISTS idx_scheduler_runs_user_date ON scheduler_runs(user_id, run_date)",
        "CREATE INDEX IF NOT EXISTS idx_portfolio_daily_user_date ON portfolio_daily_snapshots(user_id, snapshot_date)",
        "CREATE INDEX IF NOT EXISTS idx_custom_tags_user ON custom_tags(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_api_tokens_token ON api_tokens(token)",
        "CREATE INDEX IF NOT EXISTS idx_api_tokens_user ON api_tokens(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_assistant_audit_user_created ON assistant_audit_events(user_id, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_assistant_audit_token ON assistant_audit_events(token_id)",
        "CREATE INDEX IF NOT EXISTS idx_cgt_disposals_user ON cgt_disposals(user_id, disposal_date)",
        "CREATE INDEX IF NOT EXISTS idx_cgt_disposals_account ON cgt_disposals(account_id)",
        "CREATE INDEX IF NOT EXISTS idx_account_daily_account_date ON account_daily_snapshots(account_id, snapshot_date)",
    ]:
        try:
            conn.execute(stmt)
        except Exception as e:
            current_app.logger.warning(f"Index create failed ({stmt.split()[-1]}): {e}")


def init_db():
    """Initialise or migrate the database.

    Three phases:
    1. Apply base SCHEMA (all CREATE TABLE IF NOT EXISTS — idempotent).
    2. Run incremental migrations (column additions, table rewrites, data fixes).
    3. Ensure performance indexes exist.
    """
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        _run_migrations(conn)
        _ensure_indexes(conn)
        conn.commit()
