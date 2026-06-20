import pytest

from tests.path_helpers import STATIC_ROOT


def _seed_default_budget_sections(app, user_id):
    from app.models import fetch_budget_items
    with app.app_context():
        fetch_budget_items(user_id)


def _row_for(sections, name):
    return next(r for s in sections for r in s["rows"] if r["name"] == name)


def test_default_source_no_current_or_prior(app, make_user):
    uid, _, _ = make_user(username="src-default", password="password123")
    _seed_default_budget_sections(app, uid)

    from app.models import get_connection
    from app.routes.budget import _build_monthly_data

    with app.app_context():
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO budget_items (user_id, name, section, default_amount, notes, sort_order, is_active)
                VALUES (?, 'Test rent', 'fixed', 123.0, '', 0, 1)
                """,
                (uid,),
            )
            conn.commit()

        sections, _ = _build_monthly_data("2026-06", uid)
        row = _row_for(sections, "Test rent")
        assert row["amount"] == 123.0
        assert row["source"] == "default"


def test_inherited_source_from_prior_month(app, make_user):
    uid, _, _ = make_user(username="src-inherited", password="password123")
    _seed_default_budget_sections(app, uid)

    from app.models import get_connection, upsert_budget_entry
    from app.routes.budget import _build_monthly_data

    with app.app_context():
        with get_connection() as conn:
            item_id = conn.execute(
                """
                INSERT INTO budget_items (user_id, name, section, default_amount, notes, sort_order, is_active)
                VALUES (?, 'Test groceries', 'fixed', 100.0, '', 0, 1)
                """,
                (uid,),
            ).lastrowid
            conn.commit()

        upsert_budget_entry("2026-05", item_id, 250.0, uid)
        sections, _ = _build_monthly_data("2026-06", uid)
        row = _row_for(sections, "Test groceries")
        assert row["amount"] == 250.0
        assert row["source"] == "inherited"


def test_manual_override_source_current_month_entry(app, make_user):
    uid, _, _ = make_user(username="src-manual", password="password123")
    _seed_default_budget_sections(app, uid)

    from app.models import get_connection, upsert_budget_entry
    from app.routes.budget import _build_monthly_data

    with app.app_context():
        with get_connection() as conn:
            item_id = conn.execute(
                """
                INSERT INTO budget_items (user_id, name, section, default_amount, notes, sort_order, is_active)
                VALUES (?, 'Test utilities', 'fixed', 80.0, '', 0, 1)
                """,
                (uid,),
            ).lastrowid
            conn.commit()

        upsert_budget_entry("2026-06", item_id, 90.0, uid)
        sections, _ = _build_monthly_data("2026-06", uid)
        row = _row_for(sections, "Test utilities")
        assert row["amount"] == 90.0
        assert row["source"] == "manual_override"


def test_linked_account_does_not_inherit_stale_prior_amount(app, make_user):
    uid, _, _ = make_user(username="src-linked-account", password="password123")
    _seed_default_budget_sections(app, uid)

    from app.models import fetch_budget_items, get_connection, upsert_budget_entry
    from app.routes.budget import _build_monthly_data

    with app.app_context():
        with get_connection() as conn:
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, current_value, monthly_contribution, is_active)
                VALUES (?, 'Vanguard ISA', 0, 1000, 1)
                """,
                (uid,),
            ).lastrowid
            conn.commit()

        items = fetch_budget_items(uid)
        linked_item = next(i for i in items if i.get("linked_account_id") == account_id)
        upsert_budget_entry("2026-05", linked_item["id"], 1200.0, uid)

        sections, _ = _build_monthly_data("2026-06", uid)
        row = _row_for(sections, linked_item["name"])
        assert row["amount"] == 1000.0
        assert row["source"] == "linked_account"


def test_linked_account_contribution_override_applies(app, make_user):
    uid, _, _ = make_user(username="src-linked-override", password="password123")
    _seed_default_budget_sections(app, uid)

    from app.models import fetch_budget_items, get_connection, upsert_single_month_contribution_override
    from app.routes.budget import _build_monthly_data

    with app.app_context():
        with get_connection() as conn:
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, current_value, monthly_contribution, is_active)
                VALUES (?, 'Vanguard ISA', 0, 1000, 1)
                """,
                (uid,),
            ).lastrowid
            conn.commit()

        items = fetch_budget_items(uid)
        linked_item = next(i for i in items if i.get("linked_account_id") == account_id)

        upsert_single_month_contribution_override(account_id, "2026-06", 800.0, uid, reason="Test")
        sections, _ = _build_monthly_data("2026-06", uid)
        row = _row_for(sections, linked_item["name"])
        assert row["amount"] == 800.0
        assert row["source"] == "manual_override"


def test_linked_debt_does_not_inherit_stale_prior_amount(app, make_user):
    uid, _, _ = make_user(username="src-linked-debt", password="password123")
    _seed_default_budget_sections(app, uid)

    from app.models import fetch_budget_items, get_connection, upsert_budget_entry
    from app.routes.budget import _build_monthly_data

    with app.app_context():
        with get_connection() as conn:
            debt_id = conn.execute(
                """
                INSERT INTO debts (user_id, name, current_balance, monthly_payment, is_active)
                VALUES (?, 'Car loan', 10000, 300, 1)
                """,
                (uid,),
            ).lastrowid
            conn.commit()

        items = fetch_budget_items(uid)
        debt_item = next(i for i in items if i.get("linked_debt_id") == debt_id)
        upsert_budget_entry("2026-05", debt_item["id"], 500.0, uid)

        sections, _ = _build_monthly_data("2026-06", uid)
        row = _row_for(sections, debt_item["name"])
        assert row["amount"] == 300.0
        assert row["source"] == "linked_debt"


def test_stamp_inherited_entries_skips_linked_rows(app, make_user):
    uid, _, _ = make_user(username="src-stamp", password="password123")
    _seed_default_budget_sections(app, uid)

    from app.models import fetch_budget_items, fetch_budget_entries, get_connection, upsert_budget_entry
    from app.routes.budget import _stamp_inherited_entries

    with app.app_context():
        with get_connection() as conn:
            unlinked_id = conn.execute(
                """
                INSERT INTO budget_items (user_id, name, section, default_amount, notes, sort_order, is_active)
                VALUES (?, 'Unlinked item', 'fixed', 10.0, '', 0, 1)
                """,
                (uid,),
            ).lastrowid
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, current_value, monthly_contribution, is_active)
                VALUES (?, 'ISA', 0, 1000, 1)
                """,
                (uid,),
            ).lastrowid
            debt_id = conn.execute(
                """
                INSERT INTO debts (user_id, name, current_balance, monthly_payment, is_active)
                VALUES (?, 'Loan', 10000, 300, 1)
                """,
                (uid,),
            ).lastrowid
            conn.commit()

        items = fetch_budget_items(uid)
        linked_account_item = next(i for i in items if i.get("linked_account_id") == account_id)
        linked_debt_item = next(i for i in items if i.get("linked_debt_id") == debt_id)

        upsert_budget_entry("2026-05", unlinked_id, 11.0, uid)
        upsert_budget_entry("2026-05", linked_account_item["id"], 1200.0, uid)
        upsert_budget_entry("2026-05", linked_debt_item["id"], 500.0, uid)

        assert fetch_budget_entries("2026-06", uid) == []
        _stamp_inherited_entries("2026-06", uid)
        rows = fetch_budget_entries("2026-06", uid)
        assert {r["budget_item_id"] for r in rows} == {unlinked_id}


def test_pre_salary_surplus_adds_back_outside_take_home(app, make_user):
    uid, _, _ = make_user(username="src-pre-salary", password="password123")
    _seed_default_budget_sections(app, uid)

    from app.models import fetch_budget_items, get_connection
    from app.routes.budget import _build_monthly_data

    with app.app_context():
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, current_value, monthly_contribution, pre_salary, is_active)
                VALUES (?, 'Salary sacrifice', 0, 500, 1, 1)
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO budget_items (user_id, name, section, default_amount, notes, sort_order, is_active)
                VALUES (?, 'Salary', 'income', 3000.0, '', 0, 1)
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO budget_items (user_id, name, section, default_amount, notes, sort_order, is_active)
                VALUES (?, 'Bills', 'fixed', 1000.0, '', 0, 1)
                """,
                (uid,),
            )
            conn.commit()

        fetch_budget_items(uid)
        _, summary = _build_monthly_data("2026-06", uid)
        assert summary["total_income"] == 3000.0
        assert summary["total_expenses"] == 1500.0
        assert summary["pre_salary_total"] == 500.0
        assert summary["surplus"] == 2000.0



def test_budget_sections_show_share_of_income(app, client, make_user):
    uid, username, password = make_user(username="budget-section-income-share", password="password123")
    _seed_default_budget_sections(app, uid)

    from app.models import get_connection

    with app.app_context():
        with get_connection() as conn:
            conn.executemany(
                """
                INSERT INTO budget_items (user_id, name, section, default_amount, notes, sort_order, is_active)
                VALUES (?, ?, ?, ?, '', ?, 1)
                """,
                [
                    (uid, "Salary", "income", 4000.0, 0),
                    (uid, "Rent", "fixed", 1000.0, 0),
                    (uid, "Car loan", "debt", 500.0, 0),
                    (uid, "Stocks ISA", "investment", 800.0, 0),
                    (uid, "Food and fun", "discretionary", 400.0, 0),
                ],
            )
            conn.commit()

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    resp = client.get("/budget/?month=2026-06")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'class="budget-section-metrics"' in html
    assert 'class="budget-section-summary budget-section-summary-stack"' not in html
    assert "Monthly" in html
    assert "Income share" in html
    assert "Yearly" in html
    assert 'id="total-income"' in html
    assert 'id="share-income"' in html
    assert 'id="annual-income"' in html
    assert 'id="total-fixed"' in html
    assert 'id="share-fixed"' in html
    assert 'id="annual-fixed"' in html
    assert "100.0%" in html
    assert "25.0%" in html
    assert "12.5%" in html
    assert "20.0%" in html
    assert "10.0%" in html
    assert "£48,000" in html
    assert "£12,000" in html
    assert "£6,000" in html
    assert "£9,600" in html
    assert "£4,800" in html
    assert 'class="budget-row-annual"' in html
    assert "£12,000 / year" in html
    assert "£6,000 / year" in html
    assert "£9,600 / year" in html


def test_budget_page_renders_non_persistent_what_if_sandbox(app, client, make_user):
    uid, username, password = make_user(username="budget-what-if", password="password123")
    _seed_default_budget_sections(app, uid)

    from app.models import get_connection

    with app.app_context():
        with get_connection() as conn:
            conn.executemany(
                """
                INSERT INTO budget_items (user_id, name, section, default_amount, notes, sort_order, is_active)
                VALUES (?, ?, ?, ?, '', ?, 1)
                """,
                [
                    (uid, "Salary", "income", 4000.0, 0),
                    (uid, "Rent", "fixed", 1000.0, 0),
                    (uid, "Stocks ISA", "investment", 800.0, 0),
                ],
            )
            conn.commit()

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    resp = client.get("/budget/?month=2026-06")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "budget-what-if-card" in html
    assert "Budget what-if" in html
    assert "Simulation only" in html
    assert "Try changes without saving them to the real budget." in html
    assert 'id="budget-what-if-toggle"' in html
    assert 'id="budget-what-if-reset"' in html
    assert 'id="what-if-surplus-delta"' in html
    assert "Nothing is written to the database unless you leave simulation mode and edit normally." in html
    assert 'data-real-value="4000.00"' in html
    assert 'data-real-value="1000.00"' in html
    assert 'data-real-value="800.00"' in html


def test_budget_what_if_javascript_blocks_auto_save_and_restores_real_values():
    js = STATIC_ROOT.joinpath("js/app.js").read_text()

    assert "budget-what-if-toggle" in js
    assert "budget-what-if-reset" in js
    assert "budget-what-if-active" in js
    assert "function resetWhatIfValues" in js
    assert "if (whatIfMode)" in js
    assert "updateWhatIfSummary();" in js
    assert "saveEntry(input.dataset.itemId, input.value, ind);" in js


def test_budget_mobile_layout_keeps_summary_and_rows_compact():
    css = STATIC_ROOT.joinpath("css/styles.css").read_text()

    assert "@media (max-width: 640px)" in css
    assert ".budget-section-metrics {\n    grid-template-columns: repeat(3, minmax(0, 1fr));" in css
    assert ".budget-section-metric {\n    min-height: 3.15rem;" in css
    assert "padding: 0.5rem 0.35rem;" in css
    assert ".budget-section-panel .budget-row {\n    display: grid;" in css
    assert "grid-template-columns: minmax(0, 1fr) auto;" in css
    assert ".budget-section-panel .budget-row-left {\n    grid-column: 1 / -1;" in css
    assert ".budget-section-panel .budget-row-annual {\n    grid-column: 1;" in css
    assert ".budget-section-panel .budget-row-right {\n    grid-column: 2;" in css
    assert ".budget-section-panel .budget-row .budget-amount-input {\n    width: 6.2rem;" in css
