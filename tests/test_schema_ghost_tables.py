"""Ghost *_new table cleanup (migration v12_drop_ghost_tables).

Table-swap migrations create ``{table}_new``, copy, drop the original and
rename. If the copy fails part-way the ``_new`` table survives as orphan
residue: no code reads it, but the DB then holds two candidate answers to
questions like "what accounts exist". These tests pin the forward-only cleanup.
"""
from contextlib import contextmanager

from app.models.schema import init_db
from app.models._conn import get_connection

GHOST = "accounts_new"
MIGRATION = "v12_drop_ghost_tables"


@contextmanager
def _ctx(app):
    with app.app_context():
        yield


def _table_names(app):
    with app.app_context():
        with get_connection() as conn:
            return {
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }


def _migration_recorded(app, name=MIGRATION):
    with app.app_context():
        with get_connection() as conn:
            return conn.execute(
                "SELECT 1 FROM schema_migrations WHERE name = ?", (name,)
            ).fetchone() is not None


def test_fresh_database_has_no_ghost_tables(app):
    names = _table_names(app)
    ghosts = sorted(n for n in names if n.endswith("_new"))
    assert ghosts == []
    assert _migration_recorded(app)


def test_ghost_table_residue_is_dropped_on_migration(app):
    # Simulate the residue a failed v7-style swap leaves behind.
    with app.app_context():
        with get_connection() as conn:
            conn.execute(f"CREATE TABLE {GHOST} (id INTEGER PRIMARY KEY, name TEXT)")
            conn.execute(f"INSERT INTO {GHOST} (name) VALUES ('stale leftover')")
            conn.execute(f"DELETE FROM schema_migrations WHERE name = '{MIGRATION}'")
            conn.commit()
    assert GHOST in _table_names(app)

    with app.app_context():
        init_db()

    assert GHOST not in _table_names(app)
    assert _migration_recorded(app)


def test_ghost_cleanup_does_not_touch_real_tables(app):
    with app.app_context():
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 0)",
                ("ghost-guard", "x"),
            )
            conn.commit()

    before = _table_names(app)
    with app.app_context():
        init_db()  # already migrated — must be a no-op
    after = _table_names(app)

    assert before == after
    assert not any(n.endswith("_new") for n in after)
    with app.app_context():
        with get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM users WHERE username = 'ghost-guard'"
            ).fetchone()
    assert row["n"] == 1
