import importlib
import os
import sqlite3
import tempfile
from pathlib import Path


def test_create_app_raises_clear_error_when_db_file_not_writable(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="steadyplan-test-ro-db-")
    db_path = Path(tmpdir) / "finance.db"
    db_path.write_bytes(b"")
    os.chmod(db_path, 0o400)

    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-not-for-prod")
    monkeypatch.setenv("WTF_CSRF_ENABLED", "0")
    monkeypatch.setenv("FLASK_TESTING", "1")

    import app as app_pkg
    import app.config as cfg
    importlib.reload(cfg)
    importlib.reload(app_pkg)

    try:
        app_pkg.create_app()
        assert False, "Expected OperationalError for read-only DB"
    except sqlite3.OperationalError as e:
        assert "not writable" in str(e).lower()

