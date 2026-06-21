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

    expected_detail_title = "Your first baseline is saved"
    expected_detail_message = "Complete next month's monthly update and the month-by-month table will appear."

    portfolio = workbook["Portfolio (Monthly)"]
    assert portfolio["A4"].value == expected_detail_title
    assert portfolio["A5"].value == expected_detail_message
    assert "Come back after next month's monthly update" not in portfolio["A5"].value
    assert "SteadyPlan has the first snapshot for this report." not in portfolio["A5"].value
    assert portfolio["A4"].value != "Not enough data yet (need at least two monthly snapshots)."
    assert portfolio["A4"].value != "First baseline saved."
    assert portfolio["A4"].value != "Your first baseline is saved."

    account = workbook["ISA (Monthly)"]
    assert account["A4"].value == expected_detail_title
    assert account["A5"].value == expected_detail_message
    assert "Come back after next month's monthly update" not in account["A5"].value
    assert "SteadyPlan has the first snapshot for this report." not in account["A5"].value
    assert account["A4"].value != "Not enough data yet (need at least two monthly snapshots)."
    assert account["A4"].value != "First baseline saved."
    assert account["A4"].value != "Your first baseline is saved."



def test_performance_export_uses_live_current_month_values_for_end_balances(app, client, make_user):
    uid, username, password = make_user(username="perf-export-live-current", password="password123")
    with app.app_context():
        stale_id = create_account(_account_payload(name="Stale ISA", value=2500, monthly=100), uid)
        new_id = create_account(_account_payload(name="New SIPP", wrapper_type="SIPP", value=206, monthly=250), uid)
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key) VALUES ('2026-05-01', ?, 2000, '2026-05')",
                (stale_id,),
            )
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key) VALUES ('2026-06-01', ?, 2000, '2026-06')",
                (stale_id,),
            )
            conn.commit()

    _login(client, username, password)
    workbook = _workbook_from_response(client.get("/performance/export.xlsx"))

    summary = workbook["Summary"]
    rows = {summary.cell(row=r, column=1).value: summary.cell(row=r, column=10).value for r in range(5, summary.max_row + 1)}

    assert rows["Portfolio"] == 2706
    assert rows["Stale ISA"] == 2500
    assert rows["New SIPP"] == 206
    assert "New SIPP (Monthly)" in workbook.sheetnames


def test_performance_export_filters_to_requested_historical_window(app, client, make_user):
    uid, username, password = make_user(username="perf-export-window", password="password123")
    with app.app_context():
        account_id = create_account(_account_payload(value=1500, monthly=100), uid)
        with get_connection() as conn:
            for month_key, balance in [
                ("2026-01", 1000),
                ("2026-02", 1100),
                ("2026-03", 1200),
                ("2026-04", 1350),
                ("2026-05", 1500),
            ]:
                conn.execute(
                    "INSERT INTO monthly_snapshots (snapshot_date, account_id, balance, month_key) VALUES (?, ?, ?, ?)",
                    (f"{month_key}-01", account_id, balance, month_key),
                )
            conn.commit()

    _login(client, username, password)
    workbook = _workbook_from_response(client.get("/performance/export.xlsx?period=1M"))

    summary = workbook["Summary"]
    assert summary["B5"].value == "Apr 2026"
    assert summary["C5"].value == "May 2026"
    assert summary["D5"].value == 1

    portfolio = workbook["Portfolio (Monthly)"]
    assert portfolio["A5"].value == "May 2026"
    assert portfolio["A6"].value is None

    account = workbook["ISA (Monthly)"]
    assert account["A5"].value == "May 2026"
    assert account["A6"].value is None
