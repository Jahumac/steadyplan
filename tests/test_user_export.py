import json
import re


def _login(client, username, password):
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)


def test_settings_export_json_download(app, client, make_user):
    uid, username, password = make_user(username="export", password="password123")
    other_uid, _, _ = make_user(username="export2", password="password123")

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            acct_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, provider, wrapper_type, current_value, monthly_contribution, is_active)
                VALUES (?, 'Vanguard ISA', 'Vanguard', 'Stocks & Shares ISA', 1234.56, 250, 1)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO holdings (account_id, holding_name, ticker, value, units, price, notes)
                VALUES (?, 'VUSA', 'VUSA', 1234.56, 10, 123.456, 'test')
                """,
                (acct_id,),
            )
            conn.execute(
                """
                INSERT INTO goals (user_id, name, target_value, goal_type, selected_tags, notes)
                VALUES (?, 'Retirement', 1000000, 'Tagged Goal', '', '')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO debts (user_id, name, current_balance, monthly_payment, is_active)
                VALUES (?, 'Car loan', 10000, 300, 1)
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO budget_sections (user_id, key, label, sort_order)
                VALUES (?, 'fixed', 'Fixed', 1)
                """,
                (uid,),
            )
            item_id = conn.execute(
                """
                INSERT INTO budget_items (user_id, name, section, default_amount, is_active)
                VALUES (?, 'Rent', 'fixed', 1000, 1)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO budget_entries (month_key, budget_item_id, amount)
                VALUES ('2026-06', ?, 999.0)
                """,
                (item_id,),
            )
            conn.execute(
                """
                INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key)
                VALUES ('2026-06-01', ?, 1500, '2026-06')
                """,
                (acct_id,),
            )
            conn.execute(
                """
                INSERT INTO contribution_overrides (account_id, from_month, to_month, override_amount, reason, created_at)
                VALUES (?, '2026-07', '2026-07', 0, 'Skipped', '2026-07-01T00:00:00Z')
                """,
                (acct_id,),
            )
            conn.execute(
                """
                INSERT INTO cash_flow_events (user_id, account_id, event_date, amount, kind, note)
                VALUES (?, ?, '2026-06-15', 50, 'transfer', 'test')
                """,
                (uid, acct_id),
            )
            conn.execute(
                """
                INSERT INTO allowance_tracking (user_id, tax_year, isa_used, lisa_used, notes)
                VALUES (?, '2026-27', 123, 45, 'mine')
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO allowance_tracking (user_id, tax_year, isa_used, lisa_used, notes)
                VALUES (?, '2026-27', 999, 88, 'theirs')
                """,
                (other_uid,),
            )
            conn.execute(
                """
                INSERT INTO allowance_tracking (user_id, tax_year, isa_used, lisa_used, notes)
                VALUES (NULL, '2026-27', 555, 66, 'legacy')
                """
            )
            conn.commit()

    _login(client, username, password)
    resp = client.get("/settings/export.json")
    assert resp.status_code == 200

    ctype = resp.headers.get("Content-Type", "")
    assert "application/json" in ctype

    dispo = resp.headers.get("Content-Disposition", "")
    assert "attachment" in dispo
    assert re.search(r'filename="steadyplan-export-\d{4}-\d{2}-\d{2}\.json"', dispo)

    payload = json.loads(resp.data.decode("utf-8"))
    assert payload["meta"]["export_schema_version"] == 1
    assert payload["meta"]["exported_at"]

    for key in ["assumptions", "accounts", "holdings", "goals", "debts", "budget", "history", "planning"]:
        assert key in payload

    assert any(a["name"] == "Vanguard ISA" for a in payload["accounts"])
    assert any(h["holding_name"] == "VUSA" for h in payload["holdings"])
    assert any(g["name"] == "Retirement" for g in payload["goals"])
    assert any(d["name"] == "Car loan" for d in payload["debts"])
    assert payload["budget"]["sections"]
    assert payload["budget"]["items"]
    assert payload["budget"]["entries"]
    assert payload["history"]["monthly_snapshots"]
    assert payload["planning"]["contribution_overrides"]
    assert payload["planning"]["cash_flow_events"]
    assert "allowance_tracking" in payload["planning"]
    assert any(r["tax_year"] == "2026-27" and r["isa_used"] == 123 for r in payload["planning"]["allowance_tracking"])
    assert not any(r.get("notes") == "theirs" for r in payload["planning"]["allowance_tracking"])
    assert not any(r.get("notes") == "legacy" for r in payload["planning"]["allowance_tracking"])
