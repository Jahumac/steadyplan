"""Automatic SQLite backups.

Uses the sqlite3 `.backup()` API which is safe on a live DB (no need to stop
the app). Rotates to keep configurable daily snapshots and separate unique
pre-restore rollback snapshots.

Layout:
    data/backups/finance-YYYY-MM-DD.db                               ← one per day
    data/backups/finance-pre-restore-YYYY-MM-DDTHH-MM-SS-ffffff.db  ← unique restore rollback point
    data/backups/finance-latest.db                                   ← symlink to newest (if supported)
"""
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 30
DAILY_BACKUP_GLOB = "finance-????-??-??.db"
PRE_RESTORE_BACKUP_GLOB = "finance-pre-restore-*.db"


def backup_path_for(data_dir: Path, today: datetime | None = None) -> Path:
    today = today or datetime.now()
    return data_dir / "backups" / f"finance-{today.strftime('%Y-%m-%d')}.db"


def pre_restore_backup_path_for(data_dir: Path, now: datetime | None = None) -> Path:
    now = now or datetime.now()
    stamp = now.strftime("%Y-%m-%dT%H-%M-%S-%f")
    return data_dir / "backups" / f"finance-pre-restore-{stamp}.db"


def _ensure_backup_dir(data_dir: Path) -> Path:
    backup_dir = data_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(backup_dir, 0o700)
    except OSError as e:
        logger.warning(f"Failed to secure backup directory permissions for {backup_dir}: {e}")
    return backup_dir


def _write_backup_copy(db_path: Path, dest: Path) -> Path:
    tmp = dest.with_suffix(".db.tmp")

    src = sqlite3.connect(str(db_path))
    try:
        dst = sqlite3.connect(str(tmp))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()

    # Atomic rename so a half-written file never appears as a backup.
    os.replace(tmp, dest)
    try:
        os.chmod(dest, 0o600)
    except OSError as e:
        logger.warning(f"Failed to secure backup file permissions for {dest}: {e}")
    return dest


def run_backup(db_path: Path, data_dir: Path, retention_days: int = DEFAULT_RETENTION_DAYS) -> Path:
    """Create a daily backup and prune old ones. Returns the backup path.

    Safe to call on a live DB — uses SQLite's online backup API.
    Idempotent within a single day: re-running overwrites today's file.
    """
    backup_dir = _ensure_backup_dir(data_dir)
    dest = backup_path_for(data_dir)
    _write_backup_copy(db_path, dest)

    _prune_old_backups(backup_dir, retention_days, pattern=DAILY_BACKUP_GLOB)
    _update_latest_symlink(backup_dir, dest)

    size_mb = dest.stat().st_size / (1024 * 1024)
    logger.info(f"Backup written: {dest.name} ({size_mb:.2f} MB)")
    return dest


def run_pre_restore_backup(
    db_path: Path,
    data_dir: Path,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    now: datetime | None = None,
) -> Path:
    """Create a unique rollback backup before restore overwrites any user data."""
    backup_dir = _ensure_backup_dir(data_dir)
    dest = pre_restore_backup_path_for(data_dir, now=now)
    _write_backup_copy(db_path, dest)

    _prune_old_backups(backup_dir, retention_days, pattern=PRE_RESTORE_BACKUP_GLOB)
    _update_latest_symlink(backup_dir, dest)

    size_mb = dest.stat().st_size / (1024 * 1024)
    logger.info(f"Pre-restore backup written: {dest.name} ({size_mb:.2f} MB)")
    return dest


def _prune_old_backups(backup_dir: Path, retention_days: int, *, pattern: str = DAILY_BACKUP_GLOB) -> None:
    candidates = sorted(backup_dir.glob(pattern))
    # Exclude the symlink itself
    candidates = [p for p in candidates if not p.is_symlink() and p.name != "finance-latest.db"]
    if len(candidates) <= retention_days:
        return
    for old in candidates[:-retention_days]:
        try:
            old.unlink()
            logger.info(f"Pruned old backup: {old.name}")
        except OSError as e:
            logger.warning(f"Failed to prune {old}: {e}")


def _update_latest_symlink(backup_dir: Path, newest: Path) -> None:
    link = backup_dir / "finance-latest.db"
    try:
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(newest.name)
    except (OSError, NotImplementedError):
        # Symlinks not supported (e.g. Windows without dev mode). Not fatal.
        pass


def list_backups(data_dir: Path) -> list[dict]:
    backup_dir = data_dir / "backups"
    if not backup_dir.exists():
        return []
    out = []
    for p in sorted(backup_dir.glob("finance*.db")):
        if p.is_symlink():
            continue
        stat = p.stat()
        out.append({
            "name": p.name,
            "path": str(p),
            "size_bytes": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return out
