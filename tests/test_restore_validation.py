import json
import io

import pytest

from app.services.restore_validation import validate_restore_backup_json


def _login(client, username, password):
    resp = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )
    assert resp.status_code == 200


def _count_rows(app):
    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            tables = [
                "accounts",
                "holdings",
                "holding_catalogue",
                "goals",
                "debts",
                "budget_sections",
                "budget_items",
                "budget_entries",
                "monthly_snapshots",
                "portfolio_daily_snapshots",
                "account_daily_snapshots",
                "monthly_reviews",
                "monthly_review_items",
                "cash_flow_events",
                "isa_contributions",
                "pension_contributions",
                "dividend_records",
                "cgt_disposals",
                "pension_carry_forward",
                "allowance_tracking",
                "contribution_overrides",
                "premium_bonds_prizes",
            ]
            out = {}
            for t in tables:
                out[t] = int(conn.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()["c"])
            return out


@pytest.fixture
def exported_json_bytes(app, client, make_user):
    uid, username, password = make_user(username="restore-validate", password="password123")
    _login(client, username, password)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            a1 = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution)
                VALUES (?, 'A1', 'isa', 1000, 100)
                """,
                (uid,),
            ).lastrowid
            a2 = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution)
                VALUES (?, 'A2', 'cash', 2000, 200)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO cash_flow_events (user_id, account_id, event_date, amount, kind, note, counterparty_account_id)
                VALUES (?, ?, '2026-06-15', 50, 'transfer', 'test', ?)
                """,
                (uid, a1, a2),
            )
            conn.execute(
                """
                INSERT INTO allowance_tracking (user_id, tax_year, isa_used, lisa_used, notes)
                VALUES (?, '2026-27', 123, 45, 'mine')
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get("/settings/export.json")
    assert resp.status_code == 200
    return resp.data


def test_restore_validation_valid_export_passes_and_no_db_writes(app, exported_json_bytes):
    before = _count_rows(app)
    result = validate_restore_backup_json(exported_json_bytes)
    after = _count_rows(app)

    assert result["valid"] is True
    assert result["export_schema_version"] == 1
    assert result["exported_at"]
    assert result["counts"]["accounts"] >= 2
    assert result["counts"]["planning"]["allowance_tracking"] >= 1
    assert result["errors"] == []
    assert before == after


def test_restore_validation_corrupt_json_rejected_and_no_db_writes(app):
    before = _count_rows(app)
    result = validate_restore_backup_json(b"{")
    after = _count_rows(app)
    assert result["valid"] is False
    assert any("Invalid JSON" in e for e in result["errors"])
    assert before == after


def test_restore_validation_missing_meta_rejected(exported_json_bytes):
    payload = json.loads(exported_json_bytes.decode("utf-8"))
    payload.pop("meta", None)
    result = validate_restore_backup_json(json.dumps(payload).encode("utf-8"))
    assert result["valid"] is False
    assert any("meta" in e for e in result["errors"])


def test_restore_validation_missing_schema_version_rejected(exported_json_bytes):
    payload = json.loads(exported_json_bytes.decode("utf-8"))
    payload["meta"].pop("export_schema_version", None)
    result = validate_restore_backup_json(json.dumps(payload).encode("utf-8"))
    assert result["valid"] is False
    assert any("Missing meta.export_schema_version" in e for e in result["errors"])


def test_restore_validation_unsupported_future_schema_rejected(exported_json_bytes):
    payload = json.loads(exported_json_bytes.decode("utf-8"))
    payload["meta"]["export_schema_version"] = 999
    result = validate_restore_backup_json(json.dumps(payload).encode("utf-8"))
    assert result["valid"] is False
    assert any("Unsupported export_schema_version" in e for e in result["errors"])


def test_restore_validation_missing_required_section_rejected(exported_json_bytes):
    payload = json.loads(exported_json_bytes.decode("utf-8"))
    payload.pop("accounts", None)
    result = validate_restore_backup_json(json.dumps(payload).encode("utf-8"))
    assert result["valid"] is False
    assert any("Missing required top-level section: 'accounts'" in e for e in result["errors"])


def test_restore_validation_invalid_field_type_rejected(exported_json_bytes):
    payload = json.loads(exported_json_bytes.decode("utf-8"))
    payload["accounts"] = {}
    result = validate_restore_backup_json(json.dumps(payload).encode("utf-8"))
    assert result["valid"] is False
    assert any("Invalid 'accounts'" in e for e in result["errors"])


def test_restore_validation_invalid_account_reference_rejected(exported_json_bytes):
    payload = json.loads(exported_json_bytes.decode("utf-8"))
    if payload["holdings"]:
        payload["holdings"][0]["account_id"] = 999999
    else:
        payload["holdings"].append({"id": 1, "account_id": 999999})
    result = validate_restore_backup_json(json.dumps(payload).encode("utf-8"))
    assert result["valid"] is False
    assert any("holdings[].account_id" in e and "missing account" in e for e in result["errors"])


def test_restore_validation_invalid_cash_flow_counterparty_reference_rejected(exported_json_bytes):
    payload = json.loads(exported_json_bytes.decode("utf-8"))
    payload["planning"]["cash_flow_events"].append(
        {
            "id": 999,
            "account_id": payload["accounts"][0]["id"],
            "event_date": "2026-06-15",
            "amount": 10,
            "kind": "transfer",
            "note": "bad",
            "counterparty_account_id": 123456789,
        }
    )
    result = validate_restore_backup_json(json.dumps(payload).encode("utf-8"))
    assert result["valid"] is False
    assert any("counterparty_account_id" in e and "missing account" in e for e in result["errors"])


def test_restore_validation_invalid_isa_contributions_account_reference_rejected(exported_json_bytes):
    payload = json.loads(exported_json_bytes.decode("utf-8"))
    payload["planning"]["isa_contributions"].append(
        {"id": 1, "account_id": 999999, "amount": 10, "contribution_date": "2026-06-01"}
    )
    result = validate_restore_backup_json(json.dumps(payload).encode("utf-8"))
    assert result["valid"] is False
    assert any("planning.isa_contributions[].account_id" in e and "missing account" in e for e in result["errors"])


def test_restore_validation_invalid_dividend_records_account_reference_rejected(exported_json_bytes):
    payload = json.loads(exported_json_bytes.decode("utf-8"))
    payload["planning"]["dividend_records"].append(
        {"id": 1, "account_id": 999999, "amount": 3, "dividend_date": "2026-06-01"}
    )
    result = validate_restore_backup_json(json.dumps(payload).encode("utf-8"))
    assert result["valid"] is False
    assert any("planning.dividend_records[].account_id" in e and "missing account" in e for e in result["errors"])


def test_restore_validation_invalid_pension_contributions_account_reference_rejected(exported_json_bytes):
    payload = json.loads(exported_json_bytes.decode("utf-8"))
    payload["planning"]["pension_contributions"].append(
        {"id": 1, "account_id": 999999, "amount": 20, "contribution_date": "2026-06-01", "kind": "personal"}
    )
    result = validate_restore_backup_json(json.dumps(payload).encode("utf-8"))
    assert result["valid"] is False
    assert any("planning.pension_contributions[].account_id" in e and "missing account" in e for e in result["errors"])


def test_restore_validation_invalid_premium_bonds_prizes_account_reference_rejected(exported_json_bytes):
    payload = json.loads(exported_json_bytes.decode("utf-8"))
    payload["planning"]["premium_bonds_prizes"].append(
        {"id": 1, "account_id": 999999, "month_key": "2026-05", "prize_amount": 25}
    )
    result = validate_restore_backup_json(json.dumps(payload).encode("utf-8"))
    assert result["valid"] is False
    assert any(
        "planning.premium_bonds_prizes[].account_id" in e and "missing account" in e
        for e in result["errors"]
    )


def test_restore_validation_invalid_monthly_review_items_references_rejected(exported_json_bytes):
    payload = json.loads(exported_json_bytes.decode("utf-8"))
    payload["history"]["monthly_review_items"].append(
        {"id": 1, "review_id": 999999, "account_id": payload["accounts"][0]["id"]}
    )
    result = validate_restore_backup_json(json.dumps(payload).encode("utf-8"))
    assert result["valid"] is False
    assert any("history.monthly_review_items[].review_id" in e and "missing monthly review" in e for e in result["errors"])


def test_restore_validation_account_linked_references_valid_pass(exported_json_bytes):
    payload = json.loads(exported_json_bytes.decode("utf-8"))
    aid = payload["accounts"][0]["id"]

    payload["planning"]["isa_contributions"].append(
        {"id": 1, "account_id": aid, "amount": 10, "contribution_date": "2026-06-01"}
    )
    payload["planning"]["dividend_records"].append(
        {"id": 1, "account_id": aid, "amount": 3, "dividend_date": "2026-06-01"}
    )

    payload["history"]["monthly_reviews"].append({"id": 123, "month_key": "2026-05"})
    payload["history"]["monthly_review_items"].append({"id": 1, "review_id": 123, "account_id": aid})

    result = validate_restore_backup_json(json.dumps(payload).encode("utf-8"))
    assert result["valid"] is True


def test_restore_validation_duplicate_holding_catalogue_ticker_rejected(exported_json_bytes):
    payload = json.loads(exported_json_bytes.decode("utf-8"))
    payload["holding_catalogue"] = [
        {"id": 1, "holding_name": "Global ETF", "ticker": "VWRA"},
        {"id": 2, "holding_name": "Global ETF 2", "ticker": "VWRA"},
    ]
    result = validate_restore_backup_json(json.dumps(payload).encode("utf-8"))
    assert result["valid"] is False
    assert any("Duplicate holding_catalogue[].ticker" in e for e in result["errors"])


def test_restore_validation_duplicate_monthly_review_month_key_rejected(exported_json_bytes):
    payload = json.loads(exported_json_bytes.decode("utf-8"))
    payload["history"]["monthly_reviews"] = [
        {"id": 1, "month_key": "2026-05"},
        {"id": 2, "month_key": "2026-05"},
    ]
    result = validate_restore_backup_json(json.dumps(payload).encode("utf-8"))
    assert result["valid"] is False
    assert any("Duplicate history.monthly_reviews[].month_key" in e for e in result["errors"])


def test_restore_validation_duplicate_pension_carry_forward_tax_year_rejected(exported_json_bytes):
    payload = json.loads(exported_json_bytes.decode("utf-8"))
    payload["planning"]["pension_carry_forward"] = [
        {"id": 1, "tax_year": "2025-26", "unused_allowance": 1},
        {"id": 2, "tax_year": "2025-26", "unused_allowance": 2},
    ]
    result = validate_restore_backup_json(json.dumps(payload).encode("utf-8"))
    assert result["valid"] is False
    assert any("Duplicate planning.pension_carry_forward[].tax_year" in e for e in result["errors"])


def test_restore_validation_uniqueness_distinct_values_pass(exported_json_bytes):
    payload = json.loads(exported_json_bytes.decode("utf-8"))
    payload["holding_catalogue"] = [
        {"id": 1, "holding_name": "Global ETF", "ticker": "VWRA"},
        {"id": 2, "holding_name": "UK ETF", "ticker": "VUKG"},
    ]
    payload["history"]["monthly_reviews"] = [
        {"id": 1, "month_key": "2026-05"},
        {"id": 2, "month_key": "2026-06"},
    ]
    payload["planning"]["pension_carry_forward"] = [
        {"id": 1, "tax_year": "2024-25", "unused_allowance": 100},
        {"id": 2, "tax_year": "2025-26", "unused_allowance": 200},
    ]
    result = validate_restore_backup_json(json.dumps(payload).encode("utf-8"))
    assert result["valid"] is True


def test_restore_validation_unknown_extra_keys_ignored(exported_json_bytes):
    payload = json.loads(exported_json_bytes.decode("utf-8"))
    payload["some_future_key"] = {"nested": True}
    payload["planning"]["some_future_planning_key"] = [{"x": 1}]
    result = validate_restore_backup_json(json.dumps(payload).encode("utf-8"))
    assert result["valid"] is True


def test_restore_validate_route_requires_login(client, make_user):
    make_user(username="restore-validate-login-required", password="password123")
    resp = client.post("/settings/restore/validate", data={}, follow_redirects=False)
    assert resp.status_code in (302, 401)
    if resp.status_code == 302:
        assert "/login" in resp.headers.get("Location", "")


def test_restore_validate_route_valid_upload_shows_valid_result_and_no_db_writes(app, client, exported_json_bytes):
    before = _count_rows(app)
    resp = client.post(
        "/settings/restore/validate",
        data={"backup_file": (io.BytesIO(exported_json_bytes), "backup.json")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    after = _count_rows(app)
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "Check a backup file" in body
    assert "This backup looks valid. No data has been changed." in body
    assert "Export schema version" in body
    assert before == after


def test_restore_validate_route_corrupt_json_shows_errors_and_no_db_writes(app, client, make_user):
    uid, username, password = make_user(username="restore-validate-corrupt", password="password123")
    _login(client, username, password)

    before = _count_rows(app)
    resp = client.post(
        "/settings/restore/validate",
        data={"backup_file": (io.BytesIO(b"{"), "backup.json")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    after = _count_rows(app)

    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "This backup cannot be restored yet. No data has been changed." in body
    assert "Invalid JSON" in body
    assert before == after


def test_restore_validate_route_missing_file_shows_friendly_error_and_no_db_writes(app, client, make_user):
    uid, username, password = make_user(username="restore-validate-missing", password="password123")
    _login(client, username, password)

    before = _count_rows(app)
    resp = client.post(
        "/settings/restore/validate",
        data={},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    after = _count_rows(app)

    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "This backup cannot be restored yet. No data has been changed." in body
    assert "Please choose a .json backup file to upload." in body
    assert before == after


def test_no_restore_commit_route_added(app, client, make_user):
    uid, username, password = make_user(username="restore-validate-no-commit", password="password123")
    _login(client, username, password)

    resp = client.post("/settings/restore/commit", data={}, follow_redirects=False)
    assert resp.status_code == 404
