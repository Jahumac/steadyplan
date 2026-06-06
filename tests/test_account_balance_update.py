from datetime import date


def _login(client, username, password):
    resp = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302)


def test_user_can_update_own_account_balance_and_snapshot_created(app, client, make_user):
    uid, username, password = make_user(username="bal-own", password="password123")
    _login(client, username, password)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            aid = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active, valuation_mode) "
                "VALUES (?, 'Cash', 10, 1, 'manual')",
                (uid,),
            ).lastrowid
            conn.commit()

    resp = client.post(
        f"/accounts/{aid}/balance",
        data={"current_value": "123.45", "month_key": date.today().strftime("%Y-%m")},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    month_key = date.today().strftime("%Y-%m")
    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            row = conn.execute(
                "SELECT current_value, last_updated FROM accounts WHERE id = ? AND user_id = ?",
                (aid, uid),
            ).fetchone()
            assert float(row["current_value"]) == 123.45
            assert row["last_updated"]

            snap_count = conn.execute(
                "SELECT COUNT(*) AS c FROM monthly_snapshots WHERE account_id = ? AND month_key = ?",
                (aid, month_key),
            ).fetchone()["c"]
            assert int(snap_count) == 1

            ads_count = conn.execute(
                "SELECT COUNT(*) AS c FROM account_daily_snapshots WHERE user_id = ? AND account_id = ?",
                (uid, aid),
            ).fetchone()["c"]
            assert int(ads_count) == 1


def test_account_detail_balance_panel_uses_open_monthly_update_cta(app, client, make_user):
    uid, username, password = make_user(username="bal-detail-copy", password="password123")
    _login(client, username, password)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            aid = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active, valuation_mode) "
                "VALUES (?, 'Cash', 10, 1, 'manual')",
                (uid,),
            ).lastrowid
            conn.execute(
                "INSERT INTO account_daily_snapshots (user_id, account_id, snapshot_date, value) VALUES (?, ?, '2026-04-01', 10)",
                (uid, aid),
            )
            conn.execute(
                "INSERT INTO account_daily_snapshots (user_id, account_id, snapshot_date, value) VALUES (?, ?, '2026-04-02', 12)",
                (uid, aid),
            )
            conn.commit()

    resp = client.get(f"/accounts/{aid}", follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert '>Open monthly update<' in html
    assert 'investment day (shifted for weekends, plus settlement)' in html
    assert 'monthly update due date' not in html
    assert 'salary day shifted for weekends' not in html
    assert 'Budget overrides / monthly update entries' in html
    assert '>Go to Monthly Update<' not in html
    assert 'Monthly Review entries' not in html


def test_account_detail_open_monthly_update_uses_monthly_review_return_when_present(app, client, make_user):
    uid, username, password = make_user(username="bal-detail-next", password="password123")
    _login(client, username, password)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            aid = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active, valuation_mode) "
                "VALUES (?, 'Cash', 10, 1, 'manual')",
                (uid,),
            ).lastrowid
            conn.commit()

    resp = client.get(f"/accounts/{aid}?mode=view&next=%2Fmonthly-review%2F%3Fmonth%3D2026-04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'name="next" value="/monthly-review/?month=2026-04"' in html
    assert 'href="/monthly-review/?month=2026-04">Open monthly update</a>' in html
    assert 'href="/monthly-review/?month=' in html


def test_invalid_balance_rejected_without_changes(app, client, make_user):
    uid, username, password = make_user(username="bal-invalid", password="password123")
    _login(client, username, password)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            aid = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active, valuation_mode) "
                "VALUES (?, 'Cash', 10, 1, 'manual')",
                (uid,),
            ).lastrowid
            conn.commit()

    resp = client.post(
        f"/accounts/{aid}/balance",
        data={"current_value": "not-a-number"},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            row = conn.execute(
                "SELECT current_value FROM accounts WHERE id = ? AND user_id = ?",
                (aid, uid),
            ).fetchone()
            assert float(row["current_value"]) == 10.0


def test_user_cannot_update_other_users_account(app, client, make_user):
    uid1, username1, password1 = make_user(username="bal-alice", password="password123")
    uid2, username2, password2 = make_user(username="bal-bob", password="password123")

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            aid = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active, valuation_mode) "
                "VALUES (?, 'Alice Cash', 10, 1, 'manual')",
                (uid1,),
            ).lastrowid
            conn.commit()

    _login(client, username2, password2)
    resp = client.post(
        f"/accounts/{aid}/balance",
        data={"current_value": "999"},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            row = conn.execute(
                "SELECT current_value FROM accounts WHERE id = ? AND user_id = ?",
                (aid, uid1),
            ).fetchone()
            assert float(row["current_value"]) == 10.0


def test_repeated_updates_do_not_create_duplicate_monthly_snapshot_rows(app, client, make_user):
    uid, username, password = make_user(username="bal-repeat", password="password123")
    _login(client, username, password)
    month_key = date.today().strftime("%Y-%m")

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            aid = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active, valuation_mode) "
                "VALUES (?, 'Cash', 10, 1, 'manual')",
                (uid,),
            ).lastrowid
            conn.commit()

    resp = client.post(
        f"/accounts/{aid}/balance",
        data={"current_value": "101", "month_key": month_key},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    resp = client.post(
        f"/accounts/{aid}/balance",
        data={"current_value": "202", "month_key": month_key},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            snap_count = conn.execute(
                "SELECT COUNT(*) AS c FROM monthly_snapshots WHERE account_id = ? AND month_key = ?",
                (aid, month_key),
            ).fetchone()["c"]
            assert int(snap_count) == 1
            bal = conn.execute(
                "SELECT balance FROM monthly_snapshots WHERE account_id = ? AND month_key = ?",
                (aid, month_key),
            ).fetchone()["balance"]
            assert float(bal) == 202.0


def test_bulk_balance_update_page_lists_only_current_users_accounts(app, client, make_user):
    uid1, username1, password1 = make_user(username="bulk-a", password="password123")
    uid2, username2, password2 = make_user(username="bulk-b", password="password123")

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active, valuation_mode) "
                "VALUES (?, 'Alice Cash', 10, 1, 'manual')",
                (uid1,),
            )
            conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active, valuation_mode) "
                "VALUES (?, 'Bob Cash', 20, 1, 'manual')",
                (uid2,),
            )
            conn.commit()

    _login(client, username1, password1)
    resp = client.get("/accounts/balances/bulk")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Alice Cash" in html
    assert "Bob Cash" not in html


def test_user_can_bulk_update_multiple_account_balances(app, client, make_user):
    uid, username, password = make_user(username="bulk-own", password="password123")
    _login(client, username, password)
    month_key = date.today().strftime("%Y-%m")

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            a1 = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active, valuation_mode) "
                "VALUES (?, 'A1', 10, 1, 'manual')",
                (uid,),
            ).lastrowid
            a2 = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active, valuation_mode) "
                "VALUES (?, 'A2', 20, 1, 'manual')",
                (uid,),
            ).lastrowid
            conn.commit()

    resp = client.post(
        "/accounts/balances/bulk",
        data={
            "month_key": month_key,
            f"balance_{a1}": "111.11",
            f"balance_{a2}": "222.22",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            v1 = conn.execute("SELECT current_value FROM accounts WHERE id = ?", (a1,)).fetchone()["current_value"]
            v2 = conn.execute("SELECT current_value FROM accounts WHERE id = ?", (a2,)).fetchone()["current_value"]
            assert float(v1) == 111.11
            assert float(v2) == 222.22

            c1 = conn.execute(
                "SELECT COUNT(*) AS c FROM monthly_snapshots WHERE account_id = ? AND month_key = ?",
                (a1, month_key),
            ).fetchone()["c"]
            c2 = conn.execute(
                "SELECT COUNT(*) AS c FROM monthly_snapshots WHERE account_id = ? AND month_key = ?",
                (a2, month_key),
            ).fetchone()["c"]
            assert int(c1) == 1
            assert int(c2) == 1


def test_bulk_update_leaves_blank_rows_unchanged(app, client, make_user):
    uid, username, password = make_user(username="bulk-blank", password="password123")
    _login(client, username, password)
    month_key = date.today().strftime("%Y-%m")

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            a1 = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active, valuation_mode) "
                "VALUES (?, 'A1', 10, 1, 'manual')",
                (uid,),
            ).lastrowid
            a2 = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active, valuation_mode) "
                "VALUES (?, 'A2', 20, 1, 'manual')",
                (uid,),
            ).lastrowid
            conn.commit()

    resp = client.post(
        "/accounts/balances/bulk",
        data={
            "month_key": month_key,
            f"balance_{a1}": "111",
            f"balance_{a2}": "",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            v1 = conn.execute("SELECT current_value FROM accounts WHERE id = ?", (a1,)).fetchone()["current_value"]
            v2 = conn.execute("SELECT current_value FROM accounts WHERE id = ?", (a2,)).fetchone()["current_value"]
            assert float(v1) == 111.0
            assert float(v2) == 20.0


def test_bulk_update_invalid_input_does_not_partially_update(app, client, make_user):
    uid, username, password = make_user(username="bulk-invalid", password="password123")
    _login(client, username, password)
    month_key = date.today().strftime("%Y-%m")

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            a1 = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active, valuation_mode) "
                "VALUES (?, 'A1', 10, 1, 'manual')",
                (uid,),
            ).lastrowid
            a2 = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active, valuation_mode) "
                "VALUES (?, 'A2', 20, 1, 'manual')",
                (uid,),
            ).lastrowid
            conn.commit()

    resp = client.post(
        "/accounts/balances/bulk",
        data={
            "month_key": month_key,
            f"balance_{a1}": "111",
            f"balance_{a2}": "nope",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            v1 = conn.execute("SELECT current_value FROM accounts WHERE id = ?", (a1,)).fetchone()["current_value"]
            v2 = conn.execute("SELECT current_value FROM accounts WHERE id = ?", (a2,)).fetchone()["current_value"]
            assert float(v1) == 10.0
            assert float(v2) == 20.0


def test_bulk_update_cannot_update_other_users_account_id(app, client, make_user):
    uid1, username1, password1 = make_user(username="bulk-own2", password="password123")
    uid2, username2, password2 = make_user(username="bulk-other2", password="password123")
    month_key = date.today().strftime("%Y-%m")

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            a1 = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active, valuation_mode) "
                "VALUES (?, 'A1', 10, 1, 'manual')",
                (uid1,),
            ).lastrowid
            other = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active, valuation_mode) "
                "VALUES (?, 'Other', 999, 1, 'manual')",
                (uid2,),
            ).lastrowid
            conn.commit()

    _login(client, username1, password1)
    resp = client.post(
        "/accounts/balances/bulk",
        data={
            "month_key": month_key,
            f"balance_{a1}": "111",
            f"balance_{other}": "222",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            v1 = conn.execute("SELECT current_value FROM accounts WHERE id = ?", (a1,)).fetchone()["current_value"]
            v2 = conn.execute("SELECT current_value FROM accounts WHERE id = ?", (other,)).fetchone()["current_value"]
            assert float(v1) == 10.0
            assert float(v2) == 999.0


def test_repeated_bulk_updates_do_not_create_duplicate_monthly_snapshots(app, client, make_user):
    uid, username, password = make_user(username="bulk-repeat", password="password123")
    _login(client, username, password)
    month_key = date.today().strftime("%Y-%m")

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            a1 = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active, valuation_mode) "
                "VALUES (?, 'A1', 10, 1, 'manual')",
                (uid,),
            ).lastrowid
            conn.commit()

    resp = client.post(
        "/accounts/balances/bulk",
        data={"month_key": month_key, f"balance_{a1}": "111"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    resp = client.post(
        "/accounts/balances/bulk",
        data={"month_key": month_key, f"balance_{a1}": "222"},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            snap_count = conn.execute(
                "SELECT COUNT(*) AS c FROM monthly_snapshots WHERE account_id = ? AND month_key = ?",
                (a1, month_key),
            ).fetchone()["c"]
            assert int(snap_count) == 1
            bal = conn.execute(
                "SELECT balance FROM monthly_snapshots WHERE account_id = ? AND month_key = ?",
                (a1, month_key),
            ).fetchone()["balance"]
            assert float(bal) == 222.0
