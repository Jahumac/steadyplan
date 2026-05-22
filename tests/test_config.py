import importlib


def _load_config(monkeypatch, **env):
    keys = {
        "APP_ENV",
        "SESSION_COOKIE_SECURE",
        "REMEMBER_COOKIE_SECURE",
        "SECRET_KEY",
        "RATELIMIT_STORAGE_URI",
        "WEB_CONCURRENCY",
    }
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    import app.config as cfg
    importlib.reload(cfg)
    return cfg.Config


def test_cookie_secure_defaults_off_for_local_http(monkeypatch):
    config = _load_config(monkeypatch, SECRET_KEY="test-secret")

    assert config.APP_ENV == "development"
    assert config.SESSION_COOKIE_SECURE is False
    assert config.REMEMBER_COOKIE_SECURE is False


def test_cookie_secure_defaults_on_in_production(monkeypatch):
    config = _load_config(monkeypatch, APP_ENV="production", SECRET_KEY="test-secret")

    assert config.APP_ENV == "production"
    assert config.SESSION_COOKIE_SECURE is True
    assert config.REMEMBER_COOKIE_SECURE is True


def test_cookie_secure_env_overrides_production_default(monkeypatch):
    config = _load_config(
        monkeypatch,
        APP_ENV="production",
        SESSION_COOKIE_SECURE="0",
        REMEMBER_COOKIE_SECURE="0",
        SECRET_KEY="test-secret",
    )

    assert config.SESSION_COOKIE_SECURE is False
    assert config.REMEMBER_COOKIE_SECURE is False


def test_single_worker_default_keeps_memory_rate_limiter_honest(monkeypatch):
    config = _load_config(monkeypatch, SECRET_KEY="test-secret")

    assert config.WEB_CONCURRENCY == 1
    assert config.RATELIMIT_STORAGE_URI == "memory://"
    assert config.RATELIMIT_STORAGE_WARNING is None


def test_memory_rate_limiter_warns_with_multiple_workers(monkeypatch):
    config = _load_config(
        monkeypatch,
        SECRET_KEY="test-secret",
        WEB_CONCURRENCY="2",
        RATELIMIT_STORAGE_URI="memory://",
    )

    assert config.WEB_CONCURRENCY == 2
    assert "memory://" in config.RATELIMIT_STORAGE_WARNING
    assert "WEB_CONCURRENCY=1" in config.RATELIMIT_STORAGE_WARNING


def test_shared_rate_limit_storage_allows_multiple_workers(monkeypatch):
    config = _load_config(
        monkeypatch,
        SECRET_KEY="test-secret",
        WEB_CONCURRENCY="2",
        RATELIMIT_STORAGE_URI="redis://redis:6379/0",
    )

    assert config.WEB_CONCURRENCY == 2
    assert config.RATELIMIT_STORAGE_WARNING is None
