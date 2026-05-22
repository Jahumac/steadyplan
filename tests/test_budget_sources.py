import pytest


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

