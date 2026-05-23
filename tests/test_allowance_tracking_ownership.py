def test_allowance_tracking_is_user_scoped(app, make_user):
    uid1, _, _ = make_user(username="alice", password="password123")
    uid2, _, _ = make_user(username="bob", password="password123")

    from app.models import fetch_allowance_tracking, upsert_allowance_tracking

    with app.app_context():
        upsert_allowance_tracking(uid1, "2026-27", isa_used=111.0, lisa_used=22.0, notes="a")
        upsert_allowance_tracking(uid2, "2026-27", isa_used=999.0, lisa_used=88.0, notes="b")

        r1 = fetch_allowance_tracking(uid1)
        r2 = fetch_allowance_tracking(uid2)

        assert r1["user_id"] == uid1
        assert r1["tax_year"] == "2026-27"
        assert float(r1["isa_used"]) == 111.0

        assert r2["user_id"] == uid2
        assert r2["tax_year"] == "2026-27"
        assert float(r2["isa_used"]) == 999.0


def test_allowance_tracking_does_not_leak_between_users(app, make_user):
    uid1, _, _ = make_user(username="alice2", password="password123")
    uid2, _, _ = make_user(username="bob2", password="password123")

    from app.models import fetch_allowance_tracking, upsert_allowance_tracking

    with app.app_context():
        upsert_allowance_tracking(uid2, "2026-27", isa_used=500.0)
        assert fetch_allowance_tracking(uid1) is None


def test_migration_backfills_single_user_allowance_tracking(app, make_user):
    uid, _, _ = make_user(username="solo", password="password123")

    from app.models import get_connection
    from app.models.schema import init_db

    with app.app_context():
        with get_connection() as conn:
            conn.execute("DELETE FROM schema_migrations WHERE name = 'v9_allowance_tracking_user'")
            conn.execute("DROP TABLE IF EXISTS allowance_tracking")
            conn.execute(
                """
                CREATE TABLE allowance_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tax_year TEXT NOT NULL,
                    isa_used REAL DEFAULT 0,
                    lisa_used REAL DEFAULT 0,
                    notes TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT INTO allowance_tracking (tax_year, isa_used, lisa_used, notes)
                VALUES ('2026-27', 123.0, 45.0, 'legacy')
                """
            )
            conn.commit()

        init_db()

        with get_connection() as conn:
            row = conn.execute(
                "SELECT user_id, tax_year, isa_used FROM allowance_tracking ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert row is not None
            assert row["user_id"] == uid
            assert row["tax_year"] == "2026-27"
            assert float(row["isa_used"]) == 123.0

