import base64
import io
import json
import urllib.error
from email.message import Message
from pathlib import Path

from app.models import (
    PROVIDER_TRADING212,
    add_holding,
    create_account,
    delete_broker_connection,
    fetch_account,
    fetch_broker_connections,
    fetch_broker_sync_events,
    fetch_holdings_for_account,
    log_broker_sync_event,
    update_account,
    upsert_broker_connection,
)
from app.services.trading212 import (
    Trading212ConnectionError,
    decrypt_trading212_credential,
    encrypt_trading212_credential,
    fetch_trading212_account_summary,
    fetch_trading212_positions,
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


def test_requirements_include_cryptography_for_trading212_runtime():
    requirements = Path(__file__).resolve().parents[1] / "requirements.txt"
    lines = [line.strip() for line in requirements.read_text(encoding="utf-8").splitlines()]
    assert any(line.lower().startswith("cryptography") for line in lines)


def test_settings_renders_trading212_panel_and_support_boundary(app, client, make_user):
    _uid, username, password = make_user(username="t212-settings")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/settings/")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Trading 212 sync (beta)" in body
    assert "Add a read-only Trading 212 connection" in body
    assert "store the key pair encrypted on this server using this app's secret key" in body
    assert "Public API currently supports Invest and Stocks ISA only" in body
    assert "Cash ISA and SIPP accounts should stay manual/CSV-tracked for now" in body
    assert "SIPP data is not available through the broker API yet" not in body
    assert "SteadyPlan's own price service and manual/CSV imports stay in place" in body
    assert "SteadyPlan's own price service and CSV/manual imports stay in place" not in body
    assert "SteadyPlan can keep more than one read-only Trading 212 connection" in body
    assert "separate Invest and Stocks ISA accounts can be saved side by side" in body
    assert "separate Invest and ISA accounts can be saved side by side" not in body
    assert "Manual/CSV imports remain available even if you never connect the broker API" in body
    assert "CSV import remains available" not in body


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
    assert "Cash ISA and SIPP accounts should stay manual/CSV-tracked for now" in body
    assert "SteadyPlan's own price service and manual/CSV imports stay in place" in body
    assert "SteadyPlan's own price service and CSV/manual imports stay in place" not in body
    assert "SIPP data is not available through the broker API yet" not in body
    assert "Preview holdings snapshot" in body
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


def test_disconnect_trading212_keeps_manual_csv_path_message(app, client, make_user):
    uid, username, password = make_user(username="t212-disconnect")
    with app.app_context():
        connection = upsert_broker_connection(
            user_id=uid,
            provider=PROVIDER_TRADING212,
            environment="live",
            label="Trading 212 ISA",
            access_mode="read_only",
            api_key_ciphertext=encrypt_trading212_credential("live-key"),
            api_secret_ciphertext=encrypt_trading212_credential("live-secret"),
            status="connected",
            last_tested_at="2026-06-08T10:00:00+00:00",
            external_account_id="ISA-111",
            external_account_currency="GBP",
            external_total_value=12000.0,
        )
        assert connection is not None
        connection_id = connection["id"]

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    resp = client.post(f"/settings/trading212/{connection_id}/disconnect", follow_redirects=True)
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Trading 212 connection removed. Manual/CSV imports remain available." in body
    assert "Trading 212 connection removed. CSV/manual imports remain available." not in body

    with app.app_context():
        rows = fetch_broker_connections(uid, provider=PROVIDER_TRADING212)
        assert rows == []


def test_connect_trading212_keeps_multiple_live_accounts_separate(app, client, make_user, monkeypatch):
    uid, username, password = make_user(username="t212-multi-live")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    probes = [
        {
            "ok": True,
            "message": "ok",
            "summary": {
                "environment": "live",
                "account_id": "ISA-111",
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
        },
        {
            "ok": True,
            "message": "ok",
            "summary": {
                "environment": "live",
                "account_id": "INVEST-222",
                "currency": "GBP",
                "available_to_trade": 50.0,
                "cash_in_pies": 5.0,
                "cash_reserved_for_orders": 0.0,
                "investments_current_value": 1450.0,
                "investments_total_cost": 1300.0,
                "investments_unrealized_profit_loss": 150.0,
                "investments_realized_profit_loss": 0.0,
                "total_value": 1500.0,
                "fetched_at": "2026-06-07T18:05:00+00:00",
            },
        },
    ]

    def fake_probe_trading212_connection(*, api_key, api_secret, environment):
        assert environment == "live"
        return probes.pop(0)

    monkeypatch.setattr(
        "app.routes.settings.probe_trading212_connection",
        fake_probe_trading212_connection,
    )

    first = client.post(
        "/settings/trading212/connect",
        data={
            "label": "Trading 212 ISA",
            "environment": "live",
            "api_key": "live-key-isa",
            "api_secret": "live-secret-isa",
        },
        follow_redirects=True,
    )
    assert first.status_code == 200

    second = client.post(
        "/settings/trading212/connect",
        data={
            "label": "Trading 212 Invest",
            "environment": "live",
            "api_key": "live-key-invest",
            "api_secret": "live-secret-invest",
        },
        follow_redirects=True,
    )
    assert second.status_code == 200
    body = second.data.decode("utf-8", errors="ignore")
    assert "Trading 212 ISA" in body
    assert "Trading 212 Invest" in body
    assert "ISA-111" in body
    assert "INVEST-222" in body

    with app.app_context():
        rows = fetch_broker_connections(uid, provider=PROVIDER_TRADING212)
        assert len(rows) == 2
        assert [row["external_account_id"] for row in rows] == ["ISA-111", "INVEST-222"]
        by_account = {row["external_account_id"]: row for row in rows}
        row_isa = by_account["ISA-111"]
        row_invest = by_account["INVEST-222"]
        assert row_isa is not None
        assert row_invest is not None
        assert decrypt_trading212_credential(row_isa["api_key_ciphertext"]) == "live-key-isa"
        assert decrypt_trading212_credential(row_invest["api_key_ciphertext"]) == "live-key-invest"


def test_accounts_edit_form_offers_saved_trading212_linking(app, client, make_user):
    uid, username, password = make_user(username="t212-account-link-form")
    with app.app_context():
        account_id = create_account(
            {
                "name": "Trading 212 ISA",
                "provider": "Trading 212",
                "wrapper_type": "Stocks & Shares ISA",
                "category": "Investments",
                "tags": "",
                "current_value": 12000.0,
                "monthly_contribution": 200.0,
                "pension_contribution_day": 0,
                "goal_value": None,
                "valuation_mode": "manual",
                "growth_mode": "default",
                "growth_rate_override": None,
                "owner": "",
                "linked_broker_connection_id": None,
                "is_active": 1,
                "notes": "",
                "last_updated": "2026-06-08T10:00:00+00:00",
            },
            uid,
        )
        upsert_broker_connection(
            user_id=uid,
            provider=PROVIDER_TRADING212,
            environment="live",
            label="Trading 212 ISA live",
            access_mode="read_only",
            api_key_ciphertext=encrypt_trading212_credential("isa-key"),
            api_secret_ciphertext=encrypt_trading212_credential("isa-secret"),
            status="connected",
            last_tested_at="2026-06-08T10:00:00+00:00",
            external_account_id="ISA-111",
            external_account_currency="GBP",
            external_total_value=12000.0,
        )

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get(f"/accounts/{account_id}?mode=edit")
    assert response.status_code == 200
    body = response.data.decode("utf-8", errors="ignore")
    assert "Optional Trading 212 link" in body
    assert "Saved Trading 212 connection" in body
    assert "Trading 212 ISA live · ISA-111 · GBP" in body
    assert "This does not overwrite balances or holdings yet." in body


def test_accounts_edit_form_empty_state_keeps_manual_csv_path(app, client, make_user):
    uid, username, password = make_user(username="t212-account-link-empty")
    with app.app_context():
        account_id = create_account(
            {
                "name": "Trading 212 ISA",
                "provider": "Trading 212",
                "wrapper_type": "Stocks & Shares ISA",
                "category": "Investments",
                "tags": "",
                "current_value": 12000.0,
                "monthly_contribution": 200.0,
                "pension_contribution_day": 0,
                "goal_value": None,
                "valuation_mode": "manual",
                "growth_mode": "default",
                "growth_rate_override": None,
                "owner": "",
                "linked_broker_connection_id": None,
                "is_active": 1,
                "notes": "",
                "last_updated": "2026-06-08T10:00:00+00:00",
            },
            uid,
        )

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get(f"/accounts/{account_id}?mode=edit")
    assert response.status_code == 200
    body = response.data.decode("utf-8", errors="ignore")
    assert "No saved Trading 212 connections yet." in body
    assert "Manual/CSV tracking stays available until you choose to add a read-only connection in Settings." in body
    assert "Add one in Settings first if you want to link this account for future preview and sync work." not in body


def test_accounts_edit_form_hides_trading212_picker_for_unsupported_wrapper(app, client, make_user):
    uid, username, password = make_user(username="t212-cash-isa-link-form")
    with app.app_context():
        connection = upsert_broker_connection(
            user_id=uid,
            provider=PROVIDER_TRADING212,
            environment="live",
            label="Trading 212 Cash ISA live",
            access_mode="read_only",
            api_key_ciphertext=encrypt_trading212_credential("cash-key"),
            api_secret_ciphertext=encrypt_trading212_credential("cash-secret"),
            status="connected",
            last_tested_at="2026-06-08T10:00:00+00:00",
            external_account_id="CASH-111",
            external_account_currency="GBP",
            external_total_value=7000.0,
        )
        assert connection is not None
        account_id = create_account(
            {
                "name": "Trading 212 Cash ISA",
                "provider": "Trading 212",
                "wrapper_type": "Cash ISA",
                "category": "Cash",
                "tags": "",
                "current_value": 7000.0,
                "monthly_contribution": 100.0,
                "pension_contribution_day": 0,
                "goal_value": None,
                "valuation_mode": "manual",
                "growth_mode": "default",
                "growth_rate_override": None,
                "owner": "",
                "linked_broker_connection_id": connection["id"],
                "is_active": 1,
                "notes": "",
                "last_updated": "2026-06-08T10:00:00+00:00",
            },
            uid,
        )

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get(f"/accounts/{account_id}?mode=edit")
    assert response.status_code == 200
    body = response.data.decode("utf-8", errors="ignore")
    assert "Optional Trading 212 link" in body
    assert "Trading 212 Public API currently supports Invest and Stocks ISA only. Keep this account manual/CSV-tracked for now." in body
    assert "Trading 212 Cash ISA live · CASH-111 · GBP" not in body
    assert 'name="linked_broker_connection_id" value="%s"' % connection["id"] in body


def test_api_create_account_rejects_trading212_link_for_unsupported_wrapper(app, client, make_user):
    uid, username, password = make_user(username="t212-cash-isa-create")
    with app.app_context():
        connection = upsert_broker_connection(
            user_id=uid,
            provider=PROVIDER_TRADING212,
            environment="live",
            label="Trading 212 Cash ISA live",
            access_mode="read_only",
            api_key_ciphertext=encrypt_trading212_credential("cash-create-key"),
            api_secret_ciphertext=encrypt_trading212_credential("cash-create-secret"),
            status="connected",
            last_tested_at="2026-06-08T10:00:00+00:00",
            external_account_id="CASH-222",
            external_account_currency="GBP",
            external_total_value=6500.0,
        )
        assert connection is not None

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.post(
        "/accounts/api/create",
        data={
            "name": "Trading 212 Cash ISA",
            "provider": "Trading 212",
            "wrapper_type": "Cash ISA",
            "category": "Cash",
            "current_value": "6500",
            "monthly_contribution": "100",
            "valuation_mode": "manual",
            "growth_mode": "default",
            "linked_broker_connection_id": str(connection["id"]),
        },
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload == {
        "ok": False,
        "error": "Trading 212 linking is currently limited to Invest and Stocks ISA accounts",
    }


def test_account_edit_can_link_existing_account_to_saved_trading212_connection(app, client, make_user):
    uid, username, password = make_user(username="t212-account-link-save")
    with app.app_context():
        account_id = create_account(
            {
                "name": "Existing ISA",
                "provider": "Trading 212",
                "wrapper_type": "Stocks & Shares ISA",
                "category": "Investments",
                "tags": "",
                "current_value": 8000.0,
                "monthly_contribution": 150.0,
                "pension_contribution_day": 0,
                "goal_value": None,
                "valuation_mode": "manual",
                "growth_mode": "default",
                "growth_rate_override": None,
                "owner": "",
                "linked_broker_connection_id": None,
                "is_active": 1,
                "notes": "",
                "last_updated": "2026-06-08T10:00:00+00:00",
            },
            uid,
        )
        connection = upsert_broker_connection(
            user_id=uid,
            provider=PROVIDER_TRADING212,
            environment="live",
            label="Trading 212 ISA live",
            access_mode="read_only",
            api_key_ciphertext=encrypt_trading212_credential("isa-key"),
            api_secret_ciphertext=encrypt_trading212_credential("isa-secret"),
            status="connected",
            last_tested_at="2026-06-08T10:00:00+00:00",
            external_account_id="ISA-111",
            external_account_currency="GBP",
            external_total_value=12000.0,
        )
        assert connection is not None

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.post(
        f"/accounts/{account_id}",
        data={
            "form_name": "account",
            "name": "Existing ISA",
            "provider": "Trading 212",
            "wrapper_type": "Stocks & Shares ISA",
            "category": "Investments",
            "current_value": "8000",
            "monthly_contribution": "150",
            "valuation_mode": "manual",
            "growth_mode": "default",
            "linked_broker_connection_id": str(connection["id"]),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    body = response.data.decode("utf-8", errors="ignore")
    assert "Linked Trading 212 connection:" in body
    assert "Trading 212 ISA live" in body
    assert "ISA-111" in body
    assert "Broker status" in body
    assert "Account source" in body
    assert "Broker primary" in body
    assert "Connected" in body
    assert "Last successful broker fetch" in body
    assert "2026-06-08 10:00 UTC" in body
    assert "Broker total (GBP)" in body
    assert "Tracked value in SteadyPlan" in body
    assert "£12,000.00" in body
    assert "£8,000.00" in body
    assert "Broker total is above tracked value" in body
    assert "+£4,000.00" in body
    assert "Trading 212 is currently the live source for this linked account. Manual tracking remains the fallback if the broker snapshot is unavailable." in body
    assert "Use the linked broker preview before changing holdings or manually adjusting this account." in body

    with app.app_context():
        account = fetch_account(account_id, uid)
        assert account is not None
        assert account["linked_broker_connection_id"] == connection["id"]


def test_account_detail_shows_linked_trading212_error_state(app, client, make_user):
    uid, username, password = make_user(username="t212-account-link-error")
    with app.app_context():
        account_id = create_account(
            {
                "name": "Existing ISA",
                "provider": "Trading 212",
                "wrapper_type": "Stocks & Shares ISA",
                "category": "Investments",
                "tags": "",
                "current_value": 5000.0,
                "monthly_contribution": 150.0,
                "pension_contribution_day": 0,
                "goal_value": None,
                "valuation_mode": "manual",
                "growth_mode": "default",
                "growth_rate_override": None,
                "owner": "",
                "linked_broker_connection_id": None,
                "is_active": 1,
                "notes": "",
                "last_updated": "2026-06-08T10:00:00+00:00",
            },
            uid,
        )
        connection = upsert_broker_connection(
            user_id=uid,
            provider=PROVIDER_TRADING212,
            environment="live",
            label="Trading 212 ISA live",
            access_mode="read_only",
            api_key_ciphertext=encrypt_trading212_credential("isa-key"),
            api_secret_ciphertext=encrypt_trading212_credential("isa-secret"),
            status="error",
            last_error="Broker timeout while fetching snapshot",
            last_tested_at="2026-06-09T07:15:00+00:00",
            external_account_id="ISA-111",
            external_account_currency="GBP",
            external_total_value=None,
        )
        assert connection is not None
        account = fetch_account(account_id, uid)
        assert account is not None
        account_payload = dict(account)
        account_payload["linked_broker_connection_id"] = connection["id"]
        update_fields = {
            "id": account_id,
            "name": account_payload["name"],
            "provider": account_payload["provider"],
            "wrapper_type": account_payload["wrapper_type"],
            "category": account_payload["category"],
            "tags": account_payload.get("tags") or "",
            "current_value": account_payload.get("current_value") or 0,
            "monthly_contribution": account_payload.get("monthly_contribution") or 0,
            "pension_contribution_day": account_payload.get("pension_contribution_day") or 0,
            "goal_value": account_payload.get("goal_value"),
            "valuation_mode": account_payload.get("valuation_mode") or "manual",
            "growth_mode": account_payload.get("growth_mode") or "default",
            "growth_rate_override": account_payload.get("growth_rate_override"),
            "owner": account_payload.get("owner") or "",
            "linked_broker_connection_id": connection["id"],
            "notes": account_payload.get("notes") or "",
            "last_updated": "2026-06-09T07:20:00+00:00",
        }
        update_account(update_fields, uid)

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get(f"/accounts/{account_id}")
    assert response.status_code == 200
    body = response.data.decode("utf-8", errors="ignore")
    assert "Broker status" in body
    assert "Account source" in body
    assert "Manual fallback" in body
    assert "Needs attention" in body
    assert "SteadyPlan is currently relying on its stored/manual tracking for this linked account because the broker snapshot is unavailable or incomplete." in body
    assert "Last broker error: Broker timeout while fetching snapshot" in body
    assert "Broker total (GBP)" in body
    assert "Not fetched yet" not in body
    assert "Use the linked broker preview before changing holdings or manually adjusting this account." not in body


def test_account_detail_hides_broker_primary_status_for_unsupported_wrapper(app, client, make_user):
    uid, username, password = make_user(username="t212-cash-isa-detail")
    with app.app_context():
        connection = upsert_broker_connection(
            user_id=uid,
            provider=PROVIDER_TRADING212,
            environment="live",
            label="Trading 212 Cash ISA live",
            access_mode="read_only",
            api_key_ciphertext=encrypt_trading212_credential("cash-detail-key"),
            api_secret_ciphertext=encrypt_trading212_credential("cash-detail-secret"),
            status="connected",
            last_tested_at="2026-06-08T10:00:00+00:00",
            external_account_id="CASH-111",
            external_account_currency="GBP",
            external_total_value=7000.0,
        )
        assert connection is not None
        account_id = create_account(
            {
                "name": "Trading 212 Cash ISA",
                "provider": "Trading 212",
                "wrapper_type": "Cash ISA",
                "category": "Cash",
                "tags": "",
                "current_value": 7000.0,
                "monthly_contribution": 100.0,
                "pension_contribution_day": 0,
                "goal_value": None,
                "valuation_mode": "manual",
                "growth_mode": "default",
                "growth_rate_override": None,
                "owner": "",
                "linked_broker_connection_id": connection["id"],
                "is_active": 1,
                "notes": "",
                "last_updated": "2026-06-08T10:00:00+00:00",
            },
            uid,
        )

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get(f"/accounts/{account_id}")
    assert response.status_code == 200
    body = response.data.decode("utf-8", errors="ignore")
    assert "Linked Trading 212 connection:" in body
    assert "Trading 212 Public API currently supports Invest and Stocks ISA only. Keep this account manual/CSV-tracked for now." in body
    assert "Account source" not in body
    assert "Broker status" not in body
    assert "Broker primary" not in body
    assert "Manual fallback" not in body
    assert "Preview linked broker snapshot" not in body


def test_account_list_shows_trading212_account_source_summary(app, client, make_user):
    uid, username, password = make_user(username="t212-account-source-list")
    with app.app_context():
        connected_connection = upsert_broker_connection(
            user_id=uid,
            provider=PROVIDER_TRADING212,
            environment="live",
            label="Trading 212 ISA live",
            access_mode="read_only",
            api_key_ciphertext=encrypt_trading212_credential("isa-key"),
            api_secret_ciphertext=encrypt_trading212_credential("isa-secret"),
            status="connected",
            last_tested_at="2026-06-08T10:00:00+00:00",
            external_account_id="ISA-111",
            external_account_currency="GBP",
            external_total_value=12000.0,
        )
        assert connected_connection is not None
        fallback_connection = upsert_broker_connection(
            user_id=uid,
            provider=PROVIDER_TRADING212,
            environment="live",
            label="Trading 212 Invest live",
            access_mode="read_only",
            api_key_ciphertext=encrypt_trading212_credential("invest-key"),
            api_secret_ciphertext=encrypt_trading212_credential("invest-secret"),
            status="error",
            last_error="Broker timeout while fetching snapshot",
            last_tested_at="2026-06-09T07:15:00+00:00",
            external_account_id="INVEST-222",
            external_account_currency="GBP",
            external_total_value=None,
        )
        assert fallback_connection is not None
        create_account(
            {
                "name": "Trading 212 ISA",
                "provider": "Trading 212",
                "wrapper_type": "Stocks & Shares ISA",
                "category": "Investments",
                "tags": "",
                "current_value": 8000.0,
                "monthly_contribution": 150.0,
                "pension_contribution_day": 0,
                "goal_value": None,
                "valuation_mode": "manual",
                "growth_mode": "default",
                "growth_rate_override": None,
                "owner": "",
                "linked_broker_connection_id": connected_connection["id"],
                "is_active": 1,
                "notes": "",
                "last_updated": "2026-06-08T10:00:00+00:00",
            },
            uid,
        )
        create_account(
            {
                "name": "Trading 212 Invest",
                "provider": "Trading 212",
                "wrapper_type": "General Investment Account",
                "category": "Investments",
                "tags": "",
                "current_value": 5000.0,
                "monthly_contribution": 100.0,
                "pension_contribution_day": 0,
                "goal_value": None,
                "valuation_mode": "manual",
                "growth_mode": "default",
                "growth_rate_override": None,
                "owner": "",
                "linked_broker_connection_id": fallback_connection["id"],
                "is_active": 1,
                "notes": "",
                "last_updated": "2026-06-09T07:20:00+00:00",
            },
            uid,
        )
        create_account(
            {
                "name": "Manual Cash Pot",
                "provider": "Monzo",
                "wrapper_type": "Cash Savings",
                "category": "Cash",
                "tags": "",
                "current_value": 1200.0,
                "monthly_contribution": 25.0,
                "pension_contribution_day": 0,
                "goal_value": None,
                "valuation_mode": "manual",
                "growth_mode": "default",
                "growth_rate_override": None,
                "owner": "",
                "linked_broker_connection_id": None,
                "is_active": 1,
                "notes": "",
                "last_updated": "2026-06-09T07:20:00+00:00",
            },
            uid,
        )

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get("/accounts/")
    assert response.status_code == 200
    body = response.data.decode("utf-8", errors="ignore")
    assert "Trading 212 ISA" in body
    assert "Trading 212 Invest" in body
    assert "Manual Cash Pot" in body
    assert body.count("Account source:") == 2
    assert "Account source: <strong>Broker primary</strong>" in body
    assert "Account source: <strong>Manual fallback</strong>" in body


def test_delete_trading212_connection_clears_linked_account_reference(app, make_user):
    uid, _, _ = make_user(username="t212-account-link-delete", password="password123")
    with app.app_context():
        account_id = create_account(
            {
                "name": "Existing ISA",
                "provider": "Trading 212",
                "wrapper_type": "Stocks & Shares ISA",
                "category": "Investments",
                "tags": "",
                "current_value": 8000.0,
                "monthly_contribution": 150.0,
                "pension_contribution_day": 0,
                "goal_value": None,
                "valuation_mode": "manual",
                "growth_mode": "default",
                "growth_rate_override": None,
                "owner": "",
                "linked_broker_connection_id": None,
                "is_active": 1,
                "notes": "",
                "last_updated": "2026-06-08T10:00:00+00:00",
            },
            uid,
        )
        connection = upsert_broker_connection(
            user_id=uid,
            provider=PROVIDER_TRADING212,
            environment="live",
            label="Trading 212 ISA live",
            access_mode="read_only",
            api_key_ciphertext=encrypt_trading212_credential("isa-key"),
            api_secret_ciphertext=encrypt_trading212_credential("isa-secret"),
            status="connected",
            last_tested_at="2026-06-08T10:00:00+00:00",
            external_account_id="ISA-111",
            external_account_currency="GBP",
            external_total_value=12000.0,
        )
        assert connection is not None
        account = fetch_account(account_id, uid)
        assert account is not None
        account_payload = dict(account)
        account_payload["linked_broker_connection_id"] = connection["id"]
        update_fields = {
            "id": account_id,
            "name": account_payload["name"],
            "provider": account_payload["provider"],
            "wrapper_type": account_payload["wrapper_type"],
            "category": account_payload["category"],
            "tags": account_payload.get("tags") or "",
            "current_value": account_payload.get("current_value") or 0,
            "monthly_contribution": account_payload.get("monthly_contribution") or 0,
            "pension_contribution_day": account_payload.get("pension_contribution_day") or 0,
            "goal_value": account_payload.get("goal_value"),
            "valuation_mode": account_payload.get("valuation_mode") or "manual",
            "growth_mode": account_payload.get("growth_mode") or "default",
            "growth_rate_override": account_payload.get("growth_rate_override"),
            "owner": account_payload.get("owner") or "",
            "linked_broker_connection_id": connection["id"],
            "notes": account_payload.get("notes") or "",
            "last_updated": "2026-06-08T10:05:00+00:00",
        }
        update_account(update_fields, uid)
        delete_broker_connection(connection["id"], uid)
        refreshed = fetch_account(account_id, uid)
        assert refreshed is not None
        assert refreshed["linked_broker_connection_id"] is None


def test_account_detail_shows_preview_button_for_linked_trading212_connection(app, client, make_user):
    uid, username, password = make_user(username="t212-account-preview-button")
    with app.app_context():
        connection = upsert_broker_connection(
            user_id=uid,
            provider=PROVIDER_TRADING212,
            environment="live",
            label="Trading 212 ISA live",
            access_mode="read_only",
            api_key_ciphertext=encrypt_trading212_credential("isa-key"),
            api_secret_ciphertext=encrypt_trading212_credential("isa-secret"),
            status="connected",
            last_tested_at="2026-06-08T10:00:00+00:00",
            external_account_id="ISA-111",
            external_account_currency="GBP",
            external_total_value=12000.0,
        )
        assert connection is not None
        account_id = create_account(
            {
                "name": "Trading 212 ISA",
                "provider": "Trading 212",
                "wrapper_type": "Stocks & Shares ISA",
                "category": "Investments",
                "tags": "",
                "current_value": 12000.0,
                "monthly_contribution": 200.0,
                "pension_contribution_day": 0,
                "goal_value": None,
                "valuation_mode": "holdings",
                "growth_mode": "default",
                "growth_rate_override": None,
                "owner": "",
                "linked_broker_connection_id": connection["id"],
                "is_active": 1,
                "notes": "",
                "last_updated": "2026-06-08T10:00:00+00:00",
            },
            uid,
        )

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    response = client.get(f"/accounts/{account_id}")
    assert response.status_code == 200
    body = response.data.decode("utf-8", errors="ignore")
    assert "Preview linked broker snapshot" in body
    assert f'action="/settings/trading212/{connection["id"]}/preview"' in body
    assert 'name="account_id" value="%s"' % account_id in body


def test_account_linked_preview_only_compares_holdings_from_that_account(app, client, make_user, monkeypatch):
    uid, username, password = make_user(username="t212-linked-preview-focus")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        connection = upsert_broker_connection(
            user_id=uid,
            provider=PROVIDER_TRADING212,
            environment="live",
            label="Trading 212 ISA",
            access_mode="read_only",
            api_key_ciphertext=encrypt_trading212_credential("live-preview-key"),
            api_secret_ciphertext=encrypt_trading212_credential("live-preview-secret"),
            status="connected",
            last_tested_at="2026-06-07T18:10:00+00:00",
            external_account_id="ACC-123",
            external_account_currency="GBP",
            external_total_value=3100.0,
        )
        assert connection is not None
        linked_account_id = create_account(
            {
                "name": "Trading 212 ISA",
                "provider": "Trading 212",
                "wrapper_type": "ISA",
                "category": "investments",
                "tags": "",
                "current_value": 2400.0,
                "monthly_contribution": 0.0,
                "goal_value": 0.0,
                "valuation_mode": "holdings",
                "growth_mode": "rate",
                "growth_rate_override": 0.0,
                "owner": "joint",
                "linked_broker_connection_id": connection["id"],
                "is_active": 1,
                "notes": "",
                "last_updated": "2026-06-07",
            },
            uid,
        )
        other_account_id = create_account(
            {
                "name": "Other broker account",
                "provider": "Trading 212",
                "wrapper_type": "GIA",
                "category": "investments",
                "tags": "",
                "current_value": 500.0,
                "monthly_contribution": 0.0,
                "goal_value": 0.0,
                "valuation_mode": "holdings",
                "growth_mode": "rate",
                "growth_rate_override": 0.0,
                "owner": "joint",
                "linked_broker_connection_id": None,
                "is_active": 1,
                "notes": "",
                "last_updated": "2026-06-07",
            },
            uid,
        )
        add_holding(
            {
                "account_id": linked_account_id,
                "holding_catalogue_id": None,
                "holding_name": "Apple Inc",
                "ticker": "AAPL_US_EQ",
                "asset_type": "stock",
                "bucket": "stocks",
                "value": 2400.0,
                "units": 10.0,
                "price": 240.0,
                "notes": "",
            },
            uid,
        )
        add_holding(
            {
                "account_id": other_account_id,
                "holding_catalogue_id": None,
                "holding_name": "Vanguard FTSE All-World",
                "ticker": "VWRP_LSE_EQ",
                "asset_type": "fund",
                "bucket": "stocks",
                "value": 500.0,
                "units": 4.0,
                "price": 125.0,
                "notes": "",
            },
            uid,
        )

    def fake_fetch_trading212_portfolio_snapshot(*, api_key, api_secret, environment):
        assert api_key == "live-preview-key"
        assert api_secret == "live-preview-secret"
        assert environment == "live"
        return {
            "environment": "live",
            "fetched_at": "2026-06-08T09:30:00+00:00",
            "summary": {
                "environment": "live",
                "account_id": "ACC-123",
                "currency": "GBP",
                "available_to_trade": 150.0,
                "cash_in_pies": 25.0,
                "cash_reserved_for_orders": 5.0,
                "investments_current_value": 2950.0,
                "investments_total_cost": 2500.0,
                "investments_unrealized_profit_loss": 450.0,
                "investments_realized_profit_loss": 0.0,
                "total_value": 3100.0,
                "fetched_at": "2026-06-08T09:30:00+00:00",
            },
            "positions": [
                {
                    "ticker": "AAPL_US_EQ",
                    "name": "Apple Inc",
                    "units": 10.0,
                    "price": 245.0,
                    "value": 2450.0,
                    "currency": "GBP",
                },
                {
                    "ticker": "VWRP_LSE_EQ",
                    "name": "Vanguard FTSE All-World",
                    "units": 4.0,
                    "price": 125.0,
                    "value": 500.0,
                    "currency": "GBP",
                },
            ],
        }

    monkeypatch.setattr(
        "app.routes.settings.fetch_trading212_portfolio_snapshot",
        fake_fetch_trading212_portfolio_snapshot,
    )

    resp = client.post(
        f"/settings/trading212/{connection['id']}/preview",
        data={"account_id": str(linked_account_id)},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Focused on linked account <strong>Trading 212 ISA</strong>" in body
    assert "Only holdings from this SteadyPlan account were compared with the broker snapshot." in body
    assert "Proposed apply plan" in body
    assert "Matched holdings to update" in body
    assert "Broker-only positions to add" in body
    assert "Tracked-only holdings to review" in body
    assert "Broker vs tracked value gap" in body
    assert "+550.00 GBP" in body
    assert "Compare <strong>2950.00 GBP</strong> from Trading 212 against <strong>2400.00 GBP</strong> currently tracked in SteadyPlan." in body
    assert "Apply reviewed matched changes" in body
    assert "Add reviewed broker-only positions" in body
    assert "This first write step only updates already matched holdings on <strong>Trading 212 ISA</strong>." in body
    assert "This step only adds broker-only positions with no possible tracked match clues." in body
    assert "This preview found differences to review. Any write step should stay explicit, account-scoped, and non-destructive." in body
    assert "Back to account" in body
    assert "Recent sync activity" in body
    assert "Previewed snapshot" in body
    assert "Last reviewed write" in body
    assert "Preview linked broker snapshot" not in body
    assert "Apple Inc" in body
    assert "Vanguard FTSE All-World" in body
    assert "Matched holdings" in body
    assert "Broker-only positions" in body
    assert "Other broker account" not in body
    assert "Tracked holdings not seen in this snapshot" in body


def test_apply_trading212_reviewed_changes_updates_only_matched_holdings(app, client, make_user, monkeypatch):
    uid, username, password = make_user(username="t212-apply-reviewed")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        connection = upsert_broker_connection(
            user_id=uid,
            provider=PROVIDER_TRADING212,
            environment="live",
            label="Trading 212 ISA",
            access_mode="read_only",
            api_key_ciphertext=encrypt_trading212_credential("apply-key"),
            api_secret_ciphertext=encrypt_trading212_credential("apply-secret"),
            status="connected",
            last_tested_at="2026-06-09T08:00:00+00:00",
            external_account_id="ACC-APPLY-1",
            external_account_currency="GBP",
            external_total_value=3200.0,
        )
        account_id = create_account(
            {
                "name": "Trading 212 ISA",
                "provider": "Trading 212",
                "wrapper_type": "ISA",
                "category": "investments",
                "tags": "",
                "current_value": 3000.0,
                "monthly_contribution": 0.0,
                "goal_value": 0.0,
                "valuation_mode": "holdings",
                "growth_mode": "rate",
                "growth_rate_override": 0.0,
                "owner": "joint",
                "linked_broker_connection_id": connection["id"],
                "is_active": 1,
                "notes": "",
                "last_updated": "2026-06-09",
            },
            uid,
        )
        add_holding(
            {
                "account_id": account_id,
                "holding_catalogue_id": None,
                "holding_name": "Apple Inc",
                "ticker": "AAPL_US_EQ",
                "asset_type": "stock",
                "bucket": "stocks",
                "value": 2400.0,
                "units": 10.0,
                "price": 240.0,
                "notes": "",
            },
            uid,
        )
        add_holding(
            {
                "account_id": account_id,
                "holding_catalogue_id": None,
                "holding_name": "Manual fund",
                "ticker": "MANUAL1",
                "asset_type": "fund",
                "bucket": "stocks",
                "value": 600.0,
                "units": 6.0,
                "price": 100.0,
                "notes": "",
            },
            uid,
        )

    def fake_fetch_trading212_portfolio_snapshot(*, api_key, api_secret, environment):
        assert api_key == "apply-key"
        assert api_secret == "apply-secret"
        assert environment == "live"
        return {
            "environment": "live",
            "fetched_at": "2026-06-09T08:30:00+00:00",
            "summary": {
                "environment": "live",
                "account_id": "ACC-APPLY-1",
                "currency": "GBP",
                "available_to_trade": 150.0,
                "cash_in_pies": 0.0,
                "cash_reserved_for_orders": 0.0,
                "investments_current_value": 3050.0,
                "investments_total_cost": 2500.0,
                "investments_unrealized_profit_loss": 550.0,
                "investments_realized_profit_loss": 0.0,
                "total_value": 3200.0,
                "fetched_at": "2026-06-09T08:30:00+00:00",
            },
            "positions": [
                {
                    "ticker": "AAPL_US_EQ",
                    "name": "Apple Inc",
                    "units": 11.0,
                    "price": 245.0,
                    "value": 2695.0,
                    "currency": "GBP",
                },
                {
                    "ticker": "NEWFUND_EQ",
                    "name": "New fund",
                    "units": 1.0,
                    "price": 355.0,
                    "value": 355.0,
                    "currency": "GBP",
                },
            ],
        }

    monkeypatch.setattr(
        "app.routes.settings.fetch_trading212_portfolio_snapshot",
        fake_fetch_trading212_portfolio_snapshot,
    )

    resp = client.post(
        f"/settings/trading212/{connection['id']}/apply-reviewed",
        data={"account_id": str(account_id), "confirm_apply_matched": "yes"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Applied 1 matched Trading 212 holding update." in body
    assert "1 broker-only position and 1 tracked-only holding were left untouched for review." in body

    with app.app_context():
        holdings = list(fetch_holdings_for_account(account_id))
        apple = next(row for row in holdings if row["ticker"] == "AAPL_US_EQ")
        manual = next(row for row in holdings if row["ticker"] == "MANUAL1")
        assert apple["units"] == 11.0
        assert apple["price"] == 245.0
        assert apple["value"] == 2695.0
        assert manual["units"] == 6.0
        assert manual["price"] == 100.0
        assert manual["value"] == 600.0
        assert len(holdings) == 2
        events = fetch_broker_sync_events(uid, connection["id"], limit=3)
        assert events[0]["action_type"] == "apply_matched"
        assert events[0]["matched_updates_count"] == 1
        assert events[0]["broker_add_count"] == 0
        assert events[0]["held_back_broker_count"] == 1
        assert events[0]["tracked_only_count"] == 1


def test_preview_trading212_shows_recent_sync_history(app, client, make_user, monkeypatch):
    uid, username, password = make_user(username="t212-sync-history")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        connection = upsert_broker_connection(
            user_id=uid,
            provider=PROVIDER_TRADING212,
            environment="live",
            label="Trading 212 ISA",
            access_mode="read_only",
            api_key_ciphertext=encrypt_trading212_credential("history-key"),
            api_secret_ciphertext=encrypt_trading212_credential("history-secret"),
            status="connected",
            last_tested_at="2026-06-09T08:00:00+00:00",
            external_account_id="ACC-HISTORY-1",
            external_account_currency="GBP",
            external_total_value=3200.0,
        )
        account_id = create_account(
            {
                "name": "Trading 212 ISA",
                "provider": "Trading 212",
                "wrapper_type": "ISA",
                "category": "investments",
                "tags": "",
                "current_value": 3000.0,
                "monthly_contribution": 0.0,
                "goal_value": 0.0,
                "valuation_mode": "holdings",
                "growth_mode": "rate",
                "growth_rate_override": 0.0,
                "owner": "joint",
                "linked_broker_connection_id": connection["id"],
                "is_active": 1,
                "notes": "",
                "last_updated": "2026-06-09",
            },
            uid,
        )
        add_holding(
            {
                "account_id": account_id,
                "holding_catalogue_id": None,
                "holding_name": "Apple Inc",
                "ticker": "AAPL_US_EQ",
                "asset_type": "stock",
                "bucket": "stocks",
                "value": 2400.0,
                "units": 10.0,
                "price": 240.0,
                "notes": "",
            },
            uid,
        )
        log_broker_sync_event(
            user_id=uid,
            connection_id=connection["id"],
            account_id=account_id,
            provider=PROVIDER_TRADING212,
            action_type="apply_matched",
            snapshot_at="2026-06-09T08:30:00+00:00",
            matched_updates_count=1,
            held_back_broker_count=1,
            tracked_only_count=1,
        )
        log_broker_sync_event(
            user_id=uid,
            connection_id=connection["id"],
            account_id=account_id,
            provider=PROVIDER_TRADING212,
            action_type="apply_broker_additions",
            snapshot_at="2026-06-09T08:45:00+00:00",
            broker_add_count=1,
            held_back_broker_count=1,
            tracked_only_count=1,
        )

    def fake_fetch_trading212_portfolio_snapshot(*, api_key, api_secret, environment):
        return {
            "environment": "live",
            "fetched_at": "2026-06-09T09:00:00+00:00",
            "summary": {
                "environment": "live",
                "account_id": "ACC-HISTORY-1",
                "currency": "GBP",
                "available_to_trade": 150.0,
                "cash_in_pies": 0.0,
                "cash_reserved_for_orders": 0.0,
                "investments_current_value": 2695.0,
                "investments_total_cost": 2500.0,
                "investments_unrealized_profit_loss": 195.0,
                "investments_realized_profit_loss": 0.0,
                "total_value": 2845.0,
                "fetched_at": "2026-06-09T09:00:00+00:00",
            },
            "positions": [
                {
                    "ticker": "AAPL_US_EQ",
                    "name": "Apple Inc",
                    "units": 11.0,
                    "price": 245.0,
                    "value": 2695.0,
                    "currency": "GBP",
                },
            ],
        }

    monkeypatch.setattr(
        "app.routes.settings.fetch_trading212_portfolio_snapshot",
        fake_fetch_trading212_portfolio_snapshot,
    )

    resp = client.post(
        f"/settings/trading212/{connection['id']}/preview",
        data={"account_id": str(account_id)},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Recent sync activity" in body
    assert "Applied matched updates" in body
    assert "Added broker-only positions" in body
    assert "Previewed snapshot" in body
    assert "Matched updates" in body
    assert "Held back" in body


def test_apply_trading212_reviewed_changes_requires_confirmation(app, client, make_user, monkeypatch):
    uid, username, password = make_user(username="t212-apply-review-confirm")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        connection = upsert_broker_connection(
            user_id=uid,
            provider=PROVIDER_TRADING212,
            environment="live",
            label="Trading 212 ISA",
            access_mode="read_only",
            api_key_ciphertext=encrypt_trading212_credential("confirm-key"),
            api_secret_ciphertext=encrypt_trading212_credential("confirm-secret"),
            status="connected",
            last_tested_at="2026-06-09T08:00:00+00:00",
            external_account_id="ACC-CONFIRM-1",
            external_account_currency="GBP",
            external_total_value=3200.0,
        )
        account_id = create_account(
            {
                "name": "Trading 212 ISA",
                "provider": "Trading 212",
                "wrapper_type": "ISA",
                "category": "investments",
                "tags": "",
                "current_value": 3000.0,
                "monthly_contribution": 0.0,
                "goal_value": 0.0,
                "valuation_mode": "holdings",
                "growth_mode": "rate",
                "growth_rate_override": 0.0,
                "owner": "joint",
                "linked_broker_connection_id": connection["id"],
                "is_active": 1,
                "notes": "",
                "last_updated": "2026-06-09",
            },
            uid,
        )
        add_holding(
            {
                "account_id": account_id,
                "holding_catalogue_id": None,
                "holding_name": "Apple Inc",
                "ticker": "AAPL_US_EQ",
                "asset_type": "stock",
                "bucket": "stocks",
                "value": 2400.0,
                "units": 10.0,
                "price": 240.0,
                "notes": "",
            },
            uid,
        )

    def fake_fetch_trading212_portfolio_snapshot(*, api_key, api_secret, environment):
        return {
            "environment": "live",
            "fetched_at": "2026-06-09T08:30:00+00:00",
            "summary": {
                "environment": "live",
                "account_id": "ACC-CONFIRM-1",
                "currency": "GBP",
                "available_to_trade": 150.0,
                "cash_in_pies": 0.0,
                "cash_reserved_for_orders": 0.0,
                "investments_current_value": 2695.0,
                "investments_total_cost": 2500.0,
                "investments_unrealized_profit_loss": 195.0,
                "investments_realized_profit_loss": 0.0,
                "total_value": 2845.0,
                "fetched_at": "2026-06-09T08:30:00+00:00",
            },
            "positions": [
                {
                    "ticker": "AAPL_US_EQ",
                    "name": "Apple Inc",
                    "units": 11.0,
                    "price": 245.0,
                    "value": 2695.0,
                    "currency": "GBP",
                },
            ],
        }

    monkeypatch.setattr(
        "app.routes.settings.fetch_trading212_portfolio_snapshot",
        fake_fetch_trading212_portfolio_snapshot,
    )

    resp = client.post(
        f"/settings/trading212/{connection['id']}/apply-reviewed",
        data={"account_id": str(account_id)},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Tick the confirmation box before applying reviewed Trading 212 changes." in body
    assert "Apply reviewed matched changes" in body

    with app.app_context():
        apple = next(row for row in fetch_holdings_for_account(account_id) if row["ticker"] == "AAPL_US_EQ")
        assert apple["units"] == 10.0
        assert apple["price"] == 240.0
        assert apple["value"] == 2400.0


def test_apply_trading212_reviewed_broker_additions_adds_only_clear_broker_only_positions(app, client, make_user, monkeypatch):
    uid, username, password = make_user(username="t212-apply-additions")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        connection = upsert_broker_connection(
            user_id=uid,
            provider=PROVIDER_TRADING212,
            environment="live",
            label="Trading 212 ISA",
            access_mode="read_only",
            api_key_ciphertext=encrypt_trading212_credential("additions-key"),
            api_secret_ciphertext=encrypt_trading212_credential("additions-secret"),
            status="connected",
            last_tested_at="2026-06-09T08:00:00+00:00",
            external_account_id="ACC-ADD-1",
            external_account_currency="GBP",
            external_total_value=3200.0,
        )
        account_id = create_account(
            {
                "name": "Trading 212 ISA",
                "provider": "Trading 212",
                "wrapper_type": "ISA",
                "category": "investments",
                "tags": "",
                "current_value": 3000.0,
                "monthly_contribution": 0.0,
                "goal_value": 0.0,
                "valuation_mode": "holdings",
                "growth_mode": "rate",
                "growth_rate_override": 0.0,
                "owner": "joint",
                "linked_broker_connection_id": connection["id"],
                "is_active": 1,
                "notes": "",
                "last_updated": "2026-06-09",
            },
            uid,
        )
        add_holding(
            {
                "account_id": account_id,
                "holding_catalogue_id": None,
                "holding_name": "Apple Inc",
                "ticker": "AAPL_US_EQ",
                "asset_type": "stock",
                "bucket": "stocks",
                "value": 2400.0,
                "units": 10.0,
                "price": 240.0,
                "notes": "",
            },
            uid,
        )
        add_holding(
            {
                "account_id": account_id,
                "holding_catalogue_id": None,
                "holding_name": "Vanguard FTSE Global All Cap",
                "ticker": "VAFTGAG",
                "asset_type": "fund",
                "bucket": "stocks",
                "value": 600.0,
                "units": 6.0,
                "price": 100.0,
                "notes": "",
            },
            uid,
        )

    def fake_fetch_trading212_portfolio_snapshot(*, api_key, api_secret, environment):
        assert api_key == "additions-key"
        assert api_secret == "additions-secret"
        assert environment == "live"
        return {
            "environment": "live",
            "fetched_at": "2026-06-09T08:30:00+00:00",
            "summary": {
                "environment": "live",
                "account_id": "ACC-ADD-1",
                "currency": "GBP",
                "available_to_trade": 150.0,
                "cash_in_pies": 0.0,
                "cash_reserved_for_orders": 0.0,
                "investments_current_value": 3200.0,
                "investments_total_cost": 2500.0,
                "investments_unrealized_profit_loss": 700.0,
                "investments_realized_profit_loss": 0.0,
                "total_value": 3350.0,
                "fetched_at": "2026-06-09T08:30:00+00:00",
            },
            "positions": [
                {
                    "ticker": "AAPL_US_EQ",
                    "name": "Apple Inc",
                    "units": 10.0,
                    "price": 240.0,
                    "value": 2400.0,
                    "currency": "GBP",
                },
                {
                    "ticker": "NEWFUND_EQ",
                    "name": "New fund",
                    "units": 1.0,
                    "price": 355.0,
                    "value": 355.0,
                    "currency": "GBP",
                },
                {
                    "ticker": "VWRP_LSE_EQ",
                    "name": "Vanguard FTSE All-World",
                    "units": 5.0,
                    "price": 119.0,
                    "value": 595.0,
                    "currency": "GBP",
                },
            ],
        }

    monkeypatch.setattr(
        "app.routes.settings.fetch_trading212_portfolio_snapshot",
        fake_fetch_trading212_portfolio_snapshot,
    )

    resp = client.post(
        f"/settings/trading212/{connection['id']}/apply-reviewed-additions",
        data={"account_id": str(account_id), "confirm_apply_broker_additions": "yes"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Added 1 reviewed Trading 212 broker-only position." in body
    assert "1 broker-only position stayed out for manual review and 1 tracked-only holding stayed untouched." in body

    with app.app_context():
        holdings = list(fetch_holdings_for_account(account_id))
        tickers = {row["ticker"] for row in holdings}
        assert "NEWFUND_EQ" in tickers
        assert "VWRP_LSE_EQ" not in tickers
        new_fund = next(row for row in holdings if row["ticker"] == "NEWFUND_EQ")
        assert new_fund["holding_name"] == "New fund"
        assert new_fund["asset_type"] == "fund"
        assert new_fund["bucket"] == "stocks"
        assert new_fund["units"] == 1.0
        assert new_fund["price"] == 355.0
        assert new_fund["value"] == 355.0
        events = fetch_broker_sync_events(uid, connection["id"], limit=3)
        assert events[0]["action_type"] == "apply_broker_additions"
        assert events[0]["matched_updates_count"] == 0
        assert events[0]["broker_add_count"] == 1
        assert events[0]["held_back_broker_count"] == 1
        assert events[0]["tracked_only_count"] == 1


def test_resolve_trading212_reviewed_possible_match_updates_selected_holding(app, client, make_user, monkeypatch):
    uid, username, password = make_user(username="t212-resolve-possible-match")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        connection = upsert_broker_connection(
            user_id=uid,
            provider=PROVIDER_TRADING212,
            environment="live",
            label="Trading 212 ISA",
            access_mode="read_only",
            api_key_ciphertext=encrypt_trading212_credential("resolve-key"),
            api_secret_ciphertext=encrypt_trading212_credential("resolve-secret"),
            status="connected",
            last_tested_at="2026-06-09T08:00:00+00:00",
            external_account_id="ACC-RESOLVE-1",
            external_account_currency="GBP",
            external_total_value=3200.0,
        )
        account_id = create_account(
            {
                "name": "Trading 212 ISA",
                "provider": "Trading 212",
                "wrapper_type": "ISA",
                "category": "investments",
                "tags": "",
                "current_value": 3000.0,
                "monthly_contribution": 0.0,
                "goal_value": 0.0,
                "valuation_mode": "holdings",
                "growth_mode": "rate",
                "growth_rate_override": 0.0,
                "owner": "joint",
                "linked_broker_connection_id": connection["id"],
                "is_active": 1,
                "notes": "",
                "last_updated": "2026-06-09",
            },
            uid,
        )
        add_holding(
            {
                "account_id": account_id,
                "holding_catalogue_id": None,
                "holding_name": "Acme Income Growth",
                "ticker": "ACME_HINT",
                "asset_type": "fund",
                "bucket": "stocks",
                "value": 550.0,
                "units": 5.0,
                "price": 110.0,
                "notes": "",
            },
            uid,
        )
        add_holding(
            {
                "account_id": account_id,
                "holding_catalogue_id": None,
                "holding_name": "Apple Inc",
                "ticker": "AAPL_US_EQ",
                "asset_type": "stock",
                "bucket": "stocks",
                "value": 2400.0,
                "units": 10.0,
                "price": 240.0,
                "notes": "",
            },
            uid,
        )
        target_holding_id = next(row for row in fetch_holdings_for_account(account_id) if row["ticker"] == "ACME_HINT")["id"]

    def fake_fetch_trading212_portfolio_snapshot(*, api_key, api_secret, environment):
        assert api_key == "resolve-key"
        assert api_secret == "resolve-secret"
        assert environment == "live"
        return {
            "environment": "live",
            "fetched_at": "2026-06-09T08:30:00+00:00",
            "summary": {
                "environment": "live",
                "account_id": "ACC-RESOLVE-1",
                "currency": "GBP",
                "available_to_trade": 150.0,
                "cash_in_pies": 0.0,
                "cash_reserved_for_orders": 0.0,
                "investments_current_value": 3050.0,
                "investments_total_cost": 2500.0,
                "investments_unrealized_profit_loss": 550.0,
                "investments_realized_profit_loss": 0.0,
                "total_value": 3200.0,
                "fetched_at": "2026-06-09T08:30:00+00:00",
            },
            "positions": [
                {
                    "ticker": "AAPL_US_EQ",
                    "name": "Apple Inc",
                    "units": 10.0,
                    "price": 240.0,
                    "value": 2400.0,
                    "currency": "GBP",
                },
                {
                    "ticker": "ACMEG_EQ",
                    "name": "Acme Global Growth",
                    "units": 4.0,
                    "price": 125.0,
                    "value": 500.0,
                    "currency": "GBP",
                },
            ],
        }

    monkeypatch.setattr(
        "app.routes.settings.fetch_trading212_portfolio_snapshot",
        fake_fetch_trading212_portfolio_snapshot,
    )

    resp = client.post(
        f"/settings/trading212/{connection['id']}/resolve-possible-match",
        data={
            "account_id": str(account_id),
            "preview_key": "0:ACMEG_EQ:Acme Global Growth",
            "selected_holding_id": str(target_holding_id),
            "confirm_resolve_possible_match": "yes",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Resolved 1 reviewed possible match for Acme Income Growth." in body
    assert "0 broker-only positions and 0 tracked-only holdings stayed untouched." in body

    with app.app_context():
        holdings = list(fetch_holdings_for_account(account_id))
        resolved = next(row for row in holdings if row["id"] == target_holding_id)
        assert resolved["units"] == 4.0
        assert resolved["price"] == 125.0
        assert resolved["value"] == 500.0
        events = fetch_broker_sync_events(uid, connection["id"], limit=3)
        assert events[0]["action_type"] == "resolve_possible_match"
        assert events[0]["matched_updates_count"] == 1
        assert events[0]["broker_add_count"] == 0
        assert events[0]["held_back_broker_count"] == 0
        assert events[0]["tracked_only_count"] == 0


def test_apply_trading212_reviewed_broker_additions_requires_confirmation(app, client, make_user, monkeypatch):
    uid, username, password = make_user(username="t212-apply-additions-confirm")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        connection = upsert_broker_connection(
            user_id=uid,
            provider=PROVIDER_TRADING212,
            environment="live",
            label="Trading 212 ISA",
            access_mode="read_only",
            api_key_ciphertext=encrypt_trading212_credential("additions-confirm-key"),
            api_secret_ciphertext=encrypt_trading212_credential("additions-confirm-secret"),
            status="connected",
            last_tested_at="2026-06-09T08:00:00+00:00",
            external_account_id="ACC-ADD-CONFIRM-1",
            external_account_currency="GBP",
            external_total_value=3200.0,
        )
        account_id = create_account(
            {
                "name": "Trading 212 ISA",
                "provider": "Trading 212",
                "wrapper_type": "ISA",
                "category": "investments",
                "tags": "",
                "current_value": 3000.0,
                "monthly_contribution": 0.0,
                "goal_value": 0.0,
                "valuation_mode": "holdings",
                "growth_mode": "rate",
                "growth_rate_override": 0.0,
                "owner": "joint",
                "linked_broker_connection_id": connection["id"],
                "is_active": 1,
                "notes": "",
                "last_updated": "2026-06-09",
            },
            uid,
        )
        add_holding(
            {
                "account_id": account_id,
                "holding_catalogue_id": None,
                "holding_name": "Apple Inc",
                "ticker": "AAPL_US_EQ",
                "asset_type": "stock",
                "bucket": "stocks",
                "value": 2400.0,
                "units": 10.0,
                "price": 240.0,
                "notes": "",
            },
            uid,
        )

    def fake_fetch_trading212_portfolio_snapshot(*, api_key, api_secret, environment):
        return {
            "environment": "live",
            "fetched_at": "2026-06-09T08:30:00+00:00",
            "summary": {
                "environment": "live",
                "account_id": "ACC-ADD-CONFIRM-1",
                "currency": "GBP",
                "available_to_trade": 150.0,
                "cash_in_pies": 0.0,
                "cash_reserved_for_orders": 0.0,
                "investments_current_value": 2400.0,
                "investments_total_cost": 2500.0,
                "investments_unrealized_profit_loss": -100.0,
                "investments_realized_profit_loss": 0.0,
                "total_value": 2550.0,
                "fetched_at": "2026-06-09T08:30:00+00:00",
            },
            "positions": [
                {
                    "ticker": "AAPL_US_EQ",
                    "name": "Apple Inc",
                    "units": 10.0,
                    "price": 240.0,
                    "value": 2400.0,
                    "currency": "GBP",
                },
                {
                    "ticker": "NEWFUND_EQ",
                    "name": "New fund",
                    "units": 1.0,
                    "price": 355.0,
                    "value": 355.0,
                    "currency": "GBP",
                },
            ],
        }

    monkeypatch.setattr(
        "app.routes.settings.fetch_trading212_portfolio_snapshot",
        fake_fetch_trading212_portfolio_snapshot,
    )

    resp = client.post(
        f"/settings/trading212/{connection['id']}/apply-reviewed-additions",
        data={"account_id": str(account_id)},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Tick the confirmation box before adding reviewed broker-only positions." in body
    assert "Add reviewed broker-only positions" in body

    with app.app_context():
        holdings = list(fetch_holdings_for_account(account_id))
        assert {row['ticker'] for row in holdings} == {"AAPL_US_EQ"}


def test_linked_preview_normalises_trading212_alias_tickers_and_etf_names(app, client, make_user, monkeypatch):
    uid, username, password = make_user(username="t212-linked-preview-aliases")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        connection = upsert_broker_connection(
            user_id=uid,
            provider=PROVIDER_TRADING212,
            environment="live",
            label="Trading 212 ISA",
            access_mode="read_only",
            api_key_ciphertext=encrypt_trading212_credential("alias-preview-key"),
            api_secret_ciphertext=encrypt_trading212_credential("alias-preview-secret"),
            status="connected",
            last_tested_at="2026-06-09T07:15:00+00:00",
            external_account_id="ACC-ALIAS-123",
            external_account_currency="GBP",
            external_total_value=9150.0,
        )
        account_id = create_account(
            {
                "name": "Trading 212 ISA",
                "provider": "Trading 212",
                "wrapper_type": "ISA",
                "category": "investments",
                "tags": "",
                "current_value": 9150.0,
                "monthly_contribution": 0.0,
                "goal_value": 0.0,
                "valuation_mode": "holdings",
                "growth_mode": "rate",
                "growth_rate_override": 0.0,
                "owner": "joint",
                "linked_broker_connection_id": connection["id"],
                "is_active": 1,
                "notes": "",
                "last_updated": "2026-06-09",
            },
            uid,
        )
        add_holding(
            {
                "account_id": account_id,
                "holding_catalogue_id": None,
                "holding_name": "Vanguard FTSE Developed World UCITS ETF USD Accumulation",
                "ticker": "VHVG",
                "asset_type": "fund",
                "bucket": "stocks",
                "value": 5000.0,
                "units": 100.0,
                "price": 50.0,
                "notes": "",
            },
            uid,
        )
        add_holding(
            {
                "account_id": account_id,
                "holding_catalogue_id": None,
                "holding_name": "Vanguard FTSE Emerging Markets UCITS ETF USD Accumulation",
                "ticker": "VFEG",
                "asset_type": "fund",
                "bucket": "stocks",
                "value": 4000.0,
                "units": 80.0,
                "price": 50.0,
                "notes": "",
            },
            uid,
        )

    def fake_fetch_trading212_portfolio_snapshot(*, api_key, api_secret, environment):
        assert api_key == "alias-preview-key"
        assert api_secret == "alias-preview-secret"
        assert environment == "live"
        return {
            "environment": "live",
            "fetched_at": "2026-06-09T07:20:00+00:00",
            "summary": {
                "environment": "live",
                "account_id": "ACC-ALIAS-123",
                "currency": "GBP",
                "available_to_trade": 150.0,
                "cash_in_pies": 0.0,
                "cash_reserved_for_orders": 0.0,
                "investments_current_value": 9150.0,
                "investments_total_cost": 8000.0,
                "investments_unrealized_profit_loss": 1150.0,
                "investments_realized_profit_loss": 0.0,
                "total_value": 9300.0,
                "fetched_at": "2026-06-09T07:20:00+00:00",
            },
            "positions": [
                {
                    "ticker": "VHVGL_EQ",
                    "name": "Vanguard FTSE Developed World (Acc)",
                    "units": 100.0,
                    "price": 51.0,
                    "value": 5100.0,
                    "currency": "GBP",
                },
                {
                    "ticker": "VFEGL_EQ",
                    "name": "Vanguard FTSE Emerging Markets (Acc)",
                    "units": 80.0,
                    "price": 50.625,
                    "value": 4050.0,
                    "currency": "GBP",
                },
            ],
        }

    monkeypatch.setattr(
        "app.routes.settings.fetch_trading212_portfolio_snapshot",
        fake_fetch_trading212_portfolio_snapshot,
    )

    resp = client.post(
        f"/settings/trading212/{connection['id']}/preview",
        data={"account_id": str(account_id)},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Matched holdings to update" in body
    assert ">2<" in body
    assert "Broker-only positions to add" in body
    assert ">0<" in body
    assert "Tracked-only holdings to review" in body
    assert "No extra tracked holdings were left unmatched." in body
    assert "VHVGL_EQ" in body
    assert "VFEGL_EQ" in body
    assert "Vanguard FTSE Developed World UCITS ETF USD Accumulation" in body
    assert "Vanguard FTSE Emerging Markets UCITS ETF USD Accumulation" in body
    assert "Possible tracked matches" not in body


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


def test_preview_trading212_snapshot_renders_matches_without_writing_data(app, client, make_user, monkeypatch):
    uid, username, password = make_user(username="t212-preview")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        connection = upsert_broker_connection(
            user_id=uid,
            provider=PROVIDER_TRADING212,
            environment="live",
            label="Trading 212 ISA",
            access_mode="read_only",
            api_key_ciphertext=encrypt_trading212_credential("live-preview-key"),
            api_secret_ciphertext=encrypt_trading212_credential("live-preview-secret"),
            status="connected",
            last_tested_at="2026-06-07T18:10:00+00:00",
            external_account_id="ACC-123",
            external_account_currency="GBP",
            external_total_value=3100.0,
        )
        assert connection is not None
        account_id = create_account(
            {
                "name": "Trading 212 ISA",
                "provider": "Trading 212",
                "wrapper_type": "ISA",
                "category": "investments",
                "tags": "",
                "current_value": 3000.0,
                "monthly_contribution": 0.0,
                "goal_value": 0.0,
                "valuation_mode": "holdings",
                "growth_mode": "rate",
                "growth_rate_override": 0.0,
                "owner": "joint",
                "is_active": 1,
                "notes": "",
                "last_updated": "2026-06-07",
            },
            uid,
        )
        add_holding(
            {
                "account_id": account_id,
                "holding_catalogue_id": None,
                "holding_name": "Apple Inc",
                "ticker": "AAPL_US_EQ",
                "asset_type": "stock",
                "bucket": "stocks",
                "value": 2400.0,
                "units": 10.0,
                "price": 240.0,
                "notes": "",
            },
            uid,
        )
        add_holding(
            {
                "account_id": account_id,
                "holding_catalogue_id": None,
                "holding_name": "Vanguard FTSE Global All Cap",
                "ticker": "VAFTGAG",
                "asset_type": "fund",
                "bucket": "stocks",
                "value": 600.0,
                "units": 5.0,
                "price": 120.0,
                "notes": "",
            },
            uid,
        )
        add_holding(
            {
                "account_id": account_id,
                "holding_catalogue_id": None,
                "holding_name": "Vanguard FTSE Emerging Markets ETF",
                "ticker": "VFEM",
                "asset_type": "fund",
                "bucket": "stocks",
                "value": 325.0,
                "units": 2.9,
                "price": 112.0,
                "notes": "",
            },
            uid,
        )
        add_holding(
            {
                "account_id": account_id,
                "holding_catalogue_id": None,
                "holding_name": "Vanguard FTSE Developed World ex-U.K. Equity Index Fund",
                "ticker": "DEVWORLD",
                "asset_type": "fund",
                "bucket": "stocks",
                "value": 118.0,
                "units": 1.0,
                "price": 118.0,
                "notes": "",
            },
            uid,
        )
        add_holding(
            {
                "account_id": account_id,
                "holding_catalogue_id": None,
                "holding_name": "Cash Reserve Jar",
                "ticker": "CASHJAR",
                "asset_type": "cash",
                "bucket": "cash",
                "value": 80.0,
                "units": 1.0,
                "price": 80.0,
                "notes": "",
            },
            uid,
        )

    def fake_fetch_trading212_portfolio_snapshot(*, api_key, api_secret, environment):
        assert api_key == "live-preview-key"
        assert api_secret == "live-preview-secret"
        assert environment == "live"
        return {
            "environment": "live",
            "fetched_at": "2026-06-08T09:30:00+00:00",
            "summary": {
                "environment": "live",
                "account_id": "ACC-123",
                "currency": "GBP",
                "available_to_trade": 150.0,
                "cash_in_pies": 25.0,
                "cash_reserved_for_orders": 5.0,
                "investments_current_value": 2950.0,
                "investments_total_cost": 2500.0,
                "investments_unrealized_profit_loss": 450.0,
                "investments_realized_profit_loss": 0.0,
                "total_value": 3100.0,
                "fetched_at": "2026-06-08T09:30:00+00:00",
            },
            "positions": [
                {
                    "ticker": "AAPL_US_EQ",
                    "name": "Apple Inc",
                    "units": 10.0,
                    "price": 245.0,
                    "value": 2450.0,
                    "currency": "GBP",
                },
                {
                    "ticker": "VWRP_LSE_EQ",
                    "name": "Vanguard FTSE All-World",
                    "units": 4.0,
                    "price": 125.0,
                    "value": 500.0,
                    "currency": "GBP",
                },
            ],
        }

    monkeypatch.setattr(
        "app.routes.settings.fetch_trading212_portfolio_snapshot",
        fake_fetch_trading212_portfolio_snapshot,
    )

    with app.app_context():
        before_rows = fetch_broker_connections(uid, provider=PROVIDER_TRADING212)
        before_count = len(before_rows)

    resp = client.post(
        f"/settings/trading212/{connection['id']}/preview",
        data={},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="ignore")
    assert "Preview holdings snapshot" in body
    assert "Nothing in SteadyPlan has been changed." in body
    assert "Matched holdings" in body
    assert "Broker-only positions" in body
    assert "Tracked holdings not seen in this snapshot" in body
    assert "Apple Inc" in body
    assert "Vanguard FTSE All-World" in body
    assert "diff +50.00" in body
    assert "Possible tracked matches" in body
    assert "Vanguard FTSE Global All Cap" in body
    assert "Trading 212 ISA" in body
    assert "Name clues" in body
    assert "shared terms:" not in body
    assert "trading212-mobile-position-list" in body
    assert "trading212-mobile-position-card" in body
    assert "trading212-position-facts" in body
    assert "trading212-desktop-only" in body
    assert "trading212-mobile-only" in body
    assert "trading212-mobile-candidate-overflow" in body
    assert "Show 1 more possible match" in body
    assert "Useful for spotting holdings that are probably stale/manual versus ones that still need a careful rematch on this linked account." in body
    assert "Needs rematch" in body
    assert "Likely stale/manual" in body
    assert "Similar broker snapshot rows exist, so this tracked holding likely needs a careful rematch rather than a fresh add." in body
    assert "No similar broker snapshot row was found, so this is more likely an older manual entry, a sold position, or something still tracked outside this API snapshot." in body
    assert "Next step: compare this holding with the broker clue first, then use the reviewed match flow if it is genuinely the same position." in body
    assert "Next step: review whether this holding should stay tracked manually, be archived, or be removed after you confirm it is no longer in the broker account." in body
    assert "Cash Reserve Jar" in body
    assert "Proposed apply plan" not in body

    with app.app_context():
        after_rows = fetch_broker_connections(uid, provider=PROVIDER_TRADING212)
        assert len(after_rows) == before_count
        row = after_rows[0]
        assert row is not None
        assert row["status"] == "connected"
        assert row["last_error"] is None
        assert row["external_total_value"] == 3100.0


def test_broker_connections_migration_drops_env_uniqueness_for_multiple_live_accounts(app, make_user):
    uid, _, _ = make_user(username="t212-migration", password="password123")

    from app.models import get_connection
    from app.models.schema import init_db

    with app.app_context():
        with get_connection() as conn:
            conn.execute("DELETE FROM schema_migrations WHERE name = 'v11_broker_connections_multi_account'")
            conn.execute("DROP TABLE IF EXISTS broker_connections")
            conn.execute(
                """
                CREATE TABLE broker_connections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    provider TEXT NOT NULL,
                    label TEXT NOT NULL,
                    environment TEXT NOT NULL DEFAULT 'live',
                    access_mode TEXT NOT NULL DEFAULT 'read_only',
                    api_key_ciphertext TEXT NOT NULL,
                    api_secret_ciphertext TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'unverified',
                    last_error TEXT,
                    last_tested_at TEXT,
                    external_account_id TEXT,
                    external_account_currency TEXT,
                    external_total_value REAL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(user_id, provider, environment)
                )
                """
            )
            conn.execute(
                """
                INSERT INTO broker_connections (
                    user_id, provider, label, environment, access_mode,
                    api_key_ciphertext, api_secret_ciphertext, status,
                    external_account_id, external_account_currency, external_total_value
                ) VALUES (?, 'trading212', 'Legacy ISA', 'live', 'read_only', ?, ?, 'connected', 'LEGACY-1', 'GBP', 123.45)
                """,
                (
                    uid,
                    encrypt_trading212_credential("legacy-key"),
                    encrypt_trading212_credential("legacy-secret"),
                ),
            )
            conn.commit()

        init_db()

        with get_connection() as conn:
            rows = conn.execute(
                "SELECT label, environment, external_account_id FROM broker_connections WHERE user_id = ? ORDER BY id ASC",
                (uid,),
            ).fetchall()
            assert len(rows) == 1
            assert rows[0]["label"] == "Legacy ISA"
            assert rows[0]["environment"] == "live"
            assert rows[0]["external_account_id"] == "LEGACY-1"
            conn.execute(
                """
                INSERT INTO broker_connections (
                    user_id, provider, label, environment, access_mode,
                    api_key_ciphertext, api_secret_ciphertext, status,
                    external_account_id, external_account_currency, external_total_value
                ) VALUES (?, 'trading212', 'Legacy Invest', 'live', 'read_only', ?, ?, 'connected', 'LEGACY-2', 'GBP', 456.78)
                """,
                (
                    uid,
                    encrypt_trading212_credential("second-key"),
                    encrypt_trading212_credential("second-secret"),
                ),
            )
            conn.commit()
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM broker_connections WHERE user_id = ? AND provider = 'trading212' AND environment = 'live'",
                (uid,),
            ).fetchone()["n"]
            assert count == 2


def test_accounts_migration_adds_linked_broker_connection_column(app):
    from app.models import get_connection
    from app.models.schema import init_db

    with app.app_context():
        with get_connection() as conn:
            conn.execute("DROP TABLE IF EXISTS accounts")
            conn.execute(
                """
                CREATE TABLE accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    provider TEXT,
                    wrapper_type TEXT,
                    category TEXT,
                    tags TEXT DEFAULT '',
                    current_value REAL DEFAULT 0,
                    monthly_contribution REAL DEFAULT 0,
                    pension_contribution_day INTEGER DEFAULT 0,
                    goal_value REAL,
                    valuation_mode TEXT DEFAULT 'manual',
                    growth_mode TEXT DEFAULT 'default',
                    growth_rate_override REAL,
                    owner TEXT,
                    is_active INTEGER DEFAULT 1,
                    notes TEXT,
                    last_updated TEXT,
                    employer_contribution REAL DEFAULT 0,
                    contribution_method TEXT DEFAULT 'standard',
                    annual_fee_pct REAL DEFAULT 0,
                    platform_fee_pct REAL DEFAULT 0,
                    platform_fee_flat REAL DEFAULT 0,
                    platform_fee_cap REAL DEFAULT 0,
                    fund_fee_pct REAL DEFAULT 0,
                    contribution_fee_pct REAL DEFAULT 0,
                    uninvested_cash REAL DEFAULT 0,
                    cash_interest_rate REAL DEFAULT 0,
                    interest_payment_day INTEGER DEFAULT 0,
                    include_in_budget INTEGER DEFAULT 1,
                    pre_salary INTEGER DEFAULT 0
                )
                """
            )
            conn.commit()

        init_db()

        with get_connection() as conn:
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(accounts)").fetchall()
            }
            assert "linked_broker_connection_id" in columns


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


def test_fetch_trading212_positions_normalises_response(app, monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["authorization"] = request.headers.get("Authorization")
        captured["timeout"] = timeout
        return _FakeHttpResponse(
            [
                {
                    "averagePricePaid": 101.25,
                    "createdAt": "2026-06-08T09:00:00Z",
                    "currentPrice": 123.45,
                    "instrument": {
                        "ticker": "VWRP_LSE_EQ",
                        "name": "Vanguard FTSE All-World",
                        "currencyCode": "GBP",
                    },
                    "quantity": 4,
                    "quantityAvailableForTrading": 3,
                    "quantityInPies": 1,
                }
            ]
        )

    monkeypatch.setattr("app.services.trading212.urllib.request.urlopen", fake_urlopen)

    with app.app_context():
        payload = fetch_trading212_positions(
            api_key="demo-key",
            api_secret="demo-secret",
            environment="demo",
        )

    expected_auth = "Basic " + base64.b64encode(b"demo-key:demo-secret").decode("ascii")
    assert captured["url"] == "https://demo.trading212.com/api/v0/equity/positions"
    assert captured["authorization"] == expected_auth
    assert captured["timeout"] == 12
    assert payload["environment"] == "demo"
    assert len(payload["positions"]) == 1
    row = payload["positions"][0]
    assert row["ticker"] == "VWRP_LSE_EQ"
    assert row["name"] == "Vanguard FTSE All-World"
    assert row["units"] == 4.0
    assert row["price"] == 123.45
    assert row["value"] == 493.8
    assert row["average_price_paid"] == 101.25
    assert row["currency"] == "GBP"
    assert row["quantity_available_for_trading"] == 3.0
    assert row["quantity_in_pies"] == 1.0


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
