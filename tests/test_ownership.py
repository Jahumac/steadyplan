"""IDOR regression tests — proves that user A cannot mutate user B's data.

If any of these fail, the site has an authorization-bypass hole.
"""
import pytest


@pytest.fixture
def two_users(app, make_user, client):
    """Create Alice and Bob, then seed one goal/account/holding/budget_item
    for each. Returns a dict with each user's ids."""
    alice_uid, _, _ = make_user(username="alice", password="password123")
    bob_uid, _, _ = make_user(username="bob", password="password123")

    with app.app_context():
        from app.models import get_connection
        with get_connection() as conn:
            # Goal
            alice_goal = conn.execute(
                "INSERT INTO goals (user_id, name, target_value) VALUES (?, 'Alice goal', 10000)",
                (alice_uid,),
            ).lastrowid
            bob_goal = conn.execute(
                "INSERT INTO goals (user_id, name, target_value) VALUES (?, 'Bob goal', 10000)",
                (bob_uid,),
            ).lastrowid
            # Account
            alice_account = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active) VALUES (?, 'Alice ISA', 5000, 1)",
                (alice_uid,),
            ).lastrowid
            bob_account = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active) VALUES (?, 'Bob ISA', 5000, 1)",
                (bob_uid,),
            ).lastrowid
            # Holding
            alice_holding = conn.execute(
                """INSERT INTO holdings (account_id, holding_name, ticker, value, units, price)
                   VALUES (?, 'VUSA', 'VUSA', 5000, 100, 50)""",
                (alice_account,),
            ).lastrowid
            bob_holding = conn.execute(
                """INSERT INTO holdings (account_id, holding_name, ticker, value, units, price)
                   VALUES (?, 'VUSA', 'VUSA', 5000, 100, 50)""",
                (bob_account,),
            ).lastrowid
            # Catalogue holding
            alice_catalogue = conn.execute(
                """
                INSERT INTO holding_catalogue (user_id, holding_name, ticker, asset_type, bucket, is_active)
                VALUES (?, 'Alice instrument', 'ALICE', 'ETF', 'Global Equity', 1)
                """,
                (alice_uid,),
            ).lastrowid
            bob_catalogue = conn.execute(
                """
                INSERT INTO holding_catalogue (user_id, holding_name, ticker, asset_type, bucket, is_active)
                VALUES (?, 'Bob instrument', 'BOB', 'ETF', 'Global Equity', 1)
                """,
                (bob_uid,),
            ).lastrowid
            # Budget item
            alice_budget = conn.execute(
                "INSERT INTO budget_items (user_id, name, section, default_amount, is_active) VALUES (?, 'Rent', 'fixed', 1000, 1)",
                (alice_uid,),
            ).lastrowid
            bob_budget = conn.execute(
                "INSERT INTO budget_items (user_id, name, section, default_amount, is_active) VALUES (?, 'Rent', 'fixed', 1000, 1)",
                (bob_uid,),
            ).lastrowid
            conn.commit()

    return {
        "alice": {"uid": alice_uid, "goal": alice_goal, "account": alice_account,
                  "holding": alice_holding, "catalogue": alice_catalogue, "budget": alice_budget},
        "bob": {"uid": bob_uid, "goal": bob_goal, "account": bob_account,
                "holding": bob_holding, "catalogue": bob_catalogue, "budget": bob_budget},
    }


def _login_as(client, username, password="password123"):
    client.post("/login", data={"username": username, "password": password})


# ── Model-level checks (unit tests, catch the core mistake earliest) ─────────

def test_update_goal_scoped_to_user(app, two_users):
    from app.models import fetch_goal, update_goal
    with app.app_context():
        ok = update_goal(
            {"id": two_users["bob"]["goal"], "name": "HACKED",
             "target_value": 99, "goal_type": "", "selected_tags": "", "notes": ""},
            two_users["alice"]["uid"],  # Alice trying to mutate Bob's goal
        )
        assert ok is False
        bob_goal = fetch_goal(two_users["bob"]["goal"])
        assert bob_goal["name"] == "Bob goal"  # untouched


def test_delete_goal_scoped_to_user(app, two_users):
    from app.models import delete_goal, fetch_goal
    with app.app_context():
        ok = delete_goal(two_users["bob"]["goal"], two_users["alice"]["uid"])
        assert ok is False
        assert fetch_goal(two_users["bob"]["goal"]) is not None


def test_update_holding_scoped_to_account_owner(app, two_users):
    from app.models import fetch_holding, update_holding
    with app.app_context():
        ok = update_holding({
            "id": two_users["bob"]["holding"],
            "account_id": two_users["bob"]["account"],
            "holding_catalogue_id": None,
            "holding_name": "HACKED", "ticker": "X",
            "asset_type": "", "bucket": "",
            "value": 0, "units": 0, "price": 0, "notes": "",
        }, two_users["alice"]["uid"])
        assert ok is False
        bob_h = fetch_holding(two_users["bob"]["holding"])
        assert bob_h["holding_name"] == "VUSA"


def test_update_holding_cannot_move_to_another_users_account(app, two_users):
    from app.models import fetch_holding, update_holding
    with app.app_context():
        ok = update_holding({
            "id": two_users["alice"]["holding"],
            "account_id": two_users["bob"]["account"],
            "holding_catalogue_id": None,
            "holding_name": "Moved", "ticker": "X",
            "asset_type": "", "bucket": "",
            "value": 0, "units": 0, "price": 0, "notes": "",
        }, two_users["alice"]["uid"])
        assert ok is False
        alice_h = fetch_holding(two_users["alice"]["holding"])
        assert alice_h["account_id"] == two_users["alice"]["account"]
        assert alice_h["holding_name"] == "VUSA"


def test_delete_holding_scoped_to_account_owner(app, two_users):
    from app.models import delete_holding, fetch_holding
    with app.app_context():
        ok = delete_holding(two_users["bob"]["holding"], two_users["alice"]["uid"])
        assert ok is False
        assert fetch_holding(two_users["bob"]["holding"]) is not None


def test_update_budget_item_scoped_to_user(app, two_users):
    from app.models import get_connection, update_budget_item
    with app.app_context():
        ok = update_budget_item({
            "id": two_users["bob"]["budget"],
            "name": "HACKED", "section": "fixed",
            "default_amount": 0, "linked_account_id": None, "notes": "",
        }, two_users["alice"]["uid"])
        assert ok is False
        with get_connection() as conn:
            name = conn.execute("SELECT name FROM budget_items WHERE id = ?",
                                (two_users["bob"]["budget"],)).fetchone()["name"]
        assert name == "Rent"


def test_budget_item_cannot_link_to_another_users_account(app, two_users):
    from app.models import create_budget_item, get_connection, update_budget_item
    with app.app_context():
        new_id = create_budget_item({
            "name": "Savings",
            "section": "investment",
            "default_amount": 100,
            "linked_account_id": two_users["bob"]["account"],
            "notes": "",
        }, two_users["alice"]["uid"])
        update_budget_item({
            "id": two_users["alice"]["budget"],
            "name": "Rent",
            "section": "fixed",
            "default_amount": 1000,
            "linked_account_id": two_users["bob"]["account"],
            "notes": "",
        }, two_users["alice"]["uid"])

        with get_connection() as conn:
            created = conn.execute(
                "SELECT linked_account_id FROM budget_items WHERE id = ?",
                (new_id,),
            ).fetchone()
            updated = conn.execute(
                "SELECT linked_account_id FROM budget_items WHERE id = ?",
                (two_users["alice"]["budget"],),
            ).fetchone()
        assert created["linked_account_id"] is None
        assert updated["linked_account_id"] is None


def test_delete_budget_item_scoped_to_user(app, two_users):
    from app.models import delete_budget_item, get_connection
    with app.app_context():
        ok = delete_budget_item(two_users["bob"]["budget"], two_users["alice"]["uid"])
        assert ok is False
        with get_connection() as conn:
            is_active = conn.execute(
                "SELECT is_active FROM budget_items WHERE id = ?",
                (two_users["bob"]["budget"],)).fetchone()["is_active"]
        assert is_active == 1


def test_fetch_goal_scoped_to_user(app, two_users):
    from app.models import fetch_goal
    with app.app_context():
        # Alice asking for Bob's goal with her user_id should get nothing
        result = fetch_goal(two_users["bob"]["goal"], two_users["alice"]["uid"])
        assert result is None
        # Without user scoping the old behaviour still works (used by internal code)
        result = fetch_goal(two_users["bob"]["goal"])
        assert result is not None


def test_fetch_holding_scoped_to_account_owner(app, two_users):
    from app.models import fetch_holding
    with app.app_context():
        result = fetch_holding(two_users["bob"]["holding"], two_users["alice"]["uid"])
        assert result is None


# ── Route-level checks (proves the wiring is correct end-to-end) ─────────────

def test_alice_cannot_delete_bobs_goal_via_route(app, client, two_users):
    _login_as(client, "alice")
    resp = client.post("/goals/", data={
        "form_name": "delete_goal",
        "goal_id": two_users["bob"]["goal"],
    })
    assert resp.status_code in (200, 302)
    with app.app_context():
        from app.models import fetch_goal
        assert fetch_goal(two_users["bob"]["goal"]) is not None  # still there


def test_alice_cannot_delete_bobs_holding_via_route(app, client, two_users):
    _login_as(client, "alice")
    resp = client.post(
        f"/accounts/{two_users['bob']['account']}/holdings/{two_users['bob']['holding']}/delete"
    )
    assert resp.status_code in (200, 302)
    with app.app_context():
        from app.models import fetch_holding
        assert fetch_holding(two_users["bob"]["holding"]) is not None


def test_alice_cannot_add_holding_to_bobs_account_via_holdings_route(app, client, two_users):
    _login_as(client, "alice")
    with app.app_context():
        from app.models import get_connection
        with get_connection() as conn:
            before = conn.execute(
                "SELECT COUNT(*) AS c FROM holdings WHERE account_id = ?",
                (two_users["bob"]["account"],),
            ).fetchone()["c"]

    resp = client.post(
        f"/holdings/{two_users['alice']['catalogue']}/add-to-account",
        data={"account_id": two_users["bob"]["account"], "units": "1", "price": "1.0"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302)

    with app.app_context():
        from app.models import get_connection
        with get_connection() as conn:
            after = conn.execute(
                "SELECT COUNT(*) AS c FROM holdings WHERE account_id = ?",
                (two_users["bob"]["account"],),
            ).fetchone()["c"]
    assert after == before


def test_alice_cannot_update_bobs_catalogue_item_via_route(app, client, two_users):
    _login_as(client, "alice")
    resp = client.post(
        "/holdings/",
        data={
            "form_name": "catalogue",
            "catalogue_id": two_users["bob"]["catalogue"],
            "catalogue_holding_name": "HACKED",
            "catalogue_ticker": "BOB",
            "catalogue_asset_type": "ETF",
            "catalogue_bucket": "Global Equity",
            "catalogue_notes": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302)

    with app.app_context():
        from app.models import get_connection
        with get_connection() as conn:
            row = conn.execute(
                "SELECT holding_name FROM holding_catalogue WHERE id = ?",
                (two_users["bob"]["catalogue"],),
            ).fetchone()
    assert row["holding_name"] == "Bob instrument"


def test_alice_cannot_delete_bobs_budget_item_via_route(app, client, two_users):
    _login_as(client, "alice")
    resp = client.post(
        f"/budget/items/{two_users['bob']['budget']}",
        data={"form_name": "delete"},
    )
    assert resp.status_code in (200, 302)
    with app.app_context():
        from app.models import get_connection
        with get_connection() as conn:
            row = conn.execute(
                "SELECT is_active FROM budget_items WHERE id = ?",
                (two_users["bob"]["budget"],),
            ).fetchone()
        assert row["is_active"] == 1  # still active


def test_alice_cannot_add_allowance_rows_for_bobs_account(app, client, two_users):
    _login_as(client, "alice")

    client.post("/allowance/add", data={
        "account_id": two_users["bob"]["account"],
        "amount": "100",
        "contribution_date": "2026-04-10",
    })
    client.post("/allowance/pension/add", data={
        "account_id": two_users["bob"]["account"],
        "amount": "100",
        "kind": "personal",
        "contribution_date": "2026-04-10",
    })
    client.post("/allowance/dividend/add", data={
        "account_id": two_users["bob"]["account"],
        "amount": "100",
        "dividend_date": "2026-04-10",
    })
    client.post("/allowance/cgt/add", data={
        "account_id": two_users["bob"]["account"],
        "asset_name": "Fund",
        "proceeds": "150",
        "cost_basis": "100",
        "disposal_date": "2026-04-10",
    })

    with app.app_context():
        from app.models import get_connection
        with get_connection() as conn:
            isa = conn.execute("SELECT COUNT(*) AS c FROM isa_contributions").fetchone()["c"]
            pensions = conn.execute("SELECT COUNT(*) AS c FROM pension_contributions").fetchone()["c"]
            dividends = conn.execute("SELECT COUNT(*) AS c FROM dividend_records").fetchone()["c"]
            cgt = conn.execute("SELECT COUNT(*) AS c FROM cgt_disposals").fetchone()["c"]
    assert (isa, pensions, dividends, cgt) == (0, 0, 0, 0)


def test_allowance_fetches_do_not_join_cross_user_accounts(app, two_users):
    from app.models import (
        fetch_cgt_disposals,
        fetch_dividend_records,
        fetch_isa_contributions,
        fetch_pension_contributions,
        get_connection,
    )
    with app.app_context():
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO isa_contributions (user_id, account_id, amount, contribution_date) VALUES (?, ?, 100, '2026-04-10')",
                (two_users["alice"]["uid"], two_users["bob"]["account"]),
            )
            conn.execute(
                "INSERT INTO pension_contributions (user_id, account_id, amount, kind, contribution_date) VALUES (?, ?, 100, 'personal', '2026-04-10')",
                (two_users["alice"]["uid"], two_users["bob"]["account"]),
            )
            conn.execute(
                "INSERT INTO dividend_records (user_id, account_id, amount, dividend_date) VALUES (?, ?, 100, '2026-04-10')",
                (two_users["alice"]["uid"], two_users["bob"]["account"]),
            )
            conn.execute(
                "INSERT INTO cgt_disposals (user_id, account_id, asset_name, proceeds, cost_basis, disposal_date) VALUES (?, ?, 'Fund', 150, 100, '2026-04-10')",
                (two_users["alice"]["uid"], two_users["bob"]["account"]),
            )
            conn.commit()

        assert fetch_isa_contributions(two_users["alice"]["uid"], "2026-04-06", "2027-04-05") == []
        assert fetch_pension_contributions(two_users["alice"]["uid"], "2026-04-06", "2027-04-05") == []
        assert fetch_dividend_records(two_users["alice"]["uid"], "2026-04-06", "2027-04-05") == []
        cgt_rows = fetch_cgt_disposals(two_users["alice"]["uid"], "2026-04-06", "2027-04-05")
        assert len(cgt_rows) == 1
        assert cgt_rows[0]["account_name"] is None


def test_user_reset_deletes_only_own_allowance_tracking(app, two_users):
    from app.models import get_connection, reset_all_user_data
    with app.app_context():
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO allowance_tracking (user_id, tax_year, isa_used, lisa_used, notes)
                VALUES (?, '2026/27', 123, 45, 'alice')
                """,
                (two_users["alice"]["uid"],),
            )
            conn.execute(
                """
                INSERT INTO allowance_tracking (user_id, tax_year, isa_used, lisa_used, notes)
                VALUES (?, '2026/27', 999, 88, 'bob')
                """,
                (two_users["bob"]["uid"],),
            )
            conn.commit()

        reset_all_user_data(two_users["alice"]["uid"])

        with get_connection() as conn:
            rows = conn.execute(
                "SELECT user_id, isa_used FROM allowance_tracking ORDER BY user_id ASC"
            ).fetchall()
        assert rows == [{"user_id": two_users["bob"]["uid"], "isa_used": 999}]


# ── Budget → contribution_overrides back-sync ────────────────────────────────

def test_linked_budget_edit_creates_contribution_override(app, two_users):
    """Saving a budget entry for a linked item writes a single-month override."""
    from app.models import get_connection, upsert_budget_entry
    from app.routes.budget import _sync_linked_override

    with app.app_context():
        # Link Alice's budget item to her account
        with get_connection() as conn:
            conn.execute(
                "UPDATE budget_items SET linked_account_id = ? WHERE id = ?",
                (two_users["alice"]["account"], two_users["alice"]["budget"]),
            )
            conn.commit()

        upsert_budget_entry("2026-07", two_users["alice"]["budget"], 555, two_users["alice"]["uid"])
        _sync_linked_override(two_users["alice"]["budget"], "2026-07", 555, two_users["alice"]["uid"])

        with get_connection() as conn:
            rows = conn.execute(
                "SELECT from_month, to_month, override_amount, reason FROM contribution_overrides WHERE account_id = ?",
                (two_users["alice"]["account"],),
            ).fetchall()
        assert len(rows) == 1
        assert rows[0]["from_month"] == "2026-07"
        assert rows[0]["to_month"] == "2026-07"
        assert rows[0]["override_amount"] == 555
        assert rows[0]["reason"] == "from budget"


def test_linked_budget_edit_updates_existing_review_expected_contribution(app, two_users):
    from app.models import fetch_monthly_review_items, fetch_or_create_monthly_review, get_connection
    from app.routes.budget import _sync_linked_override

    with app.app_context():
        with get_connection() as conn:
            conn.execute(
                "UPDATE budget_items SET linked_account_id = ? WHERE id = ?",
                (two_users["alice"]["account"], two_users["alice"]["budget"]),
            )
            conn.commit()

        review = fetch_or_create_monthly_review("2026-07", two_users["alice"]["uid"])
        from app.models import ensure_monthly_review_items
        ensure_monthly_review_items(review["id"], two_users["alice"]["uid"])

        _sync_linked_override(two_users["alice"]["budget"], "2026-07", 555, two_users["alice"]["uid"])

        items = fetch_monthly_review_items(review["id"])
        item = next(i for i in items if i["account_id"] == two_users["alice"]["account"])
        assert item["expected_contribution"] == 555


def test_review_items_created_after_override_use_override_amount(app, two_users):
    from app.models import (
        ensure_monthly_review_items,
        fetch_monthly_review_items,
        fetch_or_create_monthly_review,
        upsert_single_month_contribution_override,
    )

    with app.app_context():
        upsert_single_month_contribution_override(
            two_users["alice"]["account"],
            "2026-07",
            0,
            two_users["alice"]["uid"],
            reason="Skipped",
        )
        review = fetch_or_create_monthly_review("2026-07", two_users["alice"]["uid"])
        ensure_monthly_review_items(review["id"], two_users["alice"]["uid"])

        items = fetch_monthly_review_items(review["id"])
        item = next(i for i in items if i["account_id"] == two_users["alice"]["account"])
        assert item["expected_contribution"] == 0


def test_account_override_updates_existing_review_expected_contribution(app, two_users):
    from app.models import (
        create_contribution_override,
        ensure_monthly_review_items,
        fetch_monthly_review_items,
        fetch_or_create_monthly_review,
    )

    with app.app_context():
        review = fetch_or_create_monthly_review("2026-07", two_users["alice"]["uid"])
        ensure_monthly_review_items(review["id"], two_users["alice"]["uid"])

        create_contribution_override(
            {
                "account_id": two_users["alice"]["account"],
                "from_month": "2026-07",
                "to_month": "2026-07",
                "override_amount": 250,
                "reason": "Holiday",
            },
            two_users["alice"]["uid"],
        )

        items = fetch_monthly_review_items(review["id"])
        item = next(i for i in items if i["account_id"] == two_users["alice"]["account"])
        assert item["expected_contribution"] == 250


def test_account_override_shows_in_linked_budget_month(app, two_users):
    from app.models import create_contribution_override, get_connection
    from app.routes.budget import _build_monthly_data

    with app.app_context():
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO budget_sections (user_id, key, label, sort_order) VALUES (?, 'fixed', 'Fixed', 1)",
                (two_users["alice"]["uid"],),
            )
            conn.execute(
                "UPDATE accounts SET monthly_contribution = 400 WHERE id = ?",
                (two_users["alice"]["account"],),
            )
            conn.execute(
                "UPDATE budget_items SET linked_account_id = ? WHERE id = ?",
                (two_users["alice"]["account"], two_users["alice"]["budget"]),
            )
            conn.commit()

        create_contribution_override(
            {
                "account_id": two_users["alice"]["account"],
                "from_month": "2026-07",
                "to_month": "2026-07",
                "override_amount": 250,
                "reason": "Holiday",
            },
            two_users["alice"]["uid"],
        )

        sections, _ = _build_monthly_data("2026-07", two_users["alice"]["uid"])
        row = next(row for section in sections for row in section["rows"])
        assert row["amount"] == 250
        assert row["source"] == "manual_override"


def test_linked_budget_second_edit_replaces_not_duplicates(app, two_users):
    """A follow-up edit on the same month replaces the override, not duplicates it."""
    from app.models import get_connection
    from app.routes.budget import _sync_linked_override

    with app.app_context():
        with get_connection() as conn:
            conn.execute(
                "UPDATE budget_items SET linked_account_id = ? WHERE id = ?",
                (two_users["alice"]["account"], two_users["alice"]["budget"]),
            )
            conn.commit()

        _sync_linked_override(two_users["alice"]["budget"], "2026-07", 400, two_users["alice"]["uid"])
        _sync_linked_override(two_users["alice"]["budget"], "2026-07", 500, two_users["alice"]["uid"])

        with get_connection() as conn:
            rows = conn.execute(
                "SELECT override_amount FROM contribution_overrides WHERE account_id = ?",
                (two_users["alice"]["account"],),
            ).fetchall()
        assert len(rows) == 1
        assert rows[0]["override_amount"] == 500


def test_alice_cannot_sync_override_into_bobs_account(app, two_users):
    """Passing Bob's budget item_id into Alice's sync call must not touch Bob's account."""
    from app.models import get_connection
    from app.routes.budget import _sync_linked_override

    with app.app_context():
        # Bob's budget item is linked to Bob's account
        with get_connection() as conn:
            conn.execute(
                "UPDATE budget_items SET linked_account_id = ? WHERE id = ?",
                (two_users["bob"]["account"], two_users["bob"]["budget"]),
            )
            conn.commit()

        _sync_linked_override(two_users["bob"]["budget"], "2026-07", 9999, two_users["alice"]["uid"])

        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM contribution_overrides WHERE account_id = ?",
                (two_users["bob"]["account"],),
            ).fetchall()
        assert rows == []


def test_unlinked_budget_edit_does_not_create_override(app, two_users):
    """Items without linked_account_id don't touch contribution_overrides."""
    from app.models import get_connection
    from app.routes.budget import _sync_linked_override

    # Alice's budget item is NOT linked (default from fixture)
    with app.app_context():
        _sync_linked_override(two_users["alice"]["budget"], "2026-07", 555, two_users["alice"]["uid"])

        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM contribution_overrides").fetchall()
        assert rows == []


def test_skip_after_budget_edit_replaces_not_duplicates(app, two_users):
    """Skipping a contribution for a month that already has a budget-written
    override must replace it, not add a second row. Both paths now share
    upsert_single_month_contribution_override."""
    from app.models import get_connection, upsert_single_month_contribution_override
    from app.routes.budget import _sync_linked_override

    with app.app_context():
        with get_connection() as conn:
            conn.execute(
                "UPDATE budget_items SET linked_account_id = ? WHERE id = ?",
                (two_users["alice"]["account"], two_users["alice"]["budget"]),
            )
            conn.commit()

        _sync_linked_override(two_users["alice"]["budget"], "2026-07", 400, two_users["alice"]["uid"])
        upsert_single_month_contribution_override(
            two_users["alice"]["account"], "2026-07", 0.0,
            two_users["alice"]["uid"], reason="Skipped",
        )

        with get_connection() as conn:
            rows = conn.execute(
                "SELECT override_amount, reason FROM contribution_overrides WHERE account_id = ?",
                (two_users["alice"]["account"],),
            ).fetchall()
        assert len(rows) == 1
        assert rows[0]["override_amount"] == 0
        assert rows[0]["reason"] == "Skipped"


def test_linked_budget_items_do_not_inherit_prior_month_one_offs(app, two_users):
    from app.models import get_connection, upsert_budget_entry
    from app.routes.budget import _build_monthly_data

    with app.app_context():
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO budget_sections (user_id, key, label, sort_order) VALUES (?, 'fixed', 'Fixed', 1)",
                (two_users["alice"]["uid"],),
            )
            conn.execute(
                "UPDATE accounts SET monthly_contribution = 1000 WHERE id = ?",
                (two_users["alice"]["account"],),
            )
            conn.execute(
                "UPDATE budget_items SET linked_account_id = ? WHERE id = ?",
                (two_users["alice"]["account"], two_users["alice"]["budget"]),
            )
            conn.commit()

        upsert_budget_entry("2026-05", two_users["alice"]["budget"], 1200, two_users["alice"]["uid"])

        sections, _ = _build_monthly_data("2026-06", two_users["alice"]["uid"])
        row = next(row for section in sections for row in section["rows"])
        assert row["amount"] == 1000
        assert row["source"] == "linked_account"


def test_accounts_with_monthly_contributions_auto_appear_in_budget(app, two_users):
    from app.models import fetch_budget_items, get_connection
    from app.routes.budget import _build_monthly_data

    with app.app_context():
        with get_connection() as conn:
            conn.execute(
                "UPDATE accounts SET name = 'Premium Bonds', monthly_contribution = 10 WHERE id = ?",
                (two_users["alice"]["account"],),
            )
            conn.commit()

        items = fetch_budget_items(two_users["alice"]["uid"])
        item = next(i for i in items if i["linked_account_id"] == two_users["alice"]["account"])
        assert item["name"] == "Premium Bonds"
        assert item["section"] == "investment"

        sections, _ = _build_monthly_data("2026-04", two_users["alice"]["uid"])
        row = next(row for section in sections for row in section["rows"] if row["name"] == "Premium Bonds")
        assert row["amount"] == 10
        assert row["source"] == "linked_account"
