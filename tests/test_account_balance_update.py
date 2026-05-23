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

