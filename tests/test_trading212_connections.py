import base64
import io
import json
import urllib.error
from email.message import Message

from app.models import (
    PROVIDER_TRADING212,
    fetch_broker_connections,
    upsert_broker_connection,
)
from app.services.trading212 import (
    Trading212ConnectionError,
    decrypt_trading212_credential,
    encrypt_trading212_credential,
    fetch_trading212_account_summary,
)


class _FakeHttpResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self, *_args, **_kwargs):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_settings_renders_trading212_panel_and_support_boundary(app, client, make_user):
    _uid, username, password = make_user(username="t212-settings")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/settings/")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Trading 212 sync (beta)" in body
    assert "Add a read-only Trading 212 connection" in body
    assert "store the key pair encrypted on this server using this app's secret key" in body
    assert "Public API currently only covers Invest and Stocks ISA accounts" in body
    assert "SIPP data is not available through the broker API yet" in body
    assert "CSV import remains available" in body


def test_connect_trading212_saves_encrypted_connection_and_masks_key(app, client, make_user, monkeypatch):
    uid, username, password = make_user(username="t212-connect")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    def fake_probe_trading212_connection(*, api_key, api_secret, environment):
        assert api_key == "live-key-123456"
        assert api_secret == "live-secret-abcdef"
        assert environment == "live"
        return {
            "ok": True,
            "message": "ok",
            "summary": {
                "environment": "live",
                "account_id": "998877",
                "currency": "GBP",
                "available_to_trade": 100.0,
                "cash_in_pies": 0.0,
                "cash_reserved_for_orders": 0.0,
                "investments_current_value": 2400.0,
                "investments_total_cost": 2100.0,
                "investments_unrealized_profit_loss": 300.0,
                "investments_realized_profit_loss": 0.0,
                "total_value": 2500.0,
                "fetched_at": "2026-06-07T18:00:00+00:00",
            },
        }

    monkeypatch.setattr(
        "app.routes.settings.probe_trading212_connection",
        fake_probe_trading212_connection,
    )

    resp = client.post(
        "/settings/trading212/connect",
        data={
            "label": "Trading 212 ISA",
            "environment": "live",
            "api_key": "live-key-123456",
            "api_secret": "live-secret-abcdef",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Saved Trading 212 ISA as a read-only Trading 212 live connection." in body
    assert "SIPP data is not available through the broker API yet" in body
    assert "live…3456" in body
    assert "998877" in body
    assert "GBP" in body
    assert "live-key-123456" not in body
    assert "live-secret-abcdef" not in body

    with app.app_context():
        rows = fetch_broker_connections(uid, provider=PROVIDER_TRADING212)
        assert len(rows) == 1
        row = rows[0]
        assert row is not None
        assert row["label"] == "Trading 212 ISA"
        assert row["environment"] == "live"
        assert row["status"] == "connected"
        assert row["api_key_ciphertext"] != "live-key-123456"
        assert row["api_secret_ciphertext"] != "live-secret-abcdef"
        assert decrypt_trading212_credential(row["api_key_ciphertext"]) == "live-key-123456"
        assert decrypt_trading212_credential(row["api_secret_ciphertext"]) == "live-secret-abcdef"


def test_retest_trading212_failure_updates_status(app, client, make_user, monkeypatch):
    uid, username, password = make_user(username="t212-retest")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        connection = upsert_broker_connection(
            user_id=uid,
            provider=PROVIDER_TRADING212,
            environment="demo",
            label="Trading 212 Demo",
            access_mode="read_only",
            api_key_ciphertext=encrypt_trading212_credential("demo-key-1111"),
            api_secret_ciphertext=encrypt_trading212_credential("demo-secret-2222"),
            status="connected",
            last_tested_at="2026-06-07T18:10:00+00:00",
            external_account_id="123",
            external_account_currency="GBP",
            external_total_value=10.0,
        )
        assert connection is not None

    def fake_probe_trading212_connection(*, api_key, api_secret, environment):
        assert api_key == "demo-key-1111"
        assert api_secret == "demo-secret-2222"
        assert environment == "demo"
        raise Trading212ConnectionError("Trading 212 rate-limited the request. Please wait a moment and try again.")

    monkeypatch.setattr(
        "app.routes.settings.probe_trading212_connection",
        fake_probe_trading212_connection,
    )

    resp = client.post(
        f"/settings/trading212/{connection['id']}/retest",
        data={},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Trading 212 rate-limited the request. Please wait a moment and try again." in body

    with app.app_context():
        row = fetch_broker_connections(uid, provider=PROVIDER_TRADING212)[0]
        assert row is not None
        assert row["status"] == "error"
        assert row["last_error"] == "Trading 212 rate-limited the request. Please wait a moment and try again."


def test_fetch_trading212_account_summary_sends_basic_auth_and_parses_response(app, monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["authorization"] = request.headers.get("Authorization")
        captured["accept"] = request.headers.get("Accept")
        captured["timeout"] = timeout
        return _FakeHttpResponse(
            {
                "cash": {
                    "availableToTrade": 120.5,
                    "inPies": 4.25,
                    "reservedForOrders": 1.0,
                },
                "currency": "GBP",
                "id": 456789,
                "investments": {
                    "currentValue": 900.0,
                    "realizedProfitLoss": 20.0,
                    "totalCost": 800.0,
                    "unrealizedProfitLoss": 100.0,
                },
                "totalValue": 1025.75,
            }
        )

    monkeypatch.setattr("app.services.trading212.urllib.request.urlopen", fake_urlopen)

    with app.app_context():
        summary = fetch_trading212_account_summary(
            api_key="abc123",
            api_secret="shhh456",
            environment="demo",
        )

    expected_auth = "Basic " + base64.b64encode(b"abc123:shhh456").decode("ascii")
    assert captured["url"] == "https://demo.trading212.com/api/v0/equity/account/summary"
    assert captured["authorization"] == expected_auth
    assert captured["accept"] == "application/json"
    assert captured["timeout"] == 12
    assert summary["environment"] == "demo"
    assert summary["account_id"] == "456789"
    assert summary["currency"] == "GBP"
    assert summary["available_to_trade"] == 120.5
    assert summary["investments_current_value"] == 900.0
    assert summary["total_value"] == 1025.75


def test_fetch_trading212_account_summary_surfaces_friendly_403(app, monkeypatch):
    def fake_urlopen(_request, timeout=0):
        raise urllib.error.HTTPError(
            url="https://live.trading212.com/api/v0/equity/account/summary",
            code=403,
            msg="Forbidden",
            hdrs=Message(),
            fp=io.BytesIO(json.dumps({"message": "API key IP mismatch"}).encode("utf-8")),
        )

    monkeypatch.setattr("app.services.trading212.urllib.request.urlopen", fake_urlopen)

    with app.app_context():
        try:
            fetch_trading212_account_summary(
                api_key="abc123",
                api_secret="secret789",
                environment="live",
            )
        except Trading212ConnectionError as exc:
            message = str(exc)
        else:
            raise AssertionError("Expected Trading212ConnectionError")

    assert "limits the Public API to Invest and Stocks ISA accounts" in message
    assert "API key IP mismatch" in message
