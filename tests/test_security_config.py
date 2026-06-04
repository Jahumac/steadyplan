import importlib

from werkzeug.middleware.proxy_fix import ProxyFix

from app.extensions import _client_ip


def test_client_ip_ignores_forwarded_headers_by_default(app):
    app.config["TRUST_PROXY_HEADERS"] = False

    with app.test_request_context(
        "/login",
        environ_base={"REMOTE_ADDR": "10.0.0.5"},
        headers={"X-Forwarded-For": "203.0.113.9", "CF-Connecting-IP": "198.51.100.7"},
    ):
        assert _client_ip() == "10.0.0.5"


def test_client_ip_can_trust_forwarded_headers_when_enabled(app):
    app.config["TRUST_PROXY_HEADERS"] = True

    with app.test_request_context(
        "/login",
        environ_base={"REMOTE_ADDR": "10.0.0.5"},
        headers={"X-Forwarded-For": "203.0.113.9, 10.0.0.5"},
    ):
        assert _client_ip() == "203.0.113.9"

    with app.test_request_context(
        "/login",
        environ_base={"REMOTE_ADDR": "10.0.0.5"},
        headers={"CF-Connecting-IP": "198.51.100.7"},
    ):
        assert _client_ip() == "198.51.100.7"


def test_create_app_does_not_wrap_proxyfix_by_default(monkeypatch):
    monkeypatch.setenv("DB_PATH", "/tmp/steadyplan-proxy-default.db")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-not-for-prod")
    monkeypatch.setenv("WTF_CSRF_ENABLED", "0")
    monkeypatch.setenv("FLASK_TESTING", "1")
    monkeypatch.delenv("TRUST_PROXY_HEADERS", raising=False)

    import app as app_pkg
    import app.config as cfg

    importlib.reload(cfg)
    importlib.reload(app_pkg)

    fresh_app = app_pkg.create_app()
    assert not isinstance(fresh_app.wsgi_app, ProxyFix)


def test_create_app_wraps_proxyfix_only_when_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("DB_PATH", "/tmp/steadyplan-proxy-enabled.db")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-not-for-prod")
    monkeypatch.setenv("WTF_CSRF_ENABLED", "0")
    monkeypatch.setenv("FLASK_TESTING", "1")
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "1")

    import app as app_pkg
    import app.config as cfg

    importlib.reload(cfg)
    importlib.reload(app_pkg)

    fresh_app = app_pkg.create_app()
    assert isinstance(fresh_app.wsgi_app, ProxyFix)
