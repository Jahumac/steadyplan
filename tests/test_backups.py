"""Backup service tests."""
from datetime import datetime
from pathlib import Path


def test_backup_creates_file(app, tmp_path):
    from app.services.backups import run_backup

    with app.app_context():
        db_path = Path(app.config["DB_PATH"])
        # Write something so we can verify the copy has it
        from app.models import create_user
        create_user("backup-test-user", "password123")

    dest = run_backup(db_path, tmp_path)
    assert dest.exists()
    assert dest.stat().st_size > 0


def test_backup_directory_and_file_are_private(app, tmp_path):
    from app.services.backups import run_backup

    with app.app_context():
        db_path = Path(app.config["DB_PATH"])
        from app.models import create_user
        create_user("backup-private-user", "password123")

    dest = run_backup(db_path, tmp_path)
    backup_dir = tmp_path / "backups"

    assert backup_dir.stat().st_mode & 0o777 == 0o700
    assert dest.stat().st_mode & 0o777 == 0o600


def test_backup_is_a_readable_sqlite_db(app, tmp_path):
    import sqlite3

    from app.services.backups import run_backup

    with app.app_context():
        db_path = Path(app.config["DB_PATH"])
        from app.models import create_user
        create_user("verify-user", "password123")

    dest = run_backup(db_path, tmp_path)
    conn = sqlite3.connect(str(dest))
    users = [r[0] for r in conn.execute("SELECT username FROM users").fetchall()]
    conn.close()
    assert "verify-user" in users


def test_pre_restore_backup_is_unique_and_keeps_daily_backup(app, tmp_path):
    from app.services.backups import run_backup, run_pre_restore_backup

    with app.app_context():
        db_path = Path(app.config["DB_PATH"])
        from app.models import create_user
        create_user("pre-restore-unique-user", "password123")

    daily = run_backup(db_path, tmp_path)
    pre_restore_1 = run_pre_restore_backup(db_path, tmp_path, now=datetime(2026, 6, 4, 12, 0, 0, 123456))
    pre_restore_2 = run_pre_restore_backup(db_path, tmp_path, now=datetime(2026, 6, 4, 12, 0, 1, 123456))

    assert daily.name.startswith("finance-")
    assert not daily.name.startswith("finance-pre-restore-")
    assert daily.exists()
    assert pre_restore_1.exists()
    assert pre_restore_2.exists()
    assert pre_restore_1.name.startswith("finance-pre-restore-")
    assert pre_restore_2.name.startswith("finance-pre-restore-")
    assert pre_restore_1 != pre_restore_2

    names = sorted(p.name for p in (tmp_path / "backups").glob("finance*.db") if not p.is_symlink())
    assert daily.name in names
    assert pre_restore_1.name in names
    assert pre_restore_2.name in names


def test_backup_rotation_keeps_last_n(app, tmp_path):
    """Simulate 35 daily backups, retention=30, verify only last 30 remain."""
    from app.services.backups import _prune_old_backups

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    # Create 35 fake backup files, oldest first
    for i in range(35):
        day = (datetime(2026, 1, 1).toordinal() + i)
        d = datetime.fromordinal(day)
        (backup_dir / f"finance-{d.strftime('%Y-%m-%d')}.db").write_text("x")

    _prune_old_backups(backup_dir, retention_days=30)
    remaining = sorted(p.name for p in backup_dir.glob("finance-*.db"))
    assert len(remaining) == 30
    # Oldest 5 should be gone
    assert "finance-2026-01-01.db" not in remaining
    assert "finance-2026-02-04.db" in remaining


def test_list_backups_returns_empty_when_no_dir(tmp_path):
    from app.services.backups import list_backups

    assert list_backups(tmp_path) == []


def test_diagnostics_renders_backup_panel_when_no_backups_exist(app, client, make_user, tmp_path):
    app.config["DATA_DIR"] = tmp_path
    uid, username, password = make_user(username="diag-admin", is_admin=True)
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/settings/?mode=diagnostics")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "SQLite backups" in body
    assert "Backup health" in body
    assert "No whole-instance SQLite backup found." in body
    assert "None yet" in body
    assert "whole-instance SQLite backups" in body
    assert "data/backups" in body
    assert "finance.db" in body
    assert "secret_key.txt" in body


def test_diagnostics_renders_default_trust_posture_checkpoint(app, client, make_user, tmp_path):
    app.config.update(
        DATA_DIR=tmp_path,
        IS_PRODUCTION=False,
        SESSION_COOKIE_SECURE=False,
        REMEMBER_COOKIE_SECURE=False,
        TRUST_PROXY_HEADERS=False,
        DEMO_PUBLIC_LOGIN_ENABLED=False,
        WEB_CONCURRENCY=1,
        RATELIMIT_STORAGE_URI="memory://",
        RATELIMIT_STORAGE_WARNING=None,
    )
    uid, username, password = make_user(username="trust-admin-default", is_admin=True)
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/settings/?mode=diagnostics")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Trust posture checkpoint" in body
    assert "Local/demo posture" in body
    assert "This instance looks deliberate for local evaluation or read-only demo use." in body
    assert "App mode" in body
    assert "Development/local" in body
    assert "Local/demo posture — Local/development mode is active." in body
    assert "Secure cookies" in body
    assert "Local/demo posture — Secure cookies are off. That is normal on local HTTP, but turn them on behind HTTPS." in body
    assert "Trusted proxy headers" in body
    assert "OK — Forwarded proxy headers are ignored unless you explicitly opt in." in body
    assert "Public demo login" in body
    assert "OK — Public demo login is off. Real accounts still require normal login." in body
    assert "Rate-limit storage" in body
    assert "OK — Process-local memory storage is fine with a single worker." in body
    assert '<p class="eyebrow">Runtime checks</p>' in body
    assert "<h3>Instance overview</h3>" in body
    assert '<p class="eyebrow">Data footprint</p>' in body
    assert "<h3>Instance counts</h3>" in body
    assert '<p class="eyebrow">Prices in use</p>' in body
    assert "<h3>Linked price sample</h3>" in body
    assert "Scheduler last run" in body
    assert "Not yet recorded" in body
    assert "No scheduler run has been recorded yet. That is normal on a fresh instance or when you mainly update prices and balances manually." in body
    assert '<p class="eyebrow">Status</p>' not in body
    assert "<h3>Overview</h3>" not in body
    assert '<p class="eyebrow">Counts</p>' not in body
    assert "<h3>Data</h3>" not in body
    assert '<p class="eyebrow">Prices</p>' not in body
    assert "<h3>Latest Instruments</h3>" not in body


def test_diagnostics_warns_when_trust_posture_needs_review(app, client, make_user, tmp_path):
    app.config.update(
        DATA_DIR=tmp_path,
        IS_PRODUCTION=True,
        SESSION_COOKIE_SECURE=False,
        REMEMBER_COOKIE_SECURE=False,
        TRUST_PROXY_HEADERS=True,
        DEMO_PUBLIC_LOGIN_ENABLED=True,
        WEB_CONCURRENCY=2,
        RATELIMIT_STORAGE_URI="memory://",
        RATELIMIT_STORAGE_WARNING=(
            "RATELIMIT_STORAGE_URI=memory:// is process-local. With multiple Gunicorn workers, login/API rate limits are tracked separately per worker. Set WEB_CONCURRENCY=1 or use shared storage such as Redis."
        ),
    )
    uid, username, password = make_user(username="trust-admin-warning", is_admin=True)
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/settings/?mode=diagnostics")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Trust posture checkpoint" in body
    assert "Review recommended" in body
    assert "One or more settings need review before treating this as a polished public deployment." in body
    assert "Production" in body
    assert "Review recommended — Secure cookies are off while production mode is on. Turn them on behind HTTPS." in body
    assert "Deliberate public/proxy — SteadyPlan trusts forwarded proxy headers. Only leave this on behind a trusted reverse proxy or tunnel." in body
    assert "Deliberate public demo — Public read-only demo login is enabled. Keep it demo-data-only and treat it as an explicit host choice." in body
    assert "Review recommended — RATELIMIT_STORAGE_URI=memory:// is process-local." in body


def test_admin_can_run_manual_backup_from_settings(app, client, make_user, tmp_path):
    app.config["DATA_DIR"] = tmp_path
    uid, username, password = make_user(username="backup-admin", is_admin=True)
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.post("/settings/backups/run", data={}, follow_redirects=True)
    assert resp.status_code == 200
    backups = sorted((tmp_path / "backups").glob("finance-*.db"))
    backups = [p for p in backups if not p.is_symlink()]
    assert backups
    body = resp.data.decode("utf-8", errors="ignore")
    assert "SQLite backup created:" in body
    # Do not leak full server paths in UI
    assert str(tmp_path) not in body


def test_admin_manual_backup_safe_next_redirects_locally(app, client, make_user, tmp_path):
    app.config["DATA_DIR"] = tmp_path
    uid, username, password = make_user(username="backup-admin-next", is_admin=True)
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.post("/settings/backups/run", data={"next": "/settings/#danger-zone"}, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers.get("Location") == "/settings/#danger-zone"
    backups = sorted((tmp_path / "backups").glob("finance-*.db"))
    backups = [p for p in backups if not p.is_symlink()]
    assert backups


def test_admin_manual_backup_rejects_external_next(app, client, make_user, tmp_path):
    app.config["DATA_DIR"] = tmp_path
    uid, username, password = make_user(username="backup-admin-badnext", is_admin=True)
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.post("/settings/backups/run", data={"next": "https://example.com/phish"}, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers.get("Location", "").endswith("/settings/?mode=diagnostics")


def test_admin_manual_backup_rejects_protocol_relative_next(app, client, make_user, tmp_path):
    app.config["DATA_DIR"] = tmp_path
    uid, username, password = make_user(username="backup-admin-badnext2", is_admin=True)
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.post("/settings/backups/run", data={"next": "//example.com/phish"}, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers.get("Location", "").endswith("/settings/?mode=diagnostics")


def test_non_admin_cannot_run_manual_backup(app, client, make_user, tmp_path):
    app.config["DATA_DIR"] = tmp_path
    uid, username, password = make_user(username="backup-nonadmin", is_admin=False)
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.post("/settings/backups/run", data={}, follow_redirects=True)
    assert resp.status_code == 200
    backup_dir = tmp_path / "backups"
    assert not backup_dir.exists()
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Admin only" in body


def test_diagnostics_shows_latest_backup_metadata(app, client, make_user, tmp_path):
    from app.services.backups import run_backup
    from pathlib import Path

    app.config["DATA_DIR"] = tmp_path
    with app.app_context():
        db_path = Path(app.config["DB_PATH"])
        dest = run_backup(db_path, tmp_path)

    uid, username, password = make_user(username="diag-admin-2", is_admin=True)
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/settings/?mode=diagnostics")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert dest.name in body
    assert "Latest size" in body
    assert str(dest) not in body


def test_backup_health_is_good_for_recent_backup(app, client, make_user, tmp_path):
    import os
    import time

    app.config["DATA_DIR"] = tmp_path
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    p = backup_dir / "finance-2026-05-01.db"
    p.write_text("x")
    now = time.time()
    os.utime(p, (now, now))

    uid, username, password = make_user(username="diag-admin-recent", is_admin=True)
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    resp = client.get("/settings/?mode=diagnostics")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Backup health:" in body
    assert "OK — latest whole-instance SQLite backup is" in body


def test_backup_health_warns_when_backup_is_old(app, client, make_user, tmp_path):
    import os
    import time

    app.config["DATA_DIR"] = tmp_path
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    p = backup_dir / "finance-2026-05-01.db"
    p.write_text("x")
    old = time.time() - (10 * 24 * 60 * 60)
    os.utime(p, (old, old))

    uid, username, password = make_user(username="diag-admin-old", is_admin=True)
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    resp = client.get("/settings/?mode=diagnostics")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Backup health" in body
    assert "Latest whole-instance SQLite backup is" in body
    assert "days old." in body
