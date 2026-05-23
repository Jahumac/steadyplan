import json
import sqlite3

import pytest

from app.services.restore_service import RestoreValidationError, restore_backup_for_user


def _login(client, username, password):
    resp = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )
    assert resp.status_code == 200


def _export_payload(client):
    resp = client.get("/settings/export.json")
    assert resp.status_code == 200
    return json.loads(resp.data.decode("utf-8"))


def _seed_exportable_data(app, user_id, *, account_names=("A1", "A2")):
    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            a1 = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution)
                VALUES (?, ?, 'isa', 1000, 100)
                """,
                (user_id, account_names[0]),
            ).lastrowid
            a2 = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution)
                VALUES (?, ?, 'cash', 2000, 200)
                """,
                (user_id, account_names[1]),
            ).lastrowid

            goal_id = conn.execute(
                "INSERT INTO goals (user_id, name, target_value, goal_type) VALUES (?, 'G1', 12345, 'retirement')",
                (user_id,),
            ).lastrowid

            debt_id = conn.execute(
                """
                INSERT INTO debts (user_id, name, original_amount, current_balance, monthly_payment, apr, notes)
                VALUES (?, 'D1', 5000, 4000, 123, 4.5, 'debt')
                """,
                (user_id,),
            ).lastrowid

            cat_id = conn.execute(
                """
                INSERT INTO holding_catalogue (user_id, holding_name, ticker, asset_type, bucket, is_active)
                VALUES (?, 'Global ETF', 'VWRA', 'fund', 'dev', 1)
                """,
                (user_id,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO holdings (account_id, holding_catalogue_id, holding_name, ticker, asset_type, bucket, value, units, price)
                VALUES (?, ?, 'Global ETF', 'VWRA', 'fund', 'dev', 500, 5, 100)
                """,
                (a1, cat_id),
            )

            conn.execute(
                """
                INSERT INTO cash_flow_events (user_id, account_id, event_date, amount, kind, note, counterparty_account_id)
                VALUES (?, ?, '2026-06-15', 50, 'transfer', 'test', ?)
                """,
                (user_id, a1, a2),
            )
            conn.execute(
                """
                INSERT INTO allowance_tracking (user_id, tax_year, isa_used, lisa_used, notes)
                VALUES (?, '2026-27', 123, 45, 'mine')
                """,
                (user_id,),
            )

            conn.execute(
                """
                INSERT INTO budget_sections (user_id, key, label, sort_order)
                VALUES (?, 'income', 'Income', 0)
                """,
                (user_id,),
            )
            budget_item_id = conn.execute(
                """
                INSERT INTO budget_items (user_id, name, section, default_amount, linked_account_id, linked_debt_id, notes)
                VALUES (?, 'Salary', 'income', 1000, ?, ?, 'note')
                """,
                (user_id, a1, debt_id),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO budget_entries (month_key, budget_item_id, amount)
                VALUES ('2026-05', ?, 999)
                """,
                (budget_item_id,),
            )

            review_id = conn.execute(
                """
                INSERT INTO monthly_reviews (user_id, month_key, status, notes, created_at, updated_at)
                VALUES (?, '2026-05', 'done', 'ok', '2026-05-20T00:00:00+00:00', '2026-05-20T00:00:00+00:00')
                """,
                (user_id,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO monthly_review_items (review_id, account_id, expected_contribution, contribution_confirmed)
                VALUES (?, ?, 100, 1)
                """,
                (review_id, a1),
            )

            conn.execute(
                """
                INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, contribution, note)
                VALUES ('2026-05-31', ?, 111, 22, 'snap')
                """,
                (a1,),
            )
            conn.execute(
                """
                INSERT INTO portfolio_daily_snapshots (user_id, snapshot_date, total_value)
                VALUES (?, '2026-05-31', 3000)
                """,
                (user_id,),
            )
            conn.execute(
                """
                INSERT INTO account_daily_snapshots (user_id, account_id, snapshot_date, value)
                VALUES (?, ?, '2026-05-31', 111)
                """,
                (user_id, a1),
            )

            conn.execute(
                """
                INSERT INTO contribution_overrides (account_id, from_month, to_month, override_amount, reason)
                VALUES (?, '2026-06', '2026-12', 123, 'test')
                """,
                (a1,),
            )
            conn.execute(
                """
                INSERT INTO isa_contributions (user_id, account_id, amount, contribution_date, note)
                VALUES (?, ?, 10, '2026-06-01', 'isa')
                """,
                (user_id, a1),
            )
            conn.execute(
                """
                INSERT INTO pension_contributions (user_id, account_id, amount, kind, contribution_date, note)
                VALUES (?, ?, 20, 'personal', '2026-06-01', 'pension')
                """,
                (user_id, a1),
            )
            conn.execute(
                """
                INSERT INTO dividend_records (user_id, account_id, amount, dividend_date, note)
                VALUES (?, ?, 3, '2026-06-01', 'div')
                """,
                (user_id, a1),
            )
            conn.execute(
                """
                INSERT INTO cgt_disposals (user_id, disposal_date, asset_name, proceeds, cost_basis, note, account_id)
                VALUES (?, '2026-06-01', 'ABC', 100, 50, 'cgt', ?)
                """,
                (user_id, a1),
            )
            conn.execute(
                """
                INSERT INTO pension_carry_forward (user_id, tax_year, unused_allowance)
                VALUES (?, '2025-26', 5000)
                """,
                (user_id,),
            )
            conn.execute(
                """
                INSERT INTO premium_bonds_prizes (user_id, account_id, month_key, prize_amount, logged_at)
                VALUES (?, ?, '2026-05', 25, '2026-05-01T00:00:00+00:00')
                """,
                (user_id, a2),
            )

            conn.commit()

    return {"goal_id": goal_id, "debt_id": debt_id, "account_ids": (a1, a2)}


def _count_user_rows(app, user_id):
    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            return {
                "accounts": int(conn.execute("SELECT COUNT(*) AS c FROM accounts WHERE user_id = ?", (user_id,)).fetchone()["c"]),
                "holdings": int(
                    conn.execute(
                        "SELECT COUNT(*) AS c FROM holdings WHERE account_id IN (SELECT id FROM accounts WHERE user_id = ?)",
                        (user_id,),
                    ).fetchone()["c"]
                ),
                "allowance_tracking": int(
                    conn.execute("SELECT COUNT(*) AS c FROM allowance_tracking WHERE user_id = ?", (user_id,)).fetchone()["c"]
                ),
                "cash_flow_events": int(
                    conn.execute("SELECT COUNT(*) AS c FROM cash_flow_events WHERE user_id = ?", (user_id,)).fetchone()["c"]
                ),
            }


def _wipe_user_data(app, user_id):
    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                "DELETE FROM budget_entries WHERE budget_item_id IN (SELECT id FROM budget_items WHERE user_id = ?)",
                (user_id,),
            )
            conn.execute("DELETE FROM budget_items WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM budget_sections WHERE user_id = ?", (user_id,))
            conn.execute(
                "DELETE FROM monthly_review_items WHERE review_id IN (SELECT id FROM monthly_reviews WHERE user_id = ?)",
                (user_id,),
            )
            conn.execute("DELETE FROM monthly_reviews WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM portfolio_daily_snapshots WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM account_daily_snapshots WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM cash_flow_events WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM isa_contributions WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM pension_contributions WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM dividend_records WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM cgt_disposals WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM pension_carry_forward WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM allowance_tracking WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM premium_bonds_prizes WHERE user_id = ?", (user_id,))
            conn.execute(
                "DELETE FROM contribution_overrides WHERE account_id IN (SELECT id FROM accounts WHERE user_id = ?)",
                (user_id,),
            )
            conn.execute(
                "DELETE FROM monthly_snapshots WHERE account_id IN (SELECT id FROM accounts WHERE user_id = ?)",
                (user_id,),
            )
            conn.execute(
                "DELETE FROM holdings WHERE account_id IN (SELECT id FROM accounts WHERE user_id = ?)",
                (user_id,),
            )
            conn.execute("DELETE FROM accounts WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM goals WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM debts WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM assumptions WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM holding_catalogue WHERE user_id = ?", (user_id,))
            conn.commit()



def test_restore_service_valid_backup_restores_current_user_only(app, client, make_user):
    uid1, u1, p1 = make_user(username="restore-u1", password="password123", is_admin=True)
    uid2, u2, p2 = make_user(username="restore-u2", password="password123", is_admin=True)

    _seed_exportable_data(app, uid1)
    _seed_exportable_data(app, uid2, account_names=("B1", "B2"))

    _login(client, u1, p1)
    payload = _export_payload(client)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution)
                VALUES (?, 'EXTRA', 'cash', 1, 1)
                """,
                (uid1,),
            )
            conn.execute(
                "INSERT INTO allowance_tracking (user_id, tax_year, isa_used) VALUES (?, '2099-00', 1)",
                (uid1,),
            )
            conn.commit()

    before_u2 = _count_user_rows(app, uid2)
    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            result = restore_backup_for_user(uid1, payload, conn=conn)
    after_u2 = _count_user_rows(app, uid2)

    assert result["ok"] is True
    assert result["meta"]["export_schema_version"] == 1
    assert after_u2 == before_u2

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            names = {r["name"] for r in conn.execute("SELECT name FROM accounts WHERE user_id = ?", (uid1,)).fetchall()}
            assert "EXTRA" not in names
            assert "A1" in names and "A2" in names

            allowance = conn.execute(
                "SELECT tax_year, user_id FROM allowance_tracking WHERE tax_year = '2026-27'"
            ).fetchone()
            assert allowance is not None
            assert int(allowance["user_id"]) == uid1

            a1_id = conn.execute(
                "SELECT id FROM accounts WHERE user_id = ? AND name = 'A1'",
                (uid1,),
            ).fetchone()["id"]
            a2_id = conn.execute(
                "SELECT id FROM accounts WHERE user_id = ? AND name = 'A2'",
                (uid1,),
            ).fetchone()["id"]
            cfe = conn.execute(
                "SELECT account_id, counterparty_account_id FROM cash_flow_events WHERE user_id = ?",
                (uid1,),
            ).fetchone()
            assert cfe is not None
            assert int(cfe["account_id"]) == int(a1_id)
            assert int(cfe["counterparty_account_id"]) == int(a2_id)


def test_restore_service_imported_user_id_is_ignored(app, client, make_user):
    uid1, u1, p1 = make_user(username="restore-u1-uid", password="password123", is_admin=True)
    uid2, u2, p2 = make_user(username="restore-u2-uid", password="password123", is_admin=True)

    _seed_exportable_data(app, uid1)
    _login(client, u1, p1)
    payload = _export_payload(client)

    for a in payload.get("accounts", []):
        a["user_id"] = uid2
    for at in payload.get("planning", {}).get("allowance_tracking", []):
        at["user_id"] = None
    for c in payload.get("holding_catalogue", []):
        c["user_id"] = uid2
    for pds in payload.get("history", {}).get("portfolio_daily_snapshots", []):
        pds["user_id"] = uid2

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            restore_backup_for_user(uid1, payload, conn=conn)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            assert conn.execute(
                "SELECT 1 FROM accounts WHERE user_id = ? AND name = 'A1'",
                (uid1,),
            ).fetchone()
            assert conn.execute(
                "SELECT 1 FROM accounts WHERE user_id = ? AND name = 'A2'",
                (uid1,),
            ).fetchone()
            assert conn.execute(
                "SELECT 1 FROM holding_catalogue WHERE user_id = ?",
                (uid1,),
            ).fetchone()
            assert conn.execute(
                "SELECT 1 FROM allowance_tracking WHERE user_id = ? AND tax_year = '2026-27'",
                (uid1,),
            ).fetchone()
            assert conn.execute(
                "SELECT 1 FROM portfolio_daily_snapshots WHERE user_id = ? AND snapshot_date = '2026-05-31'",
                (uid1,),
            ).fetchone()


def test_restore_service_invalid_or_unsupported_schema_writes_nothing(app, client, make_user):
    uid, username, password = make_user(username="restore-unsupported", password="password123")
    _seed_exportable_data(app, uid)
    _login(client, username, password)
    payload = _export_payload(client)

    before = _count_user_rows(app, uid)
    payload["meta"]["export_schema_version"] = 999
    with pytest.raises(RestoreValidationError):
        with app.app_context():
            from app.models import get_connection

            with get_connection() as conn:
                restore_backup_for_user(uid, payload, conn=conn)
    after = _count_user_rows(app, uid)
    assert after == before


def test_restore_service_failure_midway_rolls_back_completely(app, client, make_user):
    uid, username, password = make_user(username="restore-rollback", password="password123")
    _seed_exportable_data(app, uid, account_names=("A1", "A2"))
    _login(client, username, password)
    payload = _export_payload(client)

    pb = payload.get("planning", {}).get("premium_bonds_prizes", [])
    assert pb
    pb.append(dict(pb[0]))

    _wipe_user_data(app, uid)
    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution)
                VALUES (?, 'OLD1', 'cash', 1, 1)
                """,
                (uid,),
            )
            conn.execute(
                "INSERT INTO allowance_tracking (user_id, tax_year, isa_used) VALUES (?, '2099-00', 1)",
                (uid,),
            )
            conn.commit()

    before = _count_user_rows(app, uid)
    with pytest.raises(sqlite3.IntegrityError):
        with app.app_context():
            from app.models import get_connection

            with get_connection() as conn:
                restore_backup_for_user(uid, payload, conn=conn)
    after = _count_user_rows(app, uid)
    assert after == before

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            names = {r["name"] for r in conn.execute("SELECT name FROM accounts WHERE user_id = ?", (uid,)).fetchall()}
            assert "OLD1" in names
            assert "A1" not in names
