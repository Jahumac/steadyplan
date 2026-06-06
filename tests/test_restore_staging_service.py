import os

from app.services.restore_staging import (
    RESTORE_STAGING_TTL_SECONDS,
    cleanup_restore_staging,
    is_staged_restore_expired,
    read_staged_restore_file,
    restore_staging_dir,
    restore_staging_path,
    stage_restore_file,
)


def test_restore_staging_path_requires_safe_token(app):
    with app.app_context():
        assert restore_staging_path(app.config, "../../etc/passwd") is None
        assert restore_staging_path(app.config, "short") is None

        token = "A" * 24
        expected = restore_staging_dir(app.config) / f"{token}.json"
        assert restore_staging_path(app.config, token) == expected.resolve()



def test_stage_and_read_restore_file_round_trip(app):
    payload = b'{"ok": true}'

    with app.app_context():
        token = stage_restore_file(app.config, payload)
        staged_path = restore_staging_dir(app.config) / f"{token}.json"

        assert staged_path.exists()
        assert read_staged_restore_file(app.config, token) == payload
        assert oct(staged_path.stat().st_mode & 0o777) == "0o600"



def test_restore_staging_expiry_and_cleanup_are_scoped(app):
    with app.app_context():
        staging_dir = restore_staging_dir(app.config)
        staging_dir.mkdir(parents=True, exist_ok=True)

        expired_token = "B" * 24
        fresh_token = "C" * 24
        expired_path = staging_dir / f"{expired_token}.json"
        fresh_path = staging_dir / f"{fresh_token}.json"
        outside = staging_dir.parent / "outside.txt"

        expired_path.write_bytes(b"{}")
        fresh_path.write_bytes(b"{}")
        outside.write_text("keep")

        now_ts = 1_700_000_000
        old_ts = now_ts - (RESTORE_STAGING_TTL_SECONDS + 5)
        fresh_ts = now_ts - 5
        os.utime(expired_path, (old_ts, old_ts))
        os.utime(fresh_path, (fresh_ts, fresh_ts))
        os.utime(outside, (old_ts, old_ts))

        assert is_staged_restore_expired(app.config, expired_token, old_ts, now_ts=now_ts) is True
        assert is_staged_restore_expired(app.config, fresh_token, fresh_ts, now_ts=now_ts) is False

        deleted = cleanup_restore_staging(app.config, now_ts=now_ts)
        assert deleted == 1
        assert not expired_path.exists()
        assert fresh_path.exists()
        assert outside.exists()
        assert outside.read_text() == "keep"
