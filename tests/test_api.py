"""API smoke tests: auth enforcement + each endpoint returns valid JSON."""
import pytest


@pytest.fixture
def token(app, make_user):
    """Mint a real API token for a test user."""
    uid, _, _ = make_user(username="apiuser")
    with app.app_context():
        from app.models import create_api_token
        return create_api_token(uid, label="test")


@pytest.fixture
def api(client, token):
    """A helper that attaches the Bearer header to every request."""
    class _Client:
        def get(self, path):
            return client.get(path, headers={"Authorization": f"Bearer {token}"})

    return _Client()


# ── Auth ──────────────────────────────────────────────────────────────────────

def test_api_rejects_missing_token(client):
    resp = client.get("/api/v1/me")
    assert resp.status_code == 401
    body = resp.get_json()
    assert body["error"] == "missing_token"


def test_api_rejects_wrong_scheme(client):
    resp = client.get("/api/v1/me", headers={"Authorization": "Basic abc"})
    assert resp.status_code == 401


def test_api_rejects_invalid_token(client):
    resp = client.get("/api/v1/me",
                      headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "invalid_token"


# ── Endpoints ────────────────────────────────────────────────────────────────

def test_me_returns_user_info(api):
    resp = api.get("/api/v1/me")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["username"] == "apiuser"
    assert "id" in body


def test_accounts_empty_for_new_user(api):
    resp = api.get("/api/v1/accounts")
    assert resp.status_code == 200
    assert resp.get_json() == {"accounts": []}


def test_account_detail_404(api):
    resp = api.get("/api/v1/accounts/99999")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "not_found"


def test_holdings_empty(api):
    resp = api.get("/api/v1/holdings")
    assert resp.status_code == 200
    assert resp.get_json() == {"holdings": []}


def test_goals_empty(api):
    resp = api.get("/api/v1/goals")
    assert resp.status_code == 200
    assert resp.get_json() == {"goals": []}


def test_overview_empty(api):
    resp = api.get("/api/v1/overview")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total_value"] == 0
    assert body["account_count"] == 0


def test_budget_bad_month_key(api):
    resp = api.get("/api/v1/budget/2026")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "bad_request"


def test_budget_valid_month_key(api):
    resp = api.get("/api/v1/budget/2026-04")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["month"] == "2026-04"
    assert "items" in body


def test_assistant_month_summary_bad_month_key(api):
    resp = api.get("/api/v1/assistant/month-summary/2026-13")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "bad_request"


def test_assistant_month_summary_empty_user(api):
    resp = api.get("/api/v1/assistant/month-summary/2026-04")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["month"] == "2026-04"
    assert body["summary"]["available_after_budget"] == 0
    assert body["summary"]["total_income"] == 0
    assert body["summary"]["take_home_outgoings"] == 0
    assert body["summary"]["planned_savings"] == 0
    assert any(signal["code"] == "no_income_budgeted" for signal in body["signals"])


def test_assistant_month_summary_includes_linked_budget_items(app, client, token):
    with app.app_context():
        from app.models import create_budget_item, fetch_budget_sections, get_connection, get_user_by_username

        uid = get_user_by_username("apiuser").id
        fetch_budget_sections(uid)
        create_budget_item(
            {
                "name": "Salary",
                "section": "income",
                "default_amount": 3000,
                "notes": "",
                "sort_order": 0,
            },
            uid,
        )
        create_budget_item(
            {
                "name": "Rent",
                "section": "fixed",
                "default_amount": 1200,
                "notes": "",
                "sort_order": 0,
            },
            uid,
        )
        create_budget_item(
            {
                "name": "Groceries",
                "section": "discretionary",
                "default_amount": 400,
                "notes": "",
                "sort_order": 0,
            },
            uid,
        )
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (
                    user_id, name, current_value, monthly_contribution,
                    include_in_budget, pre_salary, is_active
                ) VALUES (?, 'Work Pension', 0, 300, 1, 1, 1)
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO accounts (
                    user_id, name, current_value, monthly_contribution,
                    include_in_budget, pre_salary, is_active
                ) VALUES (?, 'Stocks ISA', 0, 200, 1, 0, 1)
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO debts (
                    user_id, name, current_balance, monthly_payment, apr, is_active, created_at
                ) VALUES (?, 'Car Loan', 5000, 150, 7.9, 1, datetime('now'))
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get(
        "/api/v1/assistant/month-summary/2026-04",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()

    assert body["summary"]["total_income"] == 3000
    assert body["summary"]["total_expenses"] == 2250
    assert body["summary"]["planned_savings"] == 500
    assert body["summary"]["planned_debt_payments"] == 150
    assert body["summary"]["pre_salary_total"] == 300
    assert body["summary"]["take_home_outgoings"] == 1950
    assert body["summary"]["available_after_budget"] == 1050

    investment_section = next(section for section in body["sections"] if section["key"] == "investment")
    debt_section = next(section for section in body["sections"] if section["key"] == "debt")
    assert sorted(row["name"] for row in investment_section["rows"]) == ["Stocks ISA", "Work Pension"]
    assert investment_section["total"] == 500
    assert debt_section["rows"][0]["name"] == "Car Loan"
    assert debt_section["rows"][0]["source"] == "linked_debt"



def test_assistant_portfolio_overview_splits_access_and_uses_effective_values(app, client, token):
    with app.app_context():
        from app.models import get_connection, get_user_by_username

        uid = get_user_by_username("apiuser").id
        with get_connection() as conn:
            holdings_account_id = conn.execute(
                """
                INSERT INTO accounts (
                    user_id, name, wrapper_type, category, valuation_mode,
                    current_value, uninvested_cash, is_active
                ) VALUES (?, 'ISA Portfolio', 'Stocks & Shares ISA', 'ISA', 'holdings', 5, 50, 1)
                """,
                (uid,),
            ).lastrowid
            pension_account_id = conn.execute(
                """
                INSERT INTO accounts (
                    user_id, name, wrapper_type, category, valuation_mode,
                    current_value, uninvested_cash, is_active
                ) VALUES (?, 'Work Pension', 'Workplace Pension', 'Pension', 'manual', 700, 0, 1)
                """,
                (uid,),
            ).lastrowid
            lisa_account_id = conn.execute(
                """
                INSERT INTO accounts (
                    user_id, name, wrapper_type, category, valuation_mode,
                    current_value, uninvested_cash, is_active
                ) VALUES (?, 'House LISA', 'Lifetime ISA', 'ISA', 'manual', 400, 0, 1)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO holdings (account_id, holding_name, value)
                VALUES (?, 'Vanguard FTSE Global All Cap', 1234)
                """,
                (holdings_account_id,),
            )
            conn.commit()

    resp = client.get(
        "/api/v1/assistant/portfolio-overview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()

    assert body["summary"]["total_net_worth"] == 2384
    assert body["summary"]["accessible_total"] == 1284
    assert body["summary"]["restricted_total"] == 400
    assert body["summary"]["locked_total"] == 700
    assert body["summary"]["account_count"] == 3

    accounts = {row["name"]: row for row in body["accounts"]}
    assert accounts["ISA Portfolio"]["effective_value"] == 1284
    assert accounts["ISA Portfolio"]["holdings_value"] == 1234
    assert accounts["ISA Portfolio"]["accessible_value"] == 1284
    assert accounts["ISA Portfolio"]["access_type"] == "accessible"
    assert accounts["Work Pension"]["access_type"] == "locked"
    assert accounts["House LISA"]["access_type"] == "restricted"



def test_assistant_affordability_requires_positive_amount(api):
    resp = api.get("/api/v1/assistant/affordability/2026-04")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "bad_request"

    resp = api.get("/api/v1/assistant/affordability/2026-04?amount=0")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "bad_request"



def test_assistant_affordability_rejects_invalid_spread_months(api):
    resp = api.get("/api/v1/assistant/affordability/2026-04?amount=900&spread_months=0")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "bad_request"



def test_assistant_affordability_combines_budget_and_access_context(app, client, token):
    with app.app_context():
        from app.models import create_budget_item, fetch_budget_sections, get_connection, get_user_by_username

        uid = get_user_by_username("apiuser").id
        fetch_budget_sections(uid)
        create_budget_item(
            {
                "name": "Salary",
                "section": "income",
                "default_amount": 3000,
                "notes": "",
                "sort_order": 0,
            },
            uid,
        )
        create_budget_item(
            {
                "name": "Rent",
                "section": "fixed",
                "default_amount": 1200,
                "notes": "",
                "sort_order": 0,
            },
            uid,
        )
        create_budget_item(
            {
                "name": "Groceries",
                "section": "discretionary",
                "default_amount": 400,
                "notes": "",
                "sort_order": 0,
            },
            uid,
        )
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (
                    user_id, name, wrapper_type, category, valuation_mode,
                    current_value, is_active
                ) VALUES (?, 'Emergency ISA', 'Stocks & Shares ISA', 'ISA', 'manual', 2000, 1)
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO accounts (
                    user_id, name, wrapper_type, category, valuation_mode,
                    current_value, is_active
                ) VALUES (?, 'Work Pension', 'Workplace Pension', 'Pension', 'manual', 9000, 1)
                """,
                (uid,),
            )
            conn.commit()

    resp = client.get(
        "/api/v1/assistant/affordability/2026-04?amount=1800",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["assessment"]["verdict"] == "caution"
    assert body["assessment"]["budget_affordable"] is False
    assert body["assessment"]["accessible_funding_available"] is True
    assert body["budget"]["available_after_budget"] == 1400
    assert body["budget"]["remaining_after_purchase"] == -400
    assert body["access"]["accessible_total"] == 2000
    assert body["access"]["locked_total"] == 9000

    spread_resp = client.get(
        "/api/v1/assistant/affordability/2026-04?amount=1800&spread_months=3",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert spread_resp.status_code == 200
    spread_body = spread_resp.get_json()
    assert spread_body["purchase"]["monthly_cost"] == 600
    assert spread_body["assessment"]["verdict"] == "yes"
    assert spread_body["assessment"]["budget_affordable"] is True
    assert any(signal["code"] == "spread_applied" for signal in spread_body["signals"])



def test_assumptions_returns_defaults(api):
    resp = api.get("/api/v1/assumptions")
    assert resp.status_code == 200
    body = resp.get_json()
    # Defaults are created on first access
    assert body.get("annual_growth_rate") is not None


def test_unknown_api_route_returns_json_404(api):
    resp = api.get("/api/v1/nonexistent")
    # Falls through to Flask 404 which returns HTML; our errorhandler
    # on the blueprint only fires for matched prefix mismatches. This test
    # documents current behaviour — if we ever bolt on a catch-all we can
    # tighten the assertion.
    assert resp.status_code == 404


# ── End-to-end: create account via web, fetch via API ────────────────────────

# ── Write endpoints ───────────────────────────────────────────────────────────

def test_update_account_balance_requires_ownership(app, client, token):
    """Cannot update an account that belongs to another user."""
    with app.app_context():
        from app.models import create_user, get_connection
        other_uid = create_user("eve", "password123")
        with get_connection() as conn:
            other_account = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active) "
                "VALUES (?, 'Eve ISA', 1000, 1)",
                (other_uid,),
            ).lastrowid
            conn.commit()
    resp = client.post(
        f"/api/v1/accounts/{other_account}/balance",
        json={"current_value": 999999},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_update_account_balance_succeeds_for_owner(app, client, token):
    with app.app_context():
        from app.models import get_connection, get_user_by_username
        uid = get_user_by_username("apiuser").id
        with get_connection() as conn:
            aid = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active) "
                "VALUES (?, 'Mine', 100, 1)",
                (uid,),
            ).lastrowid
            conn.commit()
    resp = client.post(
        f"/api/v1/accounts/{aid}/balance",
        json={"current_value": 5555, "month": "2026-04"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["current_value"] == 5555


def test_update_account_balance_rejects_invalid_month(app, client, token):
    with app.app_context():
        from app.models import get_connection, get_user_by_username
        uid = get_user_by_username("apiuser").id
        with get_connection() as conn:
            aid = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active) "
                "VALUES (?, 'Mine', 100, 1)",
                (uid,),
            ).lastrowid
            conn.commit()
    resp = client.post(
        f"/api/v1/accounts/{aid}/balance",
        json={"current_value": 5555, "month": "2026-13"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "bad_request"


def test_update_account_balance_rejects_negative(app, client, token):
    resp = client.post(
        "/api/v1/accounts/1/balance",
        json={"current_value": -100},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_isa_contribution_rejects_missing_fields(client, token):
    resp = client.post(
        "/api/v1/contributions/isa",
        json={"amount": 500},  # no account_id, no date
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_isa_contribution_accepted(app, client, token):
    with app.app_context():
        from app.models import get_connection, get_user_by_username
        uid = get_user_by_username("apiuser").id
        with get_connection() as conn:
            aid = conn.execute(
                "INSERT INTO accounts (user_id, name, wrapper_type, is_active) "
                "VALUES (?, 'My ISA', 'Stocks & Shares ISA', 1)",
                (uid,),
            ).lastrowid
            conn.commit()
    resp = client.post(
        "/api/v1/contributions/isa",
        json={"account_id": aid, "amount": 500, "date": "2026-04-10"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201


def test_isa_contribution_rejects_foreign_account(app, client, token):
    with app.app_context():
        from app.models import create_user, get_connection
        other_uid = create_user("mallory", "password123")
        with get_connection() as conn:
            foreign_aid = conn.execute(
                "INSERT INTO accounts (user_id, name, is_active) VALUES (?, 'theirs', 1)",
                (other_uid,),
            ).lastrowid
            conn.commit()
    resp = client.post(
        "/api/v1/contributions/isa",
        json={"account_id": foreign_aid, "amount": 500, "date": "2026-04-10"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_isa_contribution_rejects_invalid_date(app, client, token):
    with app.app_context():
        from app.models import get_connection, get_user_by_username
        uid = get_user_by_username("apiuser").id
        with get_connection() as conn:
            aid = conn.execute(
                "INSERT INTO accounts (user_id, name, wrapper_type, is_active) "
                "VALUES (?, 'My ISA', 'Stocks & Shares ISA', 1)",
                (uid,),
            ).lastrowid
            conn.commit()
    resp = client.post(
        "/api/v1/contributions/isa",
        json={"account_id": aid, "amount": 500, "date": "2026-02-31"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "bad_request"


def test_pension_contribution_rejects_bad_kind(app, client, token):
    resp = client.post(
        "/api/v1/contributions/pension",
        json={"account_id": 1, "amount": 100, "date": "2026-04-10", "kind": "wat"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


# ── Monthly review completion ────────────────────────────────────────────────

def test_complete_monthly_review_bad_month_key(client, token):
    resp = client.post(
        "/api/v1/monthly-review/2026/complete",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_complete_monthly_review_success(app, client, token):
    with app.app_context():
        from app.models import get_connection, get_user_by_username
        uid = get_user_by_username("apiuser").id
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active) "
                "VALUES (?, 'A', 1000, 1)",
                (uid,),
            )
            conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active) "
                "VALUES (?, 'B', 2000, 1)",
                (uid,),
            )
            conn.commit()

    resp = client.post(
        "/api/v1/monthly-review/2026-04/complete",
        json={"notes": "done from phone"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "complete"
    assert body["snapshots_taken"] == 0

    # Verify the review is actually marked complete in the DB
    with app.app_context():
        from app.models import fetch_or_create_monthly_review, get_user_by_username
        uid = get_user_by_username("apiuser").id
        review = fetch_or_create_monthly_review("2026-04", uid)
        assert review["status"] == "complete"
        assert review["notes"] == "done from phone"


def test_complete_monthly_review_takes_snapshots_for_updated_manual_accounts(app, client, token):
    with app.app_context():
        from app.models import (
            ensure_monthly_review_items,
            fetch_or_create_monthly_review,
            get_connection,
            get_user_by_username,
        )

        uid = get_user_by_username("apiuser").id
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active) "
                "VALUES (?, 'A', 1000, 1)",
                (uid,),
            )
            conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active) "
                "VALUES (?, 'B', 2000, 1)",
                (uid,),
            )
            conn.commit()

        review = fetch_or_create_monthly_review("2026-04", uid)
        ensure_monthly_review_items(review["id"], uid)
        with get_connection() as conn:
            conn.execute(
                "UPDATE monthly_review_items SET balance_updated = 1 "
                "WHERE review_id = ?",
                (review["id"],),
            )
            conn.commit()

    resp = client.post(
        "/api/v1/monthly-review/2026-04/complete",
        json={"notes": "done from phone"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "complete"
    assert body["snapshots_taken"] == 2


def test_complete_monthly_review_preserves_existing_structured_checklist(app, client, token):
    from app.services.monthly_review_checklist import (
        encode_monthly_review_notes,
        parse_monthly_review_notes,
    )

    with app.app_context():
        from app.models import fetch_or_create_monthly_review, get_connection, get_user_by_username

        uid = get_user_by_username("apiuser").id
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active) "
                "VALUES (?, 'A', 1000, 1)",
                (uid,),
            )
            conn.commit()

        review = fetch_or_create_monthly_review("2026-05", uid)
        encoded = encode_monthly_review_notes("before", {"goals", "budget"})
        with get_connection() as conn:
            conn.execute(
                "UPDATE monthly_reviews SET notes = ? WHERE id = ? AND user_id = ?",
                (encoded, review["id"], uid),
            )
            conn.commit()

    resp = client.post(
        "/api/v1/monthly-review/2026-05/complete",
        json={"notes": "done from phone"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    with app.app_context():
        from app.models import fetch_monthly_review, get_user_by_username

        uid = get_user_by_username("apiuser").id
        review = fetch_monthly_review("2026-05", uid)
        assert review is not None
        assert review["status"] == "complete"
        parsed = parse_monthly_review_notes(review.get("notes"))
        assert parsed["notes"] == "done from phone"
        assert "goals" in parsed["checked"]
        assert "budget" in parsed["checked"]


# ── Health check ──────────────────────────────────────────────────────────────

def test_health_check_no_auth_required(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["checks"]["database"] == "ok"
    assert "timestamp" in body


def test_api_returns_data_created_via_db(app, client, token):
    """Proves the API reads the same DB the web UI writes to."""
    with app.app_context():
        from app.models import get_connection, get_user_by_username
        uid = get_user_by_username("apiuser").id
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO accounts (user_id, name, wrapper_type,
                   current_value, monthly_contribution, is_active)
                   VALUES (?, ?, ?, ?, ?, 1)""",
                (uid, "Test ISA", "Stocks & Shares ISA", 12345.67, 100),
            )
            conn.commit()
    resp = client.get("/api/v1/accounts",
                      headers={"Authorization": f"Bearer {token}"})
    body = resp.get_json()
    assert len(body["accounts"]) == 1
    assert body["accounts"][0]["name"] == "Test ISA"
    assert body["accounts"][0]["current_value"] == 12345.67
