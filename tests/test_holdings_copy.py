import app.routes.holdings as holdings_routes
from app.models import add_holding_catalogue_item, get_connection


def _login(client, username, password):
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)


def test_holding_detail_uses_sentence_case_price_stat_labels(client, make_user):
    uid, username, password = make_user(username="holding-detail-copy", password="password123")
    with client.application.app_context():
        catalogue_id = add_holding_catalogue_item(
            {
                "holding_name": "Vanguard FTSE Global All Cap",
                "ticker": "",
                "asset_type": "Fund",
                "bucket": "Global Equity",
                "notes": "",
            },
            uid,
        )
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE holding_catalogue
                SET last_price = 123.45,
                    price_currency = 'GBP',
                    price_change_pct = 0.67,
                    price_updated_at = '2026-06-22T08:00:00+00:00'
                WHERE id = ? AND user_id = ?
                """,
                (catalogue_id, uid),
            )
            conn.commit()

    _login(client, username, password)
    response = client.get(f"/holdings/{catalogue_id}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Latest price" in html
    assert "Day change" in html
    assert "Latest Price" not in html
    assert "Day Change" not in html


def test_holdings_list_uses_plain_instrument_and_day_change_labels(client, make_user):
    uid, username, password = make_user(username="holdings-list-copy", password="password123")
    with client.application.app_context():
        catalogue_id = add_holding_catalogue_item(
            {
                "holding_name": "Vanguard FTSE Global All Cap",
                "ticker": "VWRP",
                "asset_type": "ETF",
                "bucket": "Global Equity",
                "notes": "",
            },
            uid,
        )
        with get_connection() as conn:
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, category, valuation_mode, current_value, is_active)
                VALUES (?, 'Stocks ISA', 'Stocks & Shares ISA', 'ISA', 'holdings', 0, 1)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO holdings (account_id, holding_catalogue_id, holding_name, ticker, asset_type, value, units, price)
                VALUES (?, ?, 'Vanguard FTSE Global All Cap', 'VWRP', 'ETF', 1234, 10, 123.4)
                """,
                (account_id, catalogue_id),
            )
            conn.commit()

    _login(client, username, password)
    response = client.get("/holdings/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "My instruments" in html
    assert "Day change" in html
    assert "My Instruments" not in html
    assert "Day %" not in html


def test_holding_history_uses_comparison_line_copy_for_lagging_fund(client, make_user, monkeypatch):
    uid, username, password = make_user(username="holding-comparison-copy", password="password123")
    with client.application.app_context():
        catalogue_id = add_holding_catalogue_item(
            {
                "holding_name": "Example Global Fund",
                "ticker": "EXGF",
                "asset_type": "Fund",
                "bucket": "Global Equity",
                "notes": "",
            },
            uid,
        )

    monkeypatch.setattr(
        holdings_routes,
        "fetch_history",
        lambda ticker, period=None: [
            {"date": "2025-06-22", "price": 100.0},
            {"date": "2026-06-22", "price": 99.0},
        ],
    )

    _login(client, username, password)
    response = client.get(f"/holdings/{catalogue_id}?period=1y")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "behind</strong> the comparison line over this period" in html
    assert "behind</strong> the benchmark over this period" not in html
