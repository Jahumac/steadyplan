from pathlib import Path

import app.routes.holdings as holdings_routes


TABBED_PAGE_PATHS = [
    "/budget/",
    "/monthly-review/",
    "/allowance/",
    "/budget/trend/",
    "/budget/debts/",
    "/goals/",
    "/projections/",
    "/performance/",
    "/performance/contributions/",
    "/settings/",
    "/settings/?mode=diagnostics",
]

MAIN_HERO_PATHS = [
    "/",
    "/accounts/",
    "/planning/",
]


def test_tab_css_uses_one_consistent_mobile_safe_component():
    css = Path("/opt/data/steadyplan/app/static/css/styles.css").read_text()

    assert ".subnav-page {" in css
    assert ".subnav-history," in css
    assert ".subnav-mobile-family {" in css
    assert "display: grid;" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in css
    assert "white-space: normal;" in css
    assert "grid-column: 1 / -1;" in css
    assert "flex-wrap: nowrap;" in css
    assert "scroll-snap-type: x proximity;" in css
    assert ".subnav-page.subnav-budget," in css
    assert ".subnav-page.subnav-goals {" in css
    assert "#history-period-tabs a[aria-current=\"page\"]" in css
    assert ".accounts-hero-actions," in css
    assert ".accounts-hero-badges {" in css
    assert ".subnav-budget a:nth-child" not in css
    assert ".subnav-goals a:nth-child" not in css


import pytest


@pytest.mark.parametrize("path", TABBED_PAGE_PATHS)
def test_tabbed_pages_render_standard_tabs_without_turtle_icons(auth_client, path):
    response = auth_client.get(path, follow_redirects=True)

    assert response.status_code == 200
    html = response.data.decode()
    assert '<nav class="subnav subnav-page' in html
    assert 'hero-turtle-wrap' not in html


@pytest.mark.parametrize("path", MAIN_HERO_PATHS)
def test_main_mobile_hero_pages_do_not_render_turtle_icons(auth_client, path):
    response = auth_client.get(path, follow_redirects=True)

    assert response.status_code == 200
    html = response.data.decode()
    assert 'hero-turtle-wrap' not in html
    assert 'onboarding-turtle' not in html


def test_holding_detail_uses_standard_tab_nav_for_history_periods(app, client, make_user, monkeypatch):
    user_id, username, password = make_user(username="tabs-user", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            account_id = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active) VALUES (?, 'ISA', 1000, 1)",
                (user_id,),
            ).lastrowid
            conn.execute(
                "INSERT INTO holdings (account_id, holding_name, ticker, value, units, price) VALUES (?, 'World ETF', 'VWRP', 1000, 10, 100)",
                (account_id,),
            )
            catalogue_id = conn.execute(
                "INSERT INTO holding_catalogue (user_id, holding_name, ticker, asset_type, bucket, is_active) VALUES (?, 'World ETF', 'VWRP', 'ETF', 'Global Equity', 1)",
                (user_id,),
            ).lastrowid
            conn.commit()

    monkeypatch.setattr(
        holdings_routes,
        "fetch_history",
        lambda ticker, period=None: [
            {"date": "2026-01-01", "price": 100.0},
            {"date": "2026-03-01", "price": 104.0},
            {"date": "2026-06-01", "price": 110.0},
        ],
    )

    response = client.get(f"/holdings/{catalogue_id}?period=6m", follow_redirects=True)

    assert response.status_code == 200
    html = response.data.decode()
    assert 'id="history-period-tabs"' in html
    assert 'class="subnav subnav-history"' in html
    assert 'aria-label="Price history periods"' in html
    assert 'class="subnav-active" aria-current="page">6M<' in html

    history_nav = html.split('id="history-period-tabs"', 1)[1].split('</nav>', 1)[0]
    assert 'badge-primary-action' not in history_nav
    assert 'badge-meta' not in history_nav
