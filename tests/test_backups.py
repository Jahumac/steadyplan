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
    assert "None yet" in body


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
    assert "Backup created:" in body
    # Do not leak full server paths in UI
    assert str(tmp_path) not in body


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
