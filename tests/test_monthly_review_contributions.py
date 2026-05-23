def _login(client, username, password):
    resp = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302)


def test_monthly_review_confirm_contribution_persists_flag(app, client, make_user):
    uid, username, password = make_user(username="mr-confirm", password="password123")
    _login(client, username, password)
    month_key = "2026-04"

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            aid = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, monthly_contribution, is_active, valuation_mode) "
                "VALUES (?, 'ISA', 100, 50, 1, 'manual')",
                (uid,),
            ).lastrowid
            conn.commit()

    resp = client.get(f"/monthly-review/?month={month_key}")
    assert resp.status_code == 200

    with app.app_context():
        from app.models import fetch_monthly_review, get_connection

        review = fetch_monthly_review(month_key, uid)
        assert review is not None
        with get_connection() as conn:
            item_id = conn.execute(
                "SELECT id FROM monthly_review_items WHERE review_id = ? AND account_id = ?",
                (review["id"], aid),
            ).fetchone()["id"]

    resp = client.post(
        "/monthly-review/api/confirm-contribution",
        json={"item_id": item_id, "confirmed": True, "month_key": month_key},
    )
    assert resp.status_code == 200

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            row = conn.execute(
                "SELECT contribution_confirmed FROM monthly_review_items WHERE id = ?",
                (item_id,),
            ).fetchone()
            assert int(row["contribution_confirmed"]) == 1


def test_monthly_review_skip_contribution_creates_zero_override(app, client, make_user):
    uid, username, password = make_user(username="mr-skip", password="password123")
    _login(client, username, password)
    month_key = "2026-04"

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            aid = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, monthly_contribution, is_active, valuation_mode) "
                "VALUES (?, 'ISA', 100, 50, 1, 'manual')",
                (uid,),
            ).lastrowid
            conn.commit()

    resp = client.post(
        "/monthly-review/api/skip-contribution",
        json={"account_id": aid, "month_key": month_key, "reason": "Skipped"},
    )
    assert resp.status_code == 200

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT override_amount, from_month, to_month
                FROM contribution_overrides
                WHERE account_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (aid,),
            ).fetchone()
            assert row is not None
            assert float(row["override_amount"]) == 0.0
            assert row["from_month"] == month_key
            assert row["to_month"] == month_key

