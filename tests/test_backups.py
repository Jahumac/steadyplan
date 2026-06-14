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
    assert "SQLite backup files" in body
    assert "Backup health" in body
    assert "Backup recommended" in body
    assert "Needs backup" not in body
    assert "No whole-instance SQLite backup found." in body
    assert "No SQLite backup yet" in body
    assert "No backup yet" not in body
    assert "None yet" not in body
    assert "whole-instance SQLite backups" in body
    assert "data/backups" in body
    assert "finance.db" in body
    assert "secret_key.txt" in body
    assert "For per-user exports, use Settings → Download this user's JSON export." in body
    assert "For per-user exports, use Settings → Download JSON export." not in body


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
    assert "This instance looks set up for local evaluation or read-only demo use." in body
    assert "This instance looks deliberate for local evaluation or read-only demo use." not in body
    assert "Instance mode" in body
    assert "<td>App mode</td>" not in body
    assert "Local/development" in body
    assert "Development/local" not in body
    assert "Local/demo posture — Local/development mode is on. Fine for LAN/VPN checks, but review production settings before exposing SteadyPlan publicly." in body
    assert "Local/demo posture — Local/development mode is active. Fine for LAN/VPN evaluation, but review production settings before exposing SteadyPlan publicly." not in body
    assert "Cookie security" in body
    assert "<td>Secure cookies</td>" not in body
    assert "Local/demo posture — Secure cookies are off. That is normal on local HTTP, but turn them on behind HTTPS." in body
    assert "Forwarded proxy headers" in body
    assert "Trusted proxy headers" not in body
    assert "<td class=\"num\">Off by default</td>" in body
    assert "<td class=\"num\">Ignored by default</td>" not in body
    assert "OK — Forwarded proxy headers stay off unless you explicitly opt in." in body
    assert "OK — Forwarded proxy headers are ignored unless you explicitly opt in." not in body
    assert "Public read-only demo" in body
    assert "<td>Public demo login</td>" not in body
    assert "OK — Public read-only demo is off. Real accounts still require normal login." in body
    assert "OK — Public demo login is off. Real accounts still require normal login." not in body
    assert "Rate limit storage" in body
    assert "Rate-limit storage" not in body
    assert "<td class=\"num\">Single-worker memory</td>" in body
    assert "<td class=\"num\">Process-local memory</td>" not in body
    assert "OK — Single-worker memory is fine with one worker." in body
    assert "OK — Process-local memory storage is fine with a single worker." not in body
    assert '<p class="eyebrow">Runtime checks</p>' in body
    assert "<h3>Instance overview</h3>" in body
    assert "<td class=\"num\">Reachable</td>" in body
    assert "<td class=\"num\">Available</td>" not in body
    assert "Needs attention" not in body
    assert '<p class="eyebrow">Data in this instance</p>' in body
    assert "<h3>Instance counts</h3>" in body
    assert '<p class="eyebrow">Linked prices</p>' in body
    assert "<h3>Sample of linked prices</h3>" in body
    assert "No linked holdings are using saved prices yet." in body
    assert "Linked prices needing attention in sample (&gt;2 days old or missing)" in body
    assert "No holdings with catalogue links yet." not in body
    assert "Stale prices (sample, &gt;2d/none)" not in body
    assert "No holdings are linked to saved prices yet." not in body
    assert "Stale or missing linked prices in sample (&gt;2 days old or none)" not in body
    assert "Scheduler last run" in body
    assert "Latest saved portfolio snapshot" in body
    assert "Latest portfolio snapshot" not in body
    assert "Latest saved price update" in body
    assert "Latest price update (raw)" not in body
    assert "Saved daily snapshots" in body
    assert ">Daily snapshots<" not in body
    assert "Saved prices" in body
    assert "Saved prices linked to holdings" in body
    assert "Saved portfolio daily snapshots" in body
    assert '<tr><td>Portfolio daily snapshots</td><td class="num">{{ diagnostics.counts.portfolio_daily_snapshots if diagnostics and diagnostics.counts else 0 }}</td></tr>' not in body
    assert "Catalogue active" not in body
    assert "Catalogue in use" not in body
    assert "Active price catalogue entries" not in body
    assert "Price catalogue entries linked to holdings" not in body
    assert "No scheduler run yet" in body
    assert "No run recorded yet" not in body
    assert "No scheduler run has been recorded yet. That is normal on a fresh instance or when you mainly update prices and balances manually." in body
    assert "Not yet recorded" not in body
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
    assert "One or more settings need review before relying on this for public use." in body
    assert "One or more settings need review before relying on this as a polished public deployment." not in body
    assert "One or more settings need review before treating this as a polished public deployment." not in body
    assert "Production" in body
    assert "Review recommended — Secure cookies are off while production mode is on. Turn them on behind HTTPS." in body
    assert "<td class=\"num\">Enabled</td>" in body
    assert "<td class=\"num\">Ignored by default</td>" not in body
    assert "Proxy headers enabled — Forwarded proxy headers are trusted. Only leave this on behind a trusted reverse proxy or tunnel." in body
    assert "Proxy headers enabled — SteadyPlan trusts forwarded proxy headers. Only leave this on behind a trusted reverse proxy or tunnel." not in body
    assert "Public demo enabled — Public read-only demo is enabled. Keep it demo-data-only and treat it as an explicit host choice." in body
    assert "Public demo enabled — Public read-only demo login is enabled. Keep it demo-data-only and treat it as an explicit host choice." not in body
    assert "Deliberate public/proxy" not in body
    assert "Deliberate public demo" not in body
    assert "Review recommended — RATELIMIT_STORAGE_URI=memory:// is process-local." in body


def test_diagnostics_renders_ok_public_trust_posture_message(app, client, make_user, tmp_path):
    app.config.update(
        DATA_DIR=tmp_path,
        IS_PRODUCTION=True,
        SESSION_COOKIE_SECURE=True,
        REMEMBER_COOKIE_SECURE=True,
        TRUST_PROXY_HEADERS=False,
        DEMO_PUBLIC_LOGIN_ENABLED=False,
        WEB_CONCURRENCY=1,
        RATELIMIT_STORAGE_URI="memory://",
        RATELIMIT_STORAGE_WARNING=None,
    )
    uid, username, password = make_user(username="trust-admin-ok", is_admin=True)
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/settings/?mode=diagnostics")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Trust posture checkpoint" in body
    assert "Basic public-facing settings look in place for this trust checkpoint." in body
    assert "Production-ready basics look in place for this trust checkpoint." not in body
    assert "OK — Production mode is on. Keep HTTPS and secure cookies on for real use." in body
    assert "OK — Production mode is on. Pair this with HTTPS and secure cookies for real use." not in body
    assert "OK — Secure cookies are on for sessions and remembered logins." in body
    assert "OK — Secure session and remember cookies are on." not in body
    assert "Review recommended" not in body


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
    assert "SQLite backup files" in body
    assert "Latest SQLite backup" in body
    assert "Latest SQLite backup size" in body
    assert "Backup files" not in body
    assert "Latest backup</td>" not in body
    assert "Latest backup size" not in body
    assert "Latest size" not in body
    assert str(dest) not in body


def test_diagnostics_price_sample_template_uses_clearer_column_labels():
    from pathlib import Path

    body = Path("/opt/data/steadyplan/app/templates/settings.html").read_text()

    assert "<th>Holding name</th>" in body
    assert "<th>Price updated</th>" in body
    assert '<th class="num">Linked holdings</th>' in body
    assert "<th>Holding</th>" not in body
    assert "<th>Updated</th>" not in body
    assert '<th class="num">Linked</th>' not in body


def test_diagnostics_instance_counts_template_uses_clearer_stale_price_label():
    from pathlib import Path

    body = Path("/opt/data/steadyplan/app/templates/settings.html").read_text()

    assert "Linked prices needing attention in sample (&gt;2 days old or missing)" in body
    assert "Stale prices (sample, &gt;2d/none)" not in body
    assert "Stale or missing linked prices in sample (&gt;2 days old or none)" not in body


def test_diagnostics_linked_prices_empty_state_uses_clearer_saved_prices_wording():
    from pathlib import Path

    body = Path("/opt/data/steadyplan/app/templates/settings.html").read_text()

    assert "No linked holdings are using saved prices yet." in body
    assert "No holdings are linked to saved prices yet." not in body


def test_diagnostics_instance_overview_template_uses_clearer_price_update_label():
    from pathlib import Path

    body = Path("/opt/data/steadyplan/app/templates/settings.html").read_text()

    assert "Latest saved portfolio snapshot" in body
    assert "Latest portfolio snapshot" not in body
    assert "Latest saved price update" in body
    assert "Latest price update (raw)" not in body
    assert "Latest catalogue price update" not in body


def test_diagnostics_instance_counts_template_uses_clearer_catalogue_count_labels():
    from pathlib import Path

    body = Path("/opt/data/steadyplan/app/templates/settings.html").read_text()

    assert "Saved daily snapshots" in body
    assert "hero_stat('Daily snapshots')" not in body
    assert "Saved prices" in body
    assert "Saved prices linked to holdings" in body
    assert "Saved portfolio daily snapshots" in body
    assert '<tr><td>Portfolio daily snapshots</td><td class="num">{{ diagnostics.counts.portfolio_daily_snapshots if diagnostics and diagnostics.counts else 0 }}</td></tr>' not in body
    assert "Catalogue active" not in body
    assert "Catalogue in use" not in body
    assert "Active price catalogue entries" not in body
    assert "Price catalogue entries linked to holdings" not in body


def test_diagnostics_backup_metadata_template_uses_clearer_backup_labels():
    from pathlib import Path

    body = Path("/opt/data/steadyplan/app/templates/settings.html").read_text()

    assert "SQLite backup files" in body
    assert "Latest SQLite backup" in body
    assert "Latest SQLite backup saved at" in body
    assert "Latest SQLite backup size" in body
    assert "Backup files" not in body
    assert "Latest backup</td>" not in body
    assert "Latest backup saved at" not in body
    assert "Latest backup size" not in body
    assert "Latest modified" not in body
    assert "Latest size" not in body


def test_diagnostics_runtime_status_template_uses_clearer_state_labels():
    from pathlib import Path

    body = Path("/opt/data/steadyplan/app/templates/settings.html").read_text()

    assert "Reachable" in body
    assert "Available" not in body
    assert "Needs attention" in body
    assert "No scheduler run yet" in body
    assert "No run yet" not in body
    assert "No SQLite backup yet" in body
    assert "No backup yet" not in body
    assert "Backup recommended" in body
    assert "Needs backup" not in body
    assert ">OK<" not in body
    assert ">Error<" not in body
    assert "Not yet recorded" not in body
    assert "None yet" not in body


def test_diagnostics_trust_checkpoint_copy_uses_clearer_setup_wording():
    from pathlib import Path

    body = Path("/opt/data/steadyplan/app/templates/settings.html").read_text()

    assert "Live runtime checks for the main trust-related settings on this instance." in body
    assert "This is not a full security audit, but it should make the current setup easier to review." in body
    assert "Live runtime checks for the main trust settings on this instance." not in body
    assert "it should make the current posture easier to review." not in body


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
    assert "Backup recommended" in body
    assert "Needs backup" not in body
    assert "Latest whole-instance SQLite backup is" in body
    assert "days old." in body
