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
    "/holdings/",
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
    assert ".site-logo-mark {" in css
    assert "width: 1.85rem;" in css
    assert "height: 1.85rem;" in css
    assert "align-items: center;" in css
    assert "margin-left: auto;" in css
    assert "border-color: rgba(148, 163, 184, 0.18);" in css
    assert "object-fit: contain;" in css
    assert ".hero-turtle-wrap {" not in css
    assert ".onboarding-turtle {" not in css
    assert ".shelly-modal-icon {" not in css
    assert ".site-logo-icon {" not in css
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


def test_shared_shell_does_not_render_confirm_modal_mascot_icon(auth_client):
    response = auth_client.get("/", follow_redirects=True)

    assert response.status_code == 200
    html = response.data.decode()
    assert 'id="shelly-confirm"' in html
    assert 'brand/steadyplan-mark.png' in html
    assert 'icons/favicon-32.png' in html
    assert 'class="site-logo-mark"' in html
    assert 'class="nav-logout"' in html
    assert 'site-logo-icon' not in html
    assert 'icon-192.png' not in html
    assert 'shelly-modal-icon' not in html
    assert 'shelly-inline-icon shelly-icon-lg' not in html


def test_confirm_helper_js_no_longer_carries_dead_mascot_icon_wiring():
    js = Path("/opt/data/steadyplan/app/static/js/app.js").read_text()

    assert "window.shellyConfirm({" in js
    assert "opts.icon" not in js
    assert ".shelly-modal-icon img" not in js
    assert "/static/icons/shelly/Accounts.png" not in js


def test_lifetime_isa_preview_js_uses_specific_bonus_copy():
    js = Path("/opt/data/steadyplan/app/static/js/app.js").read_text()

    assert "+ Lifetime ISA bonus (25%)" in js
    assert "+ government bonus (25%)" not in js
    assert "Your Lifetime ISA bonus adds 25% on top (up to £1,000/year)." in js
    assert "The government tops it up with a lovely 25% bonus (up to £1,000/year)." not in js
    assert "How much do you put into this ISA each month? Even an estimate helps with projections." in js
    assert "How much do you put into this ISA each month? Even a rough figure helps with projections." not in js


def test_account_wizard_hints_use_plain_neutral_tone():
    js = Path("/opt/data/steadyplan/app/static/js/app.js").read_text()

    assert "How much do you add to this Cash ISA each month?" in js
    assert "How much do you stash away in this Cash ISA each month?" not in js
    assert "Prize draws are tracked separately; projections use a cautious estimate." in js
    assert "Prize draws are tracked separately; projections use a gentle estimate." not in js
    assert "Your provider adds 25% basic-rate tax relief on top automatically." in js
    assert "Your provider claims 25% tax relief from HMRC automatically." not in js
    assert "your provider adds 20% basic-rate tax relief for you (e.g. NEST)." in js
    assert "your provider claims 20% tax relief from HMRC (e.g. NEST)." not in js
    assert "free money, basically" not in js
    assert "You can always update this later." in js
    assert "No pressure — you can always update this later." not in js


def test_budget_setup_page_does_not_render_turtle_icon(auth_client):
    response = auth_client.get("/budget/items/?month=2026-04", follow_redirects=True)

    assert response.status_code == 200
    html = response.data.decode()
    assert "Budget Setup" in html
    assert "Set aside money for future goals. Items marked <em>linked</em> use the monthly contribution from that account." in html
    assert "Pay yourself first! Items marked <em>linked</em> pull their amount from your account's monthly contribution automatically." not in html
    assert "Minimum payments and extra debt overpayments — use this section to track what you plan to repay this month." in html
    assert "Minimum payments and extra chunks you're throwing at debt — every pound here gets you closer to freedom." not in html
    assert 'hero-turtle-wrap' not in html


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
