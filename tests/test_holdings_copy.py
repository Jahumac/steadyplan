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
