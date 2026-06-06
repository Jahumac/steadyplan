import os
import re
import secrets
import time
from pathlib import Path

from app.services.backups import run_pre_restore_backup

RESTORE_STAGING_TTL_SECONDS = 60 * 60
_RESTORE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,}$")


def _data_dir_from_config(config):
    db_path = Path(config["DB_PATH"])
    return Path(config.get("DATA_DIR", db_path.parent))


def restore_staging_dir(config):
    return _data_dir_from_config(config) / "restore_staging"


def restore_staging_path(config, token):
    if not token or not _RESTORE_TOKEN_RE.fullmatch(token):
        return None
    staging_dir = restore_staging_dir(config).resolve()
    path = (staging_dir / f"{token}.json").resolve()
    try:
        path.relative_to(staging_dir)
    except Exception:
        return None
    return path


def create_pre_restore_backup(config):
    db_path = Path(config["DB_PATH"])
    data_dir = _data_dir_from_config(config)
    return run_pre_restore_backup(db_path, data_dir)


def cleanup_restore_staging(config, *, now_ts=None):
    now_ts = float(now_ts if now_ts is not None else time.time())
    staging_dir = restore_staging_dir(config)
    try:
        if not staging_dir.exists():
            return 0
        staging_dir_resolved = staging_dir.resolve()
        deleted = 0
        for path in staging_dir.glob("*.json"):
            try:
                if path.is_symlink() or not path.is_file():
                    continue
                resolved_path = path.resolve()
                resolved_path.relative_to(staging_dir_resolved)
                age = now_ts - resolved_path.stat().st_mtime
                if age >= RESTORE_STAGING_TTL_SECONDS:
                    resolved_path.unlink()
                    deleted += 1
            except Exception:
                continue
        return deleted
    except Exception:
        return 0


def delete_staged_restore_file(config, token, *, logger=None):
    if not token:
        return
    try:
        path = restore_staging_path(config, token)
        if path and path.exists():
            path.unlink()
    except Exception:
        if logger is not None:
            logger.exception("Failed to delete staged restore file")


def stage_restore_file(config, json_bytes):
    staging_dir = restore_staging_dir(config)
    staging_dir.mkdir(parents=True, exist_ok=True)
    now_ts = time.time()
    for _ in range(5):
        token = secrets.token_urlsafe(24)
        path = restore_staging_path(config, token)
        if not path:
            continue
        try:
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(json_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.utime(path, (now_ts, now_ts))
            except Exception:
                pass
            return token
        except FileExistsError:
            continue
    raise RuntimeError("Failed to stage restore file.")


def read_staged_restore_file(config, token):
    if not token:
        return None
    path = restore_staging_path(config, token)
    if not path:
        return None
    try:
        return path.read_bytes()
    except Exception:
        return None


def is_staged_restore_expired(config, token, staged_at_ts, *, now_ts=None):
    now_ts = float(now_ts if now_ts is not None else time.time())
    try:
        staged_at_ts = float(staged_at_ts)
    except Exception:
        return True
    if now_ts - staged_at_ts >= RESTORE_STAGING_TTL_SECONDS:
        return True
    path = restore_staging_path(config, token)
    if not path or not path.exists():
        return True
    try:
        age = now_ts - path.stat().st_mtime
        return age >= RESTORE_STAGING_TTL_SECONDS
    except Exception:
        return True
