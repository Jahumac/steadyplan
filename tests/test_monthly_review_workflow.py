from app.services.monthly_review_checklist import (
    encode_monthly_review_notes,
    parse_monthly_review_notes,
)


def test_overview_renders_monthly_review_card(auth_client):
    resp = auth_client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Monthly review" in html
    assert "Checklist:" in html


def test_monthly_review_get_is_idempotent_for_user_month(app, client, make_user):
    uid, username, password = make_user(username="mr-idem", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = "2026-04"
    resp1 = client.get(f"/monthly-review/?month={month_key}")
    assert resp1.status_code == 200
    resp2 = client.get(f"/monthly-review/?month={month_key}")
    assert resp2.status_code == 200

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            c = conn.execute(
                "SELECT COUNT(*) AS c FROM monthly_reviews WHERE user_id = ? AND month_key = ?",
                (uid, month_key),
            ).fetchone()["c"]
    assert int(c) == 1


def test_monthly_review_page_is_lightweight_and_links_render(app, client, make_user):
    uid, username, password = make_user(username="mr-save", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = "2026-04"
    resp = client.get(f"/monthly-review/?month={month_key}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Monthly review" in html
    assert "Work down the page: confirm expected contributions" in html
    assert "Quick checklist" not in html
    assert "Monthly Update Guide" not in html
    assert "How this works" not in html
    assert "Backup/export checked" not in html
    assert "Expected Contributions" not in html
    assert "Expected contributions" in html
    assert "Confirm expected contributions that happened this month" in html
    assert "not a transaction record" in html
    assert "To confirm" in html
    assert "<p class=\"eyebrow\">Optional</p>" not in html
    assert "Update manual balances" in html
    assert 'href="#manual-accounts"' in html
    assert "/accounts/balances/bulk" not in html
    assert 'href="/accounts/' in html
    assert 'href="/goals/' in html
    assert 'href="/budget/debts/' in html
    assert 'href="/settings/?mode=edit"' in html

def test_monthly_review_notes_persist(app, client, make_user):
    uid, username, password = make_user(username="mr-save-note", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = "2026-04"
    note = "Quick note for the month"
    resp = client.post(
        "/monthly-review/",
        data={
            "form_name": "save_review_notes",
            "month": month_key,
            "notes": note,
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        from app.models import fetch_monthly_review

        review = fetch_monthly_review(month_key, uid)
        assert review is not None
        assert review["notes"] == note


def test_mark_complete_does_not_wipe_saved_monthly_review_notes(app, client, make_user):
    uid, username, password = make_user(username="mr-complete-notes", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = "2026-04"

    resp = client.post(
        "/monthly-review/",
        data={
            "form_name": "save_review_notes",
            "month": month_key,
            "notes": "Keep an eye on assumptions",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    resp = client.post(
        "/monthly-review/",
        data={
            "form_name": "mark_complete",
            "month": month_key,
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        from app.models import fetch_monthly_review

        review = fetch_monthly_review(month_key, uid)
        assert review is not None
        assert review["status"] == "complete"

    parsed = parse_monthly_review_notes(review.get("notes"))
    assert parsed["notes"] == "Keep an eye on assumptions"
    assert parsed["checked"] == set()


def test_mark_complete_skips_unupdated_manual_and_premium_bonds_snapshots(app, client, make_user):
    uid, username, password = make_user(username="mr-snap-safe", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = "2026-04"

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            holdings_acc = conn.execute(
                """
                INSERT INTO accounts (user_id, name, valuation_mode, current_value, is_active)
                VALUES (?, 'Holdings', 'holdings', 0, 1)
                """,
                (uid,),
            ).lastrowid
            manual_acc = conn.execute(
                """
                INSERT INTO accounts (user_id, name, valuation_mode, current_value, is_active)
                VALUES (?, 'Manual', 'manual', 1234, 1)
                """,
                (uid,),
            ).lastrowid
            pb_acc = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, valuation_mode, current_value, is_active)
                VALUES (?, 'PB', 'Premium Bonds', 'premium_bonds', 5678, 1)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO holdings (account_id, holding_name, ticker, value, units, price)
                VALUES (?, 'VUSA', 'VUSA', 1000, 10, 100)
                """,
                (holdings_acc,),
            )
            conn.commit()

    resp = client.post(
        "/monthly-review/",
        data={"form_name": "mark_complete", "month": month_key},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        from app.models import get_connection
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT account_id FROM monthly_snapshots
                WHERE month_key = ?
                ORDER BY account_id ASC
                """,
                (month_key,),
            ).fetchall()
            snapped = [int(r["account_id"]) for r in rows]

    assert holdings_acc in snapped
    assert manual_acc not in snapped
    assert pb_acc not in snapped


def test_confirm_import_marks_holdings_updated_for_touched_accounts_only(app, client, make_user):
    from datetime import date

    uid, username, password = make_user(username="mr-csv-holdings", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            a1 = conn.execute(
                "INSERT INTO accounts (user_id, name, valuation_mode, is_active) VALUES (?, 'A1', 'holdings', 1)",
                (uid,),
            ).lastrowid
            a2 = conn.execute(
                "INSERT INTO accounts (user_id, name, valuation_mode, is_active) VALUES (?, 'A2', 'holdings', 1)",
                (uid,),
            ).lastrowid
            h1 = conn.execute(
                "INSERT INTO holdings (account_id, holding_name, ticker, value, units, price) VALUES (?, 'AAA', 'AAA', 10, 1, 10)",
                (a1,),
            ).lastrowid
            h2 = conn.execute(
                "INSERT INTO holdings (account_id, holding_name, ticker, value, units, price) VALUES (?, 'BBB', 'BBB', 20, 2, 10)",
                (a2,),
            ).lastrowid
            conn.commit()

    with client.session_transaction() as sess:
        sess["csv_import"] = {
            "platform": "generic",
            "matched": [
                {"holding_id": h1, "new_units": 3, "new_price": 11},
                {"holding_id": h2, "new_units": 4, "new_price": 12},
            ],
        }

    resp = client.post(
        "/monthly-review/confirm-import",
        data={
            "apply_holding_id": [str(h1)],
            f"units_{h1}": "3",
            f"price_{h1}": "11",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    month_key = date.today().strftime("%Y-%m")
    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            review = conn.execute(
                "SELECT id FROM monthly_reviews WHERE user_id = ? AND month_key = ?",
                (uid, month_key),
            ).fetchone()
            assert review is not None
            flags = conn.execute(
                """
                SELECT account_id, holdings_updated
                FROM monthly_review_items
                WHERE review_id = ?
                """,
                (int(review["id"]),),
            ).fetchall()
            flags_by_account = {int(r["account_id"]): int(r["holdings_updated"] or 0) for r in flags}

    assert flags_by_account.get(a1) == 1
    assert flags_by_account.get(a2) == 0


def test_update_monthly_review_notes_enforces_ownership(app, make_user):
    uid1, _, _ = make_user(username="mr-own-a", password="password123")
    uid2, _, _ = make_user(username="mr-own-b", password="password123")

    with app.app_context():
        from app.models import fetch_or_create_monthly_review, fetch_monthly_review, update_monthly_review_notes

        month_key = "2026-04"
        review_a = fetch_or_create_monthly_review(month_key, uid1)
        update_monthly_review_notes(review_a["id"], "alice-note", uid1)

        update_monthly_review_notes(review_a["id"], "bob-hack", uid2)

        still_a = fetch_monthly_review(month_key, uid1)
        assert still_a is not None
        assert still_a["notes"] == "alice-note"


def test_plain_notes_saved_without_checks_stay_plain_text(app, client, make_user):
    uid, username, password = make_user(username="mr-plain", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = "2026-04"
    note = "Just plain text"
    resp = client.post(
        "/monthly-review/",
        data={
            "form_name": "save_review_notes",
            "month": month_key,
            "notes": note,
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        from app.models import fetch_monthly_review

        review = fetch_monthly_review(month_key, uid)
        assert review is not None
        assert review["notes"] == note


def test_malformed_internal_structured_notes_do_not_leak_json_to_ui(app, client, make_user):
    uid, username, password = make_user(username="mr-malformed", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = "2026-04"
    with app.app_context():
        from app.models import fetch_or_create_monthly_review, get_connection

        review = fetch_or_create_monthly_review(month_key, uid)
        raw = '{"__shelly_monthly_review_notes_v":1,"notes":{"x":1},"checked":"nope"}'
        with get_connection() as conn:
            conn.execute(
                "UPDATE monthly_reviews SET notes = ? WHERE id = ? AND user_id = ?",
                (raw, review["id"], uid),
            )
            conn.commit()

    resp = client.get(f"/monthly-review/?month={month_key}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "__shelly_monthly_review_notes_v" not in html


def test_structured_notes_are_not_rendered_as_raw_json(app, client, make_user):
    uid, username, password = make_user(username="mr-no-leak", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = "2026-04"
    with app.app_context():
        from app.models import fetch_or_create_monthly_review, get_connection

        review = fetch_or_create_monthly_review(month_key, uid)
        encoded = encode_monthly_review_notes("Hello", {"goals"})
        with get_connection() as conn:
            conn.execute(
                "UPDATE monthly_reviews SET notes = ? WHERE id = ? AND user_id = ?",
                (encoded, review["id"], uid),
            )
            conn.commit()

    resp = client.get(f"/monthly-review/?month={month_key}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "__shelly_monthly_review_notes_v" not in html
    assert "Hello" in html


def test_invalid_json_like_notes_do_not_crash_and_show_as_text(app, client, make_user):
    uid, username, password = make_user(username="mr-invalid-json", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = "2026-04"
    with app.app_context():
        from app.models import fetch_or_create_monthly_review, get_connection

        review = fetch_or_create_monthly_review(month_key, uid)
        raw = "{not json}"
        with get_connection() as conn:
            conn.execute(
                "UPDATE monthly_reviews SET notes = ? WHERE id = ? AND user_id = ?",
                (raw, review["id"], uid),
            )
            conn.commit()

    resp = client.get(f"/monthly-review/?month={month_key}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert raw in html


def test_corrupted_internal_json_like_notes_do_not_leak_marker(app, client, make_user):
    uid, username, password = make_user(username="mr-corrupt-internal", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    month_key = "2026-04"
    with app.app_context():
        from app.models import fetch_or_create_monthly_review, get_connection

        review = fetch_or_create_monthly_review(month_key, uid)
        raw = '{"__shelly_monthly_review_notes_v":1,"notes":"x"'
        with get_connection() as conn:
            conn.execute(
                "UPDATE monthly_reviews SET notes = ? WHERE id = ? AND user_id = ?",
                (raw, review["id"], uid),
            )
            conn.commit()

    resp = client.get(f"/monthly-review/?month={month_key}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "__shelly_monthly_review_notes_v" not in html
