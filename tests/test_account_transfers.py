from app.models import create_account, fetch_account, fetch_cash_flow_events_for_account, get_connection


def _account(name, wrapper_type, value=0, monthly=0):
    return {
        "id": None,
        "name": name,
        "provider": name.split()[0],
        "wrapper_type": wrapper_type,
        "category": "Pension" if "pension" in wrapper_type.lower() or "sipp" in wrapper_type.lower() else "ISA",
        "tags": "Retirement",
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
        "last_updated": "2026-06-01",
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
        "include_in_budget": True,
        "pre_salary": False,
    }


def _login(client, username, password):
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)


def test_provider_transfer_moves_value_without_archiving_source_history(app, client, make_user):
    uid, username, password = make_user(username="acct-transfer", password="password123")
    with app.app_context():
        source_id = create_account(_account("InvestEngine SIPP", "SIPP", 15000, 250), uid)
        dest_id = create_account(_account("Trading 212 SIPP", "SIPP", 500, 0), uid)

    _login(client, username, password)
    page = client.get(f"/accounts/{source_id}")
    body = page.data.decode("utf-8", errors="ignore")
    assert "Move this account to another provider/account" in body
    assert "does not count the movement as a new contribution or allowance use" in body
    assert 'action="/accounts/{}/transfers/add"'.format(source_id) in body

    resp = client.post(
        f"/accounts/{source_id}/transfers/add",
        data={
            "transfer_date": "2026-07-15",
            "transfer_amount": "15000",
            "to_account_id": str(dest_id),
            "transfer_scope": "full",
            "update_balances": "1",
            "transfer_note": "Provider transfer reference ABC123",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 302

    with app.app_context():
        source = fetch_account(source_id, uid)
        dest = fetch_account(dest_id, uid)
        assert source["is_active"] == 1  # keep old snapshots in performance/history queries
        assert float(source["current_value"] or 0) == 0.0
        assert float(source["monthly_contribution"] or 0) == 0.0
        assert "Transferred to Trading 212 SIPP on 2026-07-15" in (source["notes"] or "")
        assert float(dest["current_value"] or 0) == 15500.0
        assert "Transfer received from InvestEngine SIPP on 2026-07-15" in (dest["notes"] or "")

        source_events = fetch_cash_flow_events_for_account(source_id, uid)
        dest_events = fetch_cash_flow_events_for_account(dest_id, uid)
        assert len(source_events) == 1
        assert len(dest_events) == 1
        assert source_events[0]["kind"] == "account_transfer_out"
        assert float(source_events[0]["amount"]) == -15000.0
        assert source_events[0]["counterparty_account_id"] == dest_id
        assert source_events[0]["allowance_effect"] == "none"
        assert dest_events[0]["kind"] == "account_transfer_in"
        assert float(dest_events[0]["amount"]) == 15000.0
        assert dest_events[0]["counterparty_account_id"] == source_id
        assert dest_events[0]["allowance_effect"] == "none"

        rows = get_connection().execute(
            "SELECT account_id, balance FROM monthly_snapshots WHERE month_key = '2026-07' ORDER BY account_id"
        ).fetchall()
        assert [(r["account_id"], float(r["balance"])) for r in rows] == [
            (source_id, 0.0),
            (dest_id, 15500.0),
        ]


def test_provider_transfer_is_wrapper_neutral_for_stocks_isa_and_lisa(app, client, make_user):
    uid, username, password = make_user(username="acct-transfer-isa", password="password123")
    with app.app_context():
        isa_source = create_account(_account("Old ISA", "Stocks & Shares ISA", 20000, 100), uid)
        isa_dest = create_account(_account("New ISA", "Stocks & Shares ISA", 0, 0), uid)
        lisa_source = create_account(_account("Old LISA", "Lifetime ISA", 4000, 100), uid)
        lisa_dest = create_account(_account("New LISA", "Lifetime ISA", 100, 0), uid)

    _login(client, username, password)
    for source_id, dest_id, amount in [
        (isa_source, isa_dest, "20000"),
        (lisa_source, lisa_dest, "4000"),
    ]:
        resp = client.post(
            f"/accounts/{source_id}/transfers/add",
            data={
                "transfer_date": "2026-08-01",
                "transfer_amount": amount,
                "to_account_id": str(dest_id),
                "transfer_scope": "full",
                "update_balances": "1",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

    with app.app_context():
        for account_id in [isa_source, lisa_source]:
            events = fetch_cash_flow_events_for_account(account_id, uid)
            assert len(events) == 1
            assert events[0]["kind"] == "account_transfer_out"
            assert events[0]["allowance_effect"] == "none"
        assert float(fetch_account(isa_dest, uid)["current_value"] or 0) == 20000.0
        assert float(fetch_account(lisa_dest, uid)["current_value"] or 0) == 4100.0
