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
