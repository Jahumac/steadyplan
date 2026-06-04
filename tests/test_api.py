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


def test_overview_uses_effective_account_values_for_holdings_accounts(app, client, token):
    with app.app_context():
        from app.models import get_connection, get_user_by_username

        uid = get_user_by_username("apiuser").id
        with get_connection() as conn:
            holdings_account_id = conn.execute(
                """
                INSERT INTO accounts (
                    user_id, name, wrapper_type, category, valuation_mode,
                    current_value, uninvested_cash, monthly_contribution, is_active
                ) VALUES (?, 'ISA Portfolio', 'Stocks & Shares ISA', 'ISA', 'holdings', 5, 50, 125, 1)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO accounts (
                    user_id, name, wrapper_type, category, valuation_mode,
                    current_value, uninvested_cash, monthly_contribution, is_active
                ) VALUES (?, 'Cash ISA', 'Cash ISA', 'ISA', 'manual', 700, 25, 75, 1)
                """,
                (uid,),
            )
            conn.execute(
                """
                INSERT INTO holdings (account_id, holding_name, value)
                VALUES (?, 'Vanguard FTSE Global All Cap', 1234)
                """,
                (holdings_account_id,),
            )
            conn.commit()

    resp = client.get(
        "/api/v1/overview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total_value"] == 2009
    assert body["monthly_contribution"] == 200
    assert body["account_count"] == 2


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


def test_budget_endpoint_matches_budget_page_rollup_rules(app, client, token):
    with app.app_context():
        from app.models import (
            create_budget_item,
            create_contribution_override,
            fetch_budget_items,
            fetch_budget_sections,
            get_connection,
            get_user_by_username,
            upsert_budget_entry,
        )
        from app.routes.budget import _build_monthly_data

        user = get_user_by_username("apiuser")
        assert user is not None
        uid = user.id
        fetch_budget_sections(uid)

        carry_item_id = create_budget_item(
            {
                "name": "Groceries",
                "section": "discretionary",
                "default_amount": 300,
                "notes": "",
                "sort_order": 0,
            },
            uid,
        )

        with get_connection() as conn:
            linked_account_id = conn.execute(
                """
                INSERT INTO accounts (
                    user_id, name, current_value, monthly_contribution,
                    include_in_budget, pre_salary, is_active
                ) VALUES (?, 'Stocks ISA', 0, 100, 1, 0, 1)
                """,
                (uid,),
            ).lastrowid
            linked_debt_id = conn.execute(
                """
                INSERT INTO debts (
                    user_id, name, current_balance, monthly_payment, apr, is_active, created_at
                ) VALUES (?, 'Car Loan', 5000, 150, 7.9, 1, datetime('now'))
                """,
                (uid,),
            ).lastrowid
            conn.commit()

        linked_items = fetch_budget_items(uid)
        linked_account_item = next(item for item in linked_items if item.get("linked_account_id") == linked_account_id)
        linked_debt_item = next(item for item in linked_items if item.get("linked_debt_id") == linked_debt_id)

        upsert_budget_entry("2026-05", carry_item_id, 450, uid)
        create_contribution_override(
            {
                "account_id": linked_account_id,
                "from_month": "2026-05",
                "to_month": "2026-07",
                "override_amount": 100,
                "reason": "broad",
            },
            uid,
        )
        create_contribution_override(
            {
                "account_id": linked_account_id,
                "from_month": "2026-06",
                "to_month": "2026-06",
                "override_amount": 250,
                "reason": "narrow",
            },
            uid,
        )

        budget_sections, _ = _build_monthly_data("2026-06", uid)
        expected_amounts = {
            row["id"]: row["amount"]
            for section in budget_sections
            for row in section["rows"]
        }

    resp = client.get(
        "/api/v1/budget/2026-06",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()

    actual_amounts = {item["id"]: item["amount"] for item in body["items"]}
    assert actual_amounts[carry_item_id] == 450
    assert actual_amounts[linked_account_item["id"]] == 250
    assert actual_amounts[linked_debt_item["id"]] == 150
    assert actual_amounts == expected_amounts


def test_fetch_all_active_overrides_prefers_narrower_matching_override(app, make_user):
    uid, _, _ = make_user(username="override-user")

    with app.app_context():
        from app.models import create_contribution_override, get_connection, fetch_all_active_overrides

        with get_connection() as conn:
            account_id = conn.execute(
                """
                INSERT INTO accounts (
                    user_id, name, provider, wrapper_type, category, tags, current_value,
                    monthly_contribution, pension_contribution_day, goal_value, valuation_mode,
                    growth_mode, growth_rate_override, owner, is_active, notes, last_updated,
                    employer_contribution, contribution_method, annual_fee_pct, platform_fee_pct,
                    platform_fee_flat, platform_fee_cap, fund_fee_pct, contribution_fee_pct,
                    uninvested_cash, cash_interest_rate, interest_payment_day
                ) VALUES (?, 'Stocks ISA', 'Vanguard', 'Stocks & Shares ISA', 'ISA', '', 0,
                    100, 0, 0, 'manual', 'default', NULL, 'Janusz', 1, '', datetime('now'),
                    0, 'standard', 0, 0, 0, 0, 0, 0, 0, 0, 0)
                """,
                (uid,),
            ).lastrowid
            conn.commit()
        create_contribution_override(
            {
                "account_id": account_id,
                "from_month": "2026-06",
                "to_month": "2026-06",
                "override_amount": 250,
                "reason": "narrow",
            },
            uid,
        )
        create_contribution_override(
            {
                "account_id": account_id,
                "from_month": "2026-05",
                "to_month": "2026-07",
                "override_amount": 100,
                "reason": "broad",
            },
            uid,
        )

        active = fetch_all_active_overrides("2026-06", uid)

    assert float(active[account_id]["override_amount"] or 0) == 250


def test_fetch_contribution_overrides_for_accounts_groups_rows_by_account(app, make_user):
    uid, _, _ = make_user(username="override-batch-user")

    with app.app_context():
        from app.models import (
            create_contribution_override,
            fetch_contribution_overrides_for_accounts,
            get_connection,
        )

        with get_connection() as conn:
            first_account_id = conn.execute(
                """
                INSERT INTO accounts (
                    user_id, name, provider, wrapper_type, category, tags, current_value,
                    monthly_contribution, pension_contribution_day, goal_value, valuation_mode,
                    growth_mode, growth_rate_override, owner, is_active, notes, last_updated,
                    employer_contribution, contribution_method, annual_fee_pct, platform_fee_pct,
                    platform_fee_flat, platform_fee_cap, fund_fee_pct, contribution_fee_pct,
                    uninvested_cash, cash_interest_rate, interest_payment_day
                ) VALUES (?, 'Stocks ISA', 'Vanguard', 'Stocks & Shares ISA', 'ISA', '', 0,
                    100, 0, 0, 'manual', 'default', NULL, 'Janusz', 1, '', datetime('now'),
                    0, 'standard', 0, 0, 0, 0, 0, 0, 0, 0, 0)
                """,
                (uid,),
            ).lastrowid
            second_account_id = conn.execute(
                """
                INSERT INTO accounts (
                    user_id, name, provider, wrapper_type, category, tags, current_value,
                    monthly_contribution, pension_contribution_day, goal_value, valuation_mode,
                    growth_mode, growth_rate_override, owner, is_active, notes, last_updated,
                    employer_contribution, contribution_method, annual_fee_pct, platform_fee_pct,
                    platform_fee_flat, platform_fee_cap, fund_fee_pct, contribution_fee_pct,
                    uninvested_cash, cash_interest_rate, interest_payment_day
                ) VALUES (?, 'Cash ISA', 'Vanguard', 'Cash ISA', 'ISA', '', 0,
                    50, 0, 0, 'manual', 'default', NULL, 'Janusz', 1, '', datetime('now'),
                    0, 'standard', 0, 0, 0, 0, 0, 0, 0, 0, 0)
                """,
                (uid,),
            ).lastrowid
            third_account_id = conn.execute(
                """
                INSERT INTO accounts (
                    user_id, name, provider, wrapper_type, category, tags, current_value,
                    monthly_contribution, pension_contribution_day, goal_value, valuation_mode,
                    growth_mode, growth_rate_override, owner, is_active, notes, last_updated,
                    employer_contribution, contribution_method, annual_fee_pct, platform_fee_pct,
                    platform_fee_flat, platform_fee_cap, fund_fee_pct, contribution_fee_pct,
                    uninvested_cash, cash_interest_rate, interest_payment_day
                ) VALUES (?, 'Premium Bonds', 'NS&I', 'Cash', 'Cash', '', 0,
                    0, 0, 0, 'manual', 'default', NULL, 'Janusz', 1, '', datetime('now'),
                    0, 'standard', 0, 0, 0, 0, 0, 0, 0, 0, 0)
                """,
                (uid,),
            ).lastrowid
            conn.commit()

        create_contribution_override(
            {
                "account_id": first_account_id,
                "from_month": "2026-04",
                "to_month": "2026-05",
                "override_amount": 125,
                "reason": "spring",
            },
            uid,
        )
        create_contribution_override(
            {
                "account_id": first_account_id,
                "from_month": "2026-06",
                "to_month": "2026-06",
                "override_amount": 200,
                "reason": "bonus",
            },
            uid,
        )
        create_contribution_override(
            {
                "account_id": second_account_id,
                "from_month": "2026-04",
                "to_month": "2026-04",
                "override_amount": 75,
                "reason": "trim",
            },
            uid,
        )

        grouped = fetch_contribution_overrides_for_accounts(
            [first_account_id, second_account_id, third_account_id]
        )

    assert [float(row["override_amount"] or 0) for row in grouped[first_account_id]] == [125, 200]
    assert [float(row["override_amount"] or 0) for row in grouped[second_account_id]] == [75]
    assert grouped[third_account_id] == []


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



def test_assistant_month_summary_keeps_explicit_future_linked_debt_entry_visible(app, client, token):
    with app.app_context():
        from app.models import fetch_budget_items, fetch_budget_sections, get_connection, get_user_by_username, upsert_budget_entry
        from app.routes.budget import _build_monthly_data

        user = get_user_by_username("apiuser")
        assert user is not None
        uid = user.id
        fetch_budget_sections(uid)
        with get_connection() as conn:
            debt_id = conn.execute(
                """
                INSERT INTO debts (
                    user_id, name, current_balance, monthly_payment, apr, is_active, created_at
                ) VALUES (?, 'Final repayment', 0, 70, 0, 1, datetime('now'))
                """,
                (uid,),
            ).lastrowid
            conn.commit()

        debt_item = next(item for item in fetch_budget_items(uid) if item.get("linked_debt_id") == debt_id)
        upsert_budget_entry("2026-06", debt_item["id"], 70, uid)

        budget_sections, budget_summary = _build_monthly_data("2026-06", uid)
        budget_debt_rows = [row for section in budget_sections if section["key"] == "debt" for row in section["rows"]]
        assert any(row["name"] == "Final repayment" and row["amount"] == 70 for row in budget_debt_rows)
        assert budget_summary["total_expenses"] == 70

    resp = client.get(
        "/api/v1/assistant/month-summary/2026-06",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()

    debt_section = next(section for section in body["sections"] if section["key"] == "debt")
    assert any(row["name"] == "Final repayment" and row["amount"] == 70 for row in debt_section["rows"])
    assert body["summary"]["total_expenses"] == 70
    assert body["summary"]["planned_debt_payments"] == 70



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



def test_assistant_budget_entry_write_rejects_invalid_payload(app, client, token):
    with app.app_context():
        from app.models import create_budget_item, fetch_budget_sections, get_user_by_username

        uid = get_user_by_username("apiuser").id
        fetch_budget_sections(uid)
        item_id = create_budget_item(
            {
                "name": "Phone sinking fund",
                "section": "discretionary",
                "default_amount": 50,
                "notes": "",
                "sort_order": 0,
            },
            uid,
        )

    bad_month = client.post(
        f"/api/v1/assistant/budget-items/{item_id}/month-entry",
        headers={"Authorization": f"Bearer {token}"},
        json={"month": "2026-13", "amount": 200},
    )
    assert bad_month.status_code == 400
    assert bad_month.get_json()["error"] == "bad_request"

    bad_amount = client.post(
        f"/api/v1/assistant/budget-items/{item_id}/month-entry",
        headers={"Authorization": f"Bearer {token}"},
        json={"month": "2026-05", "amount": -1},
    )
    assert bad_amount.status_code == 400
    assert bad_amount.get_json()["error"] == "bad_request"



def test_assistant_budget_entry_write_updates_manual_unlinked_item(app, client, token):
    with app.app_context():
        from app.models import create_budget_item, fetch_budget_entries, fetch_budget_sections, get_user_by_username

        uid = get_user_by_username("apiuser").id
        fetch_budget_sections(uid)
        item_id = create_budget_item(
            {
                "name": "Phone sinking fund",
                "section": "discretionary",
                "default_amount": 50,
                "notes": "Planned upgrade",
                "sort_order": 0,
            },
            uid,
        )

    resp = client.post(
        f"/api/v1/assistant/budget-items/{item_id}/month-entry",
        headers={"Authorization": f"Bearer {token}"},
        json={"month": "2026-05", "amount": 799},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["budget_item"]["id"] == item_id
    assert body["budget_item"]["name"] == "Phone sinking fund"
    assert body["month"] == "2026-05"
    assert body["amount"] == 799
    assert body["previous_amount"] == 50
    assert body["previous_source"] == "default"

    with app.app_context():
        from app.models import fetch_budget_entries, get_user_by_username

        uid = get_user_by_username("apiuser").id
        entries = fetch_budget_entries("2026-05", uid)
        saved = next(entry for entry in entries if entry["budget_item_id"] == item_id)
        assert float(saved["amount"]) == 799



def test_assistant_budget_entry_write_rejects_linked_items(app, client, token):
    with app.app_context():
        from app.models import create_budget_item, fetch_budget_sections, get_connection, get_user_by_username

        uid = get_user_by_username("apiuser").id
        fetch_budget_sections(uid)
        with get_connection() as conn:
            account_id = conn.execute(
                """
                INSERT INTO accounts (
                    user_id, name, current_value, monthly_contribution,
                    include_in_budget, pre_salary, is_active
                ) VALUES (?, 'Stocks ISA', 0, 200, 1, 0, 1)
                """,
                (uid,),
            ).lastrowid
            conn.commit()

        item_id = create_budget_item(
            {
                "name": "Linked ISA",
                "section": "investment",
                "default_amount": 200,
                "linked_account_id": account_id,
                "notes": "",
                "sort_order": 0,
            },
            uid,
        )

    resp = client.post(
        f"/api/v1/assistant/budget-items/{item_id}/month-entry",
        headers={"Authorization": f"Bearer {token}"},
        json={"month": "2026-05", "amount": 799},
    )
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


def test_update_account_balance_caps_premium_bonds_and_marks_review_progress(app, client, token):
    with app.app_context():
        from app.models import (
            ensure_monthly_review_items,
            fetch_or_create_monthly_review,
            get_connection,
            get_user_by_username,
        )

        uid = get_user_by_username("apiuser").id
        with get_connection() as conn:
            aid = conn.execute(
                """
                INSERT INTO accounts (
                    user_id, name, wrapper_type, valuation_mode, current_value, is_active
                ) VALUES (?, 'PB', 'Premium Bonds', 'manual', 100, 1)
                """,
                (uid,),
            ).lastrowid
            conn.commit()

        review = fetch_or_create_monthly_review("2026-04", uid)
        assert review is not None
        ensure_monthly_review_items(review["id"], uid)
        review_id = review["id"]

    resp = client.post(
        f"/api/v1/accounts/{aid}/balance",
        json={"current_value": 60000, "month": "2026-04"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["current_value"] == 50000

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            account_row = conn.execute(
                "SELECT current_value FROM accounts WHERE id = ?",
                (aid,),
            ).fetchone()
            assert float(account_row["current_value"]) == 50000.0

            snapshot_row = conn.execute(
                "SELECT balance FROM monthly_snapshots WHERE account_id = ? AND month_key = ?",
                (aid, "2026-04"),
            ).fetchone()
            assert snapshot_row is not None
            assert float(snapshot_row["balance"]) == 50000.0

            daily_total = conn.execute(
                "SELECT total_value FROM portfolio_daily_snapshots WHERE user_id = ? ORDER BY snapshot_date DESC LIMIT 1",
                (uid,),
            ).fetchone()
            assert daily_total is not None
            assert float(daily_total["total_value"]) == 50000.0

            daily_account = conn.execute(
                "SELECT value FROM account_daily_snapshots WHERE user_id = ? AND account_id = ? ORDER BY snapshot_date DESC LIMIT 1",
                (uid, aid),
            ).fetchone()
            assert daily_account is not None
            assert float(daily_account["value"]) == 50000.0

            review_item = conn.execute(
                "SELECT balance_updated FROM monthly_review_items WHERE review_id = ? AND account_id = ?",
                (review_id, aid),
            ).fetchone()
            assert review_item is not None
            assert int(review_item["balance_updated"] or 0) == 1


def test_update_account_balance_rejects_invalid_month_without_changing_balance(app, client, token):
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

    with app.app_context():
        from app.models import get_connection
        with get_connection() as conn:
            row = conn.execute(
                "SELECT current_value FROM accounts WHERE id = ?",
                (aid,),
            ).fetchone()
        assert float(row["current_value"]) == 100.0


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
