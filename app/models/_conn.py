"""Database connection handling — the leaf module of the models package.

Kept separate so schema.py and every other submodule can import
get_connection without creating a cycle with __init__.py.
"""
import sqlite3
from os import W_OK, access
from pathlib import Path

from flask import current_app, g


def get_connection():
    if "db" not in g:
        db_path = Path(current_app.config["DB_PATH"])
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if db_path.exists():
            if not access(db_path, W_OK):
                raise sqlite3.OperationalError(
                    f"Database file is not writable: {db_path}. Ensure the file and its directory are writable."
                )
        else:
            if not access(db_path.parent, W_OK):
                raise sqlite3.OperationalError(
                    f"Database directory is not writable: {db_path.parent}. Ensure the directory is writable."
                )
        conn = sqlite3.connect(db_path, timeout=5.0)
        conn.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError as e:
            raise sqlite3.OperationalError(f"Could not enable SQLite WAL mode for {db_path}: {e}") from e
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        g.db = conn
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()
