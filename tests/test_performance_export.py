from io import BytesIO

from openpyxl import load_workbook

from app.models import create_account, get_connection


def _account_payload(name="ISA", wrapper_type="Stocks & Shares ISA", value=1000, monthly=0):
    return {
        "name": name,
        "provider": "Provider",
        "wrapper_type": wrapper_type,
        "category": "Investment",
        "tags": "",
        "current_value": value,
        "monthly_contribution": monthly,
        "pension_contribution_day": 0,
        "goal_value": None,
        "valuation_mode": "manual",
        "growth_mode": "default",
        "growth_rate_override": None,
        "owner": "Janusz",
        "is_active": 1,
        "notes": "",
        "last_updated": "2026-05-25",
        "employer_contribution": 0,
        "contribution_method": "standard",
        "annual_fee_pct": 0,
        "platform_fee_pct": 0,
        "platform_fee_flat": 0,
        "platform_fee_cap": 0,
        "fund_fee_pct": 0,
        "contribution_fee_pct": 0,
        "uninvested_cash": 0,
        "cash_interest_rate": 0,
        "interest_payment_day": 0,
    }


def _login(client, username, password):
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)


def _workbook_from_response(response):
    assert response.status_code == 200
    return load_workbook(BytesIO(response.data), data_only=True)


def test_performance_export_keeps_zero_snapshot_message_for_selected_account(app, client, make_user):
    uid, username, password = make_user(username="perf-export-zero", password="password123")
    with app.app_context():
        account_id = create_account(_account_payload(), uid)

    _login(client, username, password)
    workbook = _workbook_from_response(client.get(f"/performance/export.xlsx?account_id={account_id}"))

    detail = workbook["ISA (Monthly)"]
    assert detail["A4"].value == "Not enough data yet (need at least two monthly snapshots)."
    assert detail["A5"].value is None


def test_performance_export_acknowledges_first_baseline_for_portfolio_and_account(app, client, make_user):
    uid, username, password = make_user(username="perf-export-first-baseline", password="password123")
    with app.app_context():
        account_id = create_account(_account_payload(value=6000, monthly=150), uid)
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key) VALUES ('2026-05-01', ?, 6000, '2026-05')",
                (account_id,),
            )
            conn.commit()

    _login(client, username, password)
    workbook = _workbook_from_response(client.get("/performance/export.xlsx"))

    expected_detail_title = "First baseline saved."
    expected_detail_message = (
        "SteadyPlan has the first snapshot for this report. Come back after next month's monthly update "
        "and the month-by-month table will appear."
    )

    portfolio = workbook["Portfolio (Monthly)"]
    assert portfolio["A4"].value == expected_detail_title
    assert portfolio["A5"].value == expected_detail_message
    assert portfolio["A4"].value != "Not enough data yet (need at least two monthly snapshots)."

    account = workbook["ISA (Monthly)"]
    assert account["A4"].value == expected_detail_title
    assert account["A5"].value == expected_detail_message
    assert account["A4"].value != "Not enough data yet (need at least two monthly snapshots)."
