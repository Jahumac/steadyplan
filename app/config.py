import os
import secrets
from pathlib import Path


def _env_flag(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _app_env():
    return os.environ.get("APP_ENV", os.environ.get("FLASK_ENV", "development")).strip().lower()


def _env_int(name, default):
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _ratelimit_storage_warning(storage_uri, worker_count):
    if (storage_uri or "").strip().lower() == "memory://" and worker_count > 1:
        return (
            "RATELIMIT_STORAGE_URI=memory:// is process-local. With multiple "
            "Gunicorn workers, login/API rate limits are tracked separately per "
            "worker. Set WEB_CONCURRENCY=1 or use shared storage such as Redis."
        )
    return None


def _load_or_create_secret_key():
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    key_file = Path(__file__).resolve().parent.parent / "data" / "secret_key.txt"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    if key_file.exists():
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
        return key_file.read_text().strip()
    key = secrets.token_hex(32)
    key_file.write_text(key)
    try:
        os.chmod(key_file, 0o600)
    except OSError:
        pass
    return key


class Config:
    BASE_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = BASE_DIR / "data"
    DB_PATH = Path(os.environ["DB_PATH"]) if os.environ.get("DB_PATH") else DATA_DIR / "finance.db"
    SECRET_KEY = _load_or_create_secret_key()
    APP_ENV = _app_env()
    IS_PRODUCTION = APP_ENV in {"production", "prod"}
    SESSION_COOKIE_SECURE = _env_flag("SESSION_COOKIE_SECURE", default=IS_PRODUCTION)
    REMEMBER_COOKIE_SECURE = _env_flag("REMEMBER_COOKIE_SECURE", default=IS_PRODUCTION)
    DEMO_READ_ONLY_USERNAME = os.environ.get("DEMO_READ_ONLY_USERNAME", "demo")
    DEMO_PUBLIC_LOGIN_ENABLED = os.environ.get("DEMO_PUBLIC_LOGIN_ENABLED", "0") == "1"
    WTF_CSRF_ENABLED = os.environ.get("WTF_CSRF_ENABLED", "1") != "0"
    TESTING = os.environ.get("FLASK_TESTING", "0") == "1"
    TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY")
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    WEB_CONCURRENCY = _env_int("WEB_CONCURRENCY", 1)
    RATELIMIT_STORAGE_WARNING = _ratelimit_storage_warning(RATELIMIT_STORAGE_URI, WEB_CONCURRENCY)
    TRUST_PROXY_HEADERS = os.environ.get("TRUST_PROXY_HEADERS", "0") == "1"
    MANUAL_REFRESH_COOLDOWN_SECONDS = int(os.environ.get("MANUAL_REFRESH_COOLDOWN_SECONDS", "180"))
    # Cap upload size — budget Excel files and CSV imports are well under 1 MB
    # in practice, so 16 MB is generous while still bounding memory use.
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
