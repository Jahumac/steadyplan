def _login(client, username, password):
    resp = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302)


def _set_review_status_and_item(conn, user_id, month_key, account_id, status, expected_contribution, confirmed):
    conn.execute(
        "INSERT OR IGNORE INTO monthly_reviews (user_id, month_key, status) VALUES (?, ?, ?)",
        (user_id, month_key, status),
    )
    conn.execute(
        "UPDATE monthly_reviews SET status = ? WHERE user_id = ? AND month_key = ?",
        (status, user_id, month_key),
    )
    review_id = int(
        conn.execute(
            "SELECT id FROM monthly_reviews WHERE user_id = ? AND month_key = ?",
            (user_id, month_key),
        ).fetchone()["id"]
    )
    existing = conn.execute(
        "SELECT id FROM monthly_review_items WHERE review_id = ? AND account_id = ?",
        (review_id, account_id),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE monthly_review_items
            SET expected_contribution = ?, contribution_confirmed = ?
            WHERE id = ?
            """,
            (expected_contribution, 1 if confirmed else 0, int(existing["id"])),
        )
    else:
        conn.execute(
            """
            INSERT INTO monthly_review_items (review_id, account_id, expected_contribution, contribution_confirmed)
            VALUES (?, ?, ?, ?)
            """,
            (review_id, account_id, expected_contribution, 1 if confirmed else 0),
        )
    return review_id


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


def test_isa_usage_draft_review_does_not_override_default_or_override(app, make_user):
    from datetime import date

    uid, _, _ = make_user(username="isa-draft", password="password123")
    month_key = "2026-05"
    today = date(2026, 6, 30)
    salary_day = 28

    with app.app_context():
        from app.calculations import calculate_isa_usage
        from app.models import (
            fetch_completed_tax_year_contributions,
            fetch_isa_overrides_for_tax_year,
            get_connection,
        )

        with get_connection() as conn:
            aid = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, valuation_mode, monthly_contribution, current_value, is_active)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 'manual', 100, 0, 1)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO contribution_overrides (account_id, from_month, to_month, override_amount, reason, created_at)
                VALUES (?, ?, ?, 50, 'test', datetime('now'))
                """,
                (aid, month_key, month_key),
            )
            _set_review_status_and_item(
                conn,
                uid,
                month_key=month_key,
                account_id=aid,
                status="in_progress",
                expected_contribution=999,
                confirmed=True,
            )
            conn.commit()

        ty_start = "2026-04-06"
        ty_end = "2027-04-05"
        overrides = fetch_isa_overrides_for_tax_year(uid, ty_start, ty_end)
        review_rows = fetch_completed_tax_year_contributions(uid, "2026-04", "2027-03")

        accounts = [
            {
                "id": aid,
                "name": "ISA",
                "wrapper_type": "Stocks & Shares ISA",
                "monthly_contribution": 100,
            }
        ]
        usage = calculate_isa_usage(
            accounts,
            ad_hoc_contributions=[],
            today=today,
            salary_day=salary_day,
            isa_overrides=overrides,
            review_contributions=review_rows,
        )
        assert usage["monthly_isa"] == 250.0  # Apr 100 + May 50 (override) + Jun 100


def test_isa_usage_ignores_junior_isa_overrides_for_adult_allowance(app, make_user):
    uid, _, _ = make_user(username="junior-isa-overrides", password="password123")

    with app.app_context():
        from app.models import fetch_isa_overrides_for_tax_year, get_connection

        with get_connection() as conn:
            aid = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, valuation_mode, monthly_contribution, current_value, is_active)
                VALUES (?, 'Junior ISA', 'Junior ISA', 'manual', 100, 0, 1)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO contribution_overrides (account_id, from_month, to_month, override_amount, reason, created_at)
                VALUES (?, '2026-04', '2026-06', 50, 'test', datetime('now'))
                """,
                (aid,),
            )
            conn.commit()

        overrides = fetch_isa_overrides_for_tax_year(uid, "2026-04-06", "2027-04-05")

    assert overrides == []


def test_isa_usage_completed_review_overrides_default_or_override(app, make_user):
    from datetime import date

    uid, _, _ = make_user(username="isa-complete", password="password123")
    month_key = "2026-05"
    today = date(2026, 6, 30)
    salary_day = 28

    with app.app_context():
        from app.calculations import calculate_isa_usage
        from app.models import (
            fetch_completed_tax_year_contributions,
            fetch_isa_overrides_for_tax_year,
            get_connection,
        )

        with get_connection() as conn:
            aid = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, valuation_mode, monthly_contribution, current_value, is_active)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 'manual', 100, 0, 1)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO contribution_overrides (account_id, from_month, to_month, override_amount, reason, created_at)
                VALUES (?, ?, ?, 50, 'test', datetime('now'))
                """,
                (aid, month_key, month_key),
            )
            _set_review_status_and_item(
                conn,
                uid,
                month_key=month_key,
                account_id=aid,
                status="complete",
                expected_contribution=999,
                confirmed=True,
            )
            conn.commit()

        ty_start = "2026-04-06"
        ty_end = "2027-04-05"
        overrides = fetch_isa_overrides_for_tax_year(uid, ty_start, ty_end)
        review_rows = fetch_completed_tax_year_contributions(uid, "2026-04", "2027-03")

        accounts = [
            {
                "id": aid,
                "name": "ISA",
                "wrapper_type": "Stocks & Shares ISA",
                "monthly_contribution": 100,
            }
        ]
        usage = calculate_isa_usage(
            accounts,
            ad_hoc_contributions=[],
            today=today,
            salary_day=salary_day,
            isa_overrides=overrides,
            review_contributions=review_rows,
        )
        assert usage["monthly_isa"] == 1199.0  # Apr 100 + May 999 (review) + Jun 100


def test_isa_usage_completed_review_skip_produces_zero(app, make_user):
    from datetime import date

    uid, _, _ = make_user(username="isa-skip-complete", password="password123")
    month_key = "2026-05"
    today = date(2026, 6, 30)
    salary_day = 28

    with app.app_context():
        from app.calculations import calculate_isa_usage
        from app.models import (
            fetch_completed_tax_year_contributions,
            fetch_isa_overrides_for_tax_year,
            get_connection,
        )

        with get_connection() as conn:
            aid = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, valuation_mode, monthly_contribution, current_value, is_active)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 'manual', 100, 0, 1)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO contribution_overrides (account_id, from_month, to_month, override_amount, reason, created_at)
                VALUES (?, ?, ?, 0, 'skipped', datetime('now'))
                """,
                (aid, month_key, month_key),
            )
            _set_review_status_and_item(
                conn,
                uid,
                month_key=month_key,
                account_id=aid,
                status="complete",
                expected_contribution=100,
                confirmed=False,
            )
            conn.commit()

        ty_start = "2026-04-06"
        ty_end = "2027-04-05"
        overrides = fetch_isa_overrides_for_tax_year(uid, ty_start, ty_end)
        review_rows = fetch_completed_tax_year_contributions(uid, "2026-04", "2027-03")

        accounts = [
            {
                "id": aid,
                "name": "ISA",
                "wrapper_type": "Stocks & Shares ISA",
                "monthly_contribution": 100,
            }
        ]
        usage = calculate_isa_usage(
            accounts,
            ad_hoc_contributions=[],
            today=today,
            salary_day=salary_day,
            isa_overrides=overrides,
            review_contributions=review_rows,
        )
        assert usage["monthly_isa"] == 200.0  # Apr 100 + May 0 (skipped) + Jun 100


def test_pension_usage_respects_overrides_and_completed_review_and_ignores_draft(app, make_user):
    from datetime import date

    today = date(2026, 6, 30)
    salary_day = 28
    month_key = "2026-05"

    with app.app_context():
        from app.calculations import calculate_pension_usage
        from app.models import (
            fetch_completed_tax_year_contributions,
            fetch_pension_overrides_for_tax_year,
            get_connection,
        )

        uid, _, _ = make_user(username="pension-usage", password="password123")
        with get_connection() as conn:
            pid = conn.execute(
                """
                INSERT INTO accounts (
                    user_id, name, wrapper_type, category, valuation_mode,
                    monthly_contribution, employer_contribution, contribution_method, current_value, is_active
                )
                VALUES (?, 'SIPP', 'SIPP', 'Pension', 'manual', 800, 0, 'standard', 0, 1)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO contribution_overrides (account_id, from_month, to_month, override_amount, reason, created_at)
                VALUES (?, ?, ?, 0, 'skip', datetime('now'))
                """,
                (pid, month_key, month_key),
            )
            conn.commit()

        ty_start = "2026-04-06"
        ty_end = "2027-04-05"
        pension_overrides = fetch_pension_overrides_for_tax_year(uid, ty_start, ty_end)
        review_rows = fetch_completed_tax_year_contributions(uid, "2026-04", "2027-03")
        accounts = [
            {
                "id": pid,
                "name": "SIPP",
                "wrapper_type": "SIPP",
                "category": "Pension",
                "monthly_contribution": 800,
                "employer_contribution": 0,
                "contribution_method": "standard",
            }
        ]
        usage = calculate_pension_usage(
            accounts,
            ad_hoc_contributions=[],
            assumptions={"tax_band": "basic"},
            today=today,
            salary_day=salary_day,
            pension_overrides=pension_overrides,
            review_contributions=review_rows,
        )
        assert usage["pension_used"] == 2000.0  # Apr 1000 + May 0 + Jun 1000

        with get_connection() as conn:
            conn.execute("DELETE FROM contribution_overrides WHERE account_id = ?", (pid,))
            _set_review_status_and_item(
                conn,
                uid,
                month_key=month_key,
                account_id=pid,
                status="complete",
                expected_contribution=400,
                confirmed=True,
            )
            conn.commit()

        pension_overrides = fetch_pension_overrides_for_tax_year(uid, ty_start, ty_end)
        review_rows = fetch_completed_tax_year_contributions(uid, "2026-04", "2027-03")
        usage = calculate_pension_usage(
            accounts,
            ad_hoc_contributions=[],
            assumptions={"tax_band": "basic"},
            today=today,
            salary_day=salary_day,
            pension_overrides=pension_overrides,
            review_contributions=review_rows,
        )
        assert usage["pension_used"] == 2500.0  # Apr 1000 + May 500 + Jun 1000

        with get_connection() as conn:
            conn.execute("DELETE FROM monthly_reviews WHERE user_id = ? AND month_key = ?", (uid, month_key))
            _set_review_status_and_item(
                conn,
                uid,
                month_key=month_key,
                account_id=pid,
                status="in_progress",
                expected_contribution=0,
                confirmed=True,
            )
            conn.commit()

        review_rows = fetch_completed_tax_year_contributions(uid, "2026-04", "2027-03")
        usage = calculate_pension_usage(
            accounts,
            ad_hoc_contributions=[],
            assumptions={"tax_band": "basic"},
            today=today,
            salary_day=salary_day,
            pension_overrides=pension_overrides,
            review_contributions=review_rows,
        )
        assert usage["pension_used"] == 3000.0  # draft ignored => Apr/May/Jun all 1000


def test_pension_usage_salary_sacrifice_counts_into_pot_as_employer(app, make_user):
    from datetime import date

    uid, _, _ = make_user(username="pension-salary-sacrifice", password="password123")
    today = date(2026, 6, 30)
    salary_day = 28

    with app.app_context():
        from app.calculations import calculate_pension_usage

        accounts = [
            {
                "id": 1,
                "name": "Workplace",
                "wrapper_type": "Workplace Pension",
                "category": "Pension",
                "monthly_contribution": 1000,
                "employer_contribution": 500,
                "contribution_method": "salary_sacrifice",
                "pension_contribution_day": salary_day,
            }
        ]
        usage = calculate_pension_usage(
            accounts,
            ad_hoc_contributions=[],
            assumptions={"tax_band": "basic"},
            today=today,
            salary_day=salary_day,
            pension_overrides=[],
            review_contributions=[],
        )
        assert usage["pension_used"] == 4500.0  # Apr/May/Jun each 1500
        assert usage["pension_personal_used"] == 0.0
        assert usage["pension_employer_used"] == 4500.0
