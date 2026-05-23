import io
import os
import re
import sqlite3


def _login(client, username, password):
    resp = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )
    assert resp.status_code == 200


def _count_user_accounts(app, user_id):
    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            return int(conn.execute("SELECT COUNT(*) AS c FROM accounts WHERE user_id = ?", (user_id,)).fetchone()["c"])


def _export_json_bytes(client):
    resp = client.get("/settings/export.json")
    assert resp.status_code == 200
    return resp.data


def _extract_restore_token(html):
    m = re.search(r'name="restore_token" value="([^"]+)"', html)
    assert m, "Expected restore_token hidden field in HTML"
    return m.group(1)


def test_restore_commit_requires_login(client, make_user):
    make_user(username="restore-commit-login", password="password123")
    resp = client.post("/settings/restore/commit", data={}, follow_redirects=False)
    assert resp.status_code in (302, 401)
    if resp.status_code == 302:
        assert "/login" in resp.headers.get("Location", "")


def test_invalid_backup_does_not_show_restore_action(app, client, make_user):
    uid, username, password = make_user(username="restore-invalid-ui", password="password123")
    _login(client, username, password)

    resp = client.post(
        "/settings/restore/validate",
        data={"backup_file": (io.BytesIO(b"{"), "backup.json")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    body = resp.data.decode("utf-8")
    assert "This backup cannot be restored yet. No data has been changed." in body
    assert "/settings/restore/commit" not in body


def test_valid_backup_requires_explicit_confirmation_and_then_restores(app, client, make_user):
    uid1, u1, p1 = make_user(username="restore-u1-flow", password="password123", is_admin=True)
    uid2, u2, p2 = make_user(username="restore-u2-flow", password="password123", is_admin=True)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution) VALUES (?, 'A1', 'isa', 1000, 100)",
                (uid1,),
            )
            conn.execute(
                "INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution) VALUES (?, 'A2', 'cash', 2000, 200)",
                (uid1,),
            )
            conn.execute(
                "INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution) VALUES (?, 'B1', 'isa', 3000, 300)",
                (uid2,),
            )
            conn.commit()

    _login(client, u1, p1)
    export_bytes = _export_json_bytes(client)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution) VALUES (?, 'EXTRA', 'cash', 1, 1)",
                (uid1,),
            )
            conn.commit()

    before_u2 = _count_user_accounts(app, uid2)

    resp_validate = client.post(
        "/settings/restore/validate",
        data={"backup_file": (io.BytesIO(export_bytes), "backup.json")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    body_validate = resp_validate.data.decode("utf-8")
    assert "This backup looks valid. No data has been changed." in body_validate
    assert "Type RESTORE" in body_validate
    token = _extract_restore_token(body_validate)

    before = _count_user_accounts(app, uid1)
    resp_missing_confirm = client.post(
        "/settings/restore/commit",
        data={"restore_token": token},
        follow_redirects=True,
    )
    body_missing = resp_missing_confirm.data.decode("utf-8")
    assert "To restore, tick the checkbox and type RESTORE to confirm." in body_missing
    after = _count_user_accounts(app, uid1)
    assert after == before

    resp_wrong_phrase = client.post(
        "/settings/restore/commit",
        data={"restore_token": token, "confirm_replace": "1", "confirm_phrase": "NOPE"},
        follow_redirects=True,
    )
    body_wrong = resp_wrong_phrase.data.decode("utf-8")
    assert "To restore, tick the checkbox and type RESTORE to confirm." in body_wrong
    assert _count_user_accounts(app, uid1) == before

    resp_ok = client.post(
        "/settings/restore/commit",
        data={"restore_token": token, "confirm_replace": "1", "confirm_phrase": "RESTORE"},
        follow_redirects=True,
    )
    body_ok = resp_ok.data.decode("utf-8")
    assert "Restore complete. Your data has been replaced." in body_ok

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            names = {r["name"] for r in conn.execute("SELECT name FROM accounts WHERE user_id = ?", (uid1,)).fetchall()}
            assert "EXTRA" not in names
            assert "A1" in names and "A2" in names

    assert _count_user_accounts(app, uid2) == before_u2


def test_restore_commit_revalidates_before_writing(app, client, make_user):
    uid, username, password = make_user(username="restore-revalidate", password="password123")

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution) VALUES (?, 'A1', 'isa', 1000, 100)",
                (uid,),
            )
            conn.commit()

    _login(client, username, password)
    export_bytes = _export_json_bytes(client)

    resp_validate = client.post(
        "/settings/restore/validate",
        data={"backup_file": (io.BytesIO(export_bytes), "backup.json")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    token = _extract_restore_token(resp_validate.data.decode("utf-8"))

    with app.app_context():
        from app.routes.settings import _restore_staging_dir

        staged = _restore_staging_dir() / f"{token}.json"
        assert staged.exists()
        staged.write_bytes(b"{")

    before = _count_user_accounts(app, uid)
    resp_commit = client.post(
        "/settings/restore/commit",
        data={"restore_token": token, "confirm_replace": "1", "confirm_phrase": "RESTORE"},
        follow_redirects=True,
    )
    body = resp_commit.data.decode("utf-8")
    assert "That backup is not valid. No data has been changed." in body
    after = _count_user_accounts(app, uid)
    assert after == before


def test_restore_commit_rejects_expired_staged_token_and_deletes_file(app, client, make_user, monkeypatch):
    uid, username, password = make_user(username="restore-expired", password="password123")

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution) VALUES (?, 'A1', 'isa', 1000, 100)",
                (uid,),
            )
            conn.commit()

    _login(client, username, password)
    export_bytes = _export_json_bytes(client)

    resp_validate = client.post(
        "/settings/restore/validate",
        data={"backup_file": (io.BytesIO(export_bytes), "backup.json")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    token = _extract_restore_token(resp_validate.data.decode("utf-8"))

    with app.app_context():
        import app.routes.settings as s

        now = s.time.time()
        monkeypatch.setattr(s.time, "time", lambda: now + s.RESTORE_STAGING_TTL_SECONDS + 1)

        staged = s._restore_staging_dir() / f"{token}.json"
        assert staged.exists()

    before = _count_user_accounts(app, uid)
    resp_commit = client.post(
        "/settings/restore/commit",
        data={"restore_token": token, "confirm_replace": "1", "confirm_phrase": "RESTORE"},
        follow_redirects=True,
    )
    body = resp_commit.data.decode("utf-8")
    assert "This restore preview has expired. Please upload the backup again." in body
    after = _count_user_accounts(app, uid)
    assert after == before

    with app.app_context():
        import app.routes.settings as s

        staged = s._restore_staging_dir() / f"{token}.json"
        assert not staged.exists()


def test_restore_staging_cleanup_is_scoped_and_removes_expired_files(app, client, make_user):
    uid, username, password = make_user(username="restore-cleanup", password="password123")
    _login(client, username, password)

    with app.app_context():
        import app.routes.settings as s

        staging_dir = s._restore_staging_dir()
        staging_dir.mkdir(parents=True, exist_ok=True)

        expired = staging_dir / "expired-test.json"
        expired.write_bytes(b"{}")
        old = s.time.time() - (s.RESTORE_STAGING_TTL_SECONDS + 10)
        os.utime(expired, (old, old))

        data_dir = staging_dir.parent
        outside = data_dir / "unrelated.txt"
        outside.write_text("keep")
        os.utime(outside, (old, old))

    resp = client.post(
        "/settings/restore/validate",
        data={},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        import app.routes.settings as s

        assert not (s._restore_staging_dir() / "expired-test.json").exists()
        assert (_restore_path := (s._restore_staging_dir().parent / "unrelated.txt")).exists()
        assert _restore_path.read_text() == "keep"


def test_restore_token_is_session_bound(app, make_user):
    uid, username, password = make_user(username="restore-session-bound", password="password123")

    client1 = app.test_client()
    client2 = app.test_client()

    _login(client1, username, password)
    export_bytes = _export_json_bytes(client1)

    resp_validate = client1.post(
        "/settings/restore/validate",
        data={"backup_file": (io.BytesIO(export_bytes), "backup.json")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    token = _extract_restore_token(resp_validate.data.decode("utf-8"))

    _login(client2, username, password)
    before = _count_user_accounts(app, uid)
    resp_commit = client2.post(
        "/settings/restore/commit",
        data={"restore_token": token, "confirm_replace": "1", "confirm_phrase": "RESTORE"},
        follow_redirects=True,
    )
    body = resp_commit.data.decode("utf-8")
    assert "This restore preview has expired. Please upload the backup again." in body
    after = _count_user_accounts(app, uid)
    assert after == before


def test_malformed_restore_token_cannot_access_files(app, client, make_user):
    uid, username, password = make_user(username="restore-malformed-token", password="password123")
    _login(client, username, password)

    resp = client.post(
        "/settings/restore/commit",
        data={"restore_token": "../../etc/passwd", "confirm_replace": "1", "confirm_phrase": "RESTORE"},
        follow_redirects=True,
    )
    body = resp.data.decode("utf-8")
    assert "This restore preview has expired. Please upload the backup again." in body


def test_restore_commit_failure_rolls_back_and_shows_safe_error(app, client, make_user, monkeypatch):
    uid, username, password = make_user(username="restore-fail-safe", password="password123")

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution) VALUES (?, 'A1', 'isa', 1000, 100)",
                (uid,),
            )
            conn.commit()

    _login(client, username, password)
    export_bytes = _export_json_bytes(client)

    resp_validate = client.post(
        "/settings/restore/validate",
        data={"backup_file": (io.BytesIO(export_bytes), "backup.json")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    token = _extract_restore_token(resp_validate.data.decode("utf-8"))

    from app.services import restore_service as rs

    original_insert_row = rs._insert_row
    calls = {"n": 0}

    def _boom(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise sqlite3.IntegrityError("forced")
        return original_insert_row(*args, **kwargs)

    monkeypatch.setattr(rs, "_insert_row", _boom)

    before = _count_user_accounts(app, uid)
    resp = client.post(
        "/settings/restore/commit",
        data={"restore_token": token, "confirm_replace": "1", "confirm_phrase": "RESTORE"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/settings" in resp.headers.get("Location", "")

    page = client.get("/settings/")
    body = page.data.decode("utf-8")
    assert "Restore failed. Your data was not changed." in body
    assert "sqlite3" not in body.lower()
    after = _count_user_accounts(app, uid)
    assert after == before
