import re
from pathlib import Path

import app.routes.holdings as holdings_routes
from tests.path_helpers import STATIC_ROOT, TEMPLATES_ROOT


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
    css = STATIC_ROOT.joinpath("css/styles.css").read_text()

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


def test_budget_subnav_uses_tablet_safe_wrapping_before_mobile_switch():
    css = STATIC_ROOT.joinpath("css/styles.css").read_text()

    assert "@media (min-width: 601px) and (max-width: 900px) {" in css
    assert ".subnav-page.subnav-budget {" in css
    assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in css
    assert "white-space: normal;" in css
    assert "overflow-wrap: anywhere;" in css


import pytest


@pytest.mark.parametrize("path", TABBED_PAGE_PATHS)
def test_tabbed_pages_render_standard_tabs_without_turtle_icons(auth_client, path):
    response = auth_client.get(path, follow_redirects=True)

    assert response.status_code == 200
    html = response.data.decode()
    assert '<nav class="subnav subnav-page' in html
    assert 'hero-turtle-wrap' not in html


def test_progress_group_pages_highlight_progress_in_shell_nav(auth_client):
    grouped_pages = {
        "/goals/": False,
        "/projections/": True,
        "/performance/": True,
        "/performance/contributions/": True,
    }

    for path, expects_subnav_goal_link in grouped_pages.items():
        response = auth_client.get(path, follow_redirects=True)

        assert response.status_code == 200
        html = response.data.decode()
        assert 'href="/goals/" class="active">Progress</a>' in html
        if expects_subnav_goal_link:
            assert 'href="/goals/">Goals</a>' in html
        assert 'href="/goals/" class="bottom-nav-item bottom-nav-active">' in html
        assert '<span>Progress</span>' in html


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
    js = STATIC_ROOT.joinpath("js/app.js").read_text()

    assert "window.shellyConfirm({" in js
    assert "opts.icon" not in js
    assert ".shelly-modal-icon img" not in js
    assert "/static/icons/shelly/Accounts.png" not in js


def test_progress_future_estimate_table_uses_month_labels_not_age_labels_in_point_column():
    js = STATIC_ROOT.joinpath("js/app.js").read_text()

    assert '<tr><th>Month</th><th class="num">Age</th><th class="num">You pay/mo</th><th class="num">Future estimate</th></tr>' in js
    assert '<tr><th>Point</th><th class="num">Age</th><th class="num">You pay/mo</th><th class="num">Future estimate</th></tr>' not in js


def test_pwa_offline_comments_match_privacy_first_caching_behavior():
    js = STATIC_ROOT.joinpath("js/app.js").read_text()
    sw = STATIC_ROOT.joinpath("sw.js").read_text()

    assert "API-style JSON calls: network-only, never cached" in sw
    assert "Authenticated financial pages: network-only with offline fallback" in sw
    assert "networkOnlyAPI(request)" in sw
    assert "function networkFirstAPI" not in sw
    assert "cache response for offline reads" not in sw
    assert "Warm the cache so every top-level page works offline next time" not in js
    assert "PAGES_TO_WARM" not in js


def test_allowance_hash_links_open_targeted_log_panels():
    js = STATIC_ROOT.joinpath("js/app.js").read_text()

    assert "window.location.hash ? window.location.hash.slice(1) : ''" in js
    assert "panel.classList.contains('allowance-log-panel')" in js
    assert "document.getElementById('isa')" in js
    assert "panel.classList.remove('hidden')" in js


def test_account_wizard_first_account_focus_reads_from_existing_form_root():
    js = STATIC_ROOT.joinpath("js/app.js").read_text()

    assert "var firstAccountFocus = form.getAttribute('data-first-account-focus') === 'true';" in js
    assert "wizardRoot.getAttribute('data-first-account-focus')" not in js


def test_lifetime_isa_preview_js_uses_specific_bonus_copy():
    js = STATIC_ROOT.joinpath("js/app.js").read_text()

    assert "+ Lifetime ISA bonus (25%)" in js
    assert "+ government bonus (25%)" not in js
    assert "Your Lifetime ISA bonus adds 25% on top (up to £1,000/year)." in js
    assert "The government tops it up with a lovely 25% bonus (up to £1,000/year)." not in js
    assert "How much do you put into this ISA each month? This helps SteadyPlan estimate the future. You can update it later." in js
    assert "How much do you put into this ISA each month? This feeds into scenario estimates. You can update it later." not in js
    assert "How much do you put into this ISA each month? This feeds into projections. You can update it later." not in js
    assert "How much do you put into this ISA each month? This feeds into projections — an estimate is fine." not in js
    assert "How much do you put into this ISA each month? Even an estimate helps with projections." not in js
    assert "How much do you put into this ISA each month? Even a rough figure helps with projections." not in js


def test_account_wizard_hints_use_plain_neutral_tone():
    js = STATIC_ROOT.joinpath("js/app.js").read_text()
    html = TEMPLATES_ROOT.joinpath("accounts.html").read_text()
    wizard_html = TEMPLATES_ROOT.joinpath("_account_create_wizard.html").read_text()

    assert "NS&amp;I, tax-free prize planning" in wizard_html
    assert "NS&amp;I, tax-free prize estimate" not in wizard_html
    assert "How much do you add to this Cash ISA each month?" in js
    assert "How much do you stash away in this Cash ISA each month?" not in js
    assert "Prize draws are tracked separately; future estimates use the planning rate." in js
    assert "Prize draws are tracked separately; scenario estimates use the planning rate." not in js
    assert "Prize draws are tracked separately; projections use the planning rate." not in js
    assert "Prize draws are tracked separately; projections use a cautious estimate." not in js
    assert "Prize draws are tracked separately; projections use a gentle estimate." not in js
    assert "Monthly Update now has somewhere real to work from." in js
    assert "Monthly Update now has something real to work from." in js
    assert "it can help with future estimates whenever you need it to." in js
    assert "it can feed scenario estimates whenever you need it to." not in js
    assert "is live!" not in js
    assert "He's already crunching the numbers" not in js
    assert "check your dashboard to see how things are shaping up" not in js
    assert "You'll see it on your dashboard and in projections straight away." not in js
    assert "Premium Bonds do not pay guaranteed interest. Use this as a planning assumption only; NS&I can change the prize fund rate." in js
    assert "Premium Bonds do not pay guaranteed interest. Use this as a planning estimate only; NS&I can change the prize fund rate." not in js
    assert "Premium Bonds do not pay guaranteed interest. This is a calm estimate only; NS&I can change the prize fund rate." not in js
    assert "Your provider adds a 25% basic-rate pension tax top-up." in js
    assert "Your provider adds 25% basic-rate tax relief on top automatically." not in js
    assert "Your provider claims 25% tax relief from HMRC automatically." not in js
    assert "your provider adds a 20% basic-rate pension tax top-up." in js
    assert "your provider adds 20% basic-rate tax relief for you (e.g. NEST)." not in js
    assert "your provider claims 20% tax relief from HMRC (e.g. NEST)." not in js
    assert "Your provider adds a 20% basic-rate pension tax top-up. Claim the extra " in js
    assert " through Self Assessment — it is paid back to you, not into the pension." in js
    assert "Your provider claims 20% automatically." not in js
    assert "through your self-assessment tax return — it goes to you, not the pension." not in js
    assert "free money, basically" not in js
    assert "You can always update this later." in js
    assert "No pressure — you can always update this later." not in js
    assert "Use the usual growth estimate from Settings" in wizard_html
    assert "Use default growth rate (from Settings)" not in wizard_html
    assert "Set 0 to use the investment day from Settings." in wizard_html
    assert "Set 0 to use salary day from Settings." not in wizard_html
    assert 'data-first-account-focus="{{ \'true\' if is_first_account_focus else \'false\' }}"' in wizard_html
    assert "Your new account is ready. You'll see it in Accounts straight away, and Monthly Update now has somewhere real to work from." in wizard_html
    assert "Your new account is ready. You'll see it in Accounts straight away, and it can help with future estimates whenever you need it to." in wizard_html
    assert "Your new account is ready. You'll see it in Accounts straight away, and it can feed scenario estimates whenever you need it to." not in wizard_html
    assert "Your new account is ready. You'll see it in Accounts and it will be included in scenario estimates straight away." not in wizard_html
    assert "The contribution in use this month is shown at the top." in html
    assert "The <strong>currently active</strong> contribution is shown at the top." not in html
    assert "Use the day the pension money actually lands or gets invested" in html
    assert "Use if workplace pension invests later than your investment day" not in html
    assert "Set 0 to use the investment day from Settings." in html
    assert "Set 0 to use the investment day from your scenario estimate assumptions." not in html
    assert "Use if workplace pension invests later than salary day" not in html
    assert "Set 0 to use salary day from Settings." not in html


def test_account_wizard_scripts_are_deferred_until_the_wizard_markup_exists():
    base_html = TEMPLATES_ROOT.joinpath("base.html").read_text()

    assert '<script defer src="{{ static_v(\'js/charts.js\') }}"></script>' in base_html
    assert '<script defer src="{{ static_v(\'js/app.js\') }}"></script>' in base_html
    assert '<script src="{{ static_v(\'js/app.js\') }}"></script>' not in base_html


def test_account_wizard_template_selection_updates_visible_state_and_continue_copy():
    js = STATIC_ROOT.joinpath("js/app.js").read_text()
    css = STATIC_ROOT.joinpath("css/styles.css").read_text()

    assert "function updateTemplateSelection(selectedBtn, tpl)" in js
    assert "other.setAttribute('aria-pressed', isSelected ? 'true' : 'false');" in js
    assert "templateStatus.textContent = 'Selected: ' + selectedLabel + '. Name, wrapper type and balance method have been filled in.';" in js
    assert "basicsNextBtn.textContent = 'Continue with ' + selectedLabel;" in js
    assert "updateTemplateSelection(btn, tpl);" in js
    wizard_html = TEMPLATES_ROOT.joinpath("_account_create_wizard.html").read_text()

    assert ".cw-template-selected strong" in css
    assert "border-color: rgba(56,189,248,0.72);" in css
    assert ".cw-template-action" in css
    assert 'data-cw-template-action>Choose template</span>' in wizard_html
    assert "var action = other.querySelector('[data-cw-template-action]');" in js
    assert "if (action) action.textContent = isSelected ? 'Selected' : 'Choose template';" in js
    assert ".cw-template::after" not in css
    assert "content: \"Choose\";" not in css
    assert "content: \"Selected\";" not in css
    assert "form.querySelectorAll('[data-cw-template]').forEach(function(other) {\n            other.classList.toggle('cw-template-selected', other === btn);" not in js


def test_account_wizard_template_bundle_keeps_templates_and_manual_edits_in_sync():
    js = STATIC_ROOT.joinpath("js/app.js").read_text()
    wizard_html = TEMPLATES_ROOT.joinpath("_account_create_wizard.html").read_text()

    expected_templates = {
        "stocks_isa",
        "cash_isa",
        "lifetime_isa",
        "cash_savings",
        "workplace_pension",
        "sipp",
        "premium_bonds",
        "gia",
    }
    html_templates = set(re.findall(r'data-cw-template="([^"]+)"', wizard_html))
    js_templates = set(re.findall(r"^\s{8}([a-z_]+): \{", js, flags=re.MULTILINE)) & expected_templates

    assert html_templates == expected_templates
    assert js_templates == expected_templates
    assert wizard_html.count('aria-pressed="false"') == len(expected_templates)
    assert wizard_html.count('title="Use the ') == len(expected_templates)
    assert "'Lifetime ISA':               { cat: 'ISA',     bal: 'manual'" in js
    assert "lifetime_isa: {" in js
    assert "valuation: 'manual'" in js
    assert "function clearTemplateSelection(reason)" in js
    assert "resetTemplateSelectionOnManualEdit" in js
    assert "nameEl.addEventListener('input', resetTemplateSelectionOnManualEdit);" in js
    assert "wrapperEl.addEventListener('change', resetTemplateSelectionOnManualEdit);" in js
    assert "basicsNextBtn.textContent = 'Continue';" in js
    assert "Choose a template above or fill in the details manually." in js


def test_daily_portfolio_period_buttons_are_scoped_to_the_chart_not_overview_headline_toggle():
    js = STATIC_ROOT.joinpath("js/charts.js").read_text()

    assert "var dailyPortfolioBtns = Array.prototype.filter.call(" in js
    assert "card && card.querySelector('#dailyPortfolioChart') && btn.dataset.period" in js
    assert "dailyPortfolioBtns.forEach(function(btn) {" in js
    assert "dailyPortfolioBtns.forEach(function(b) { b.classList.remove('active'); });" in js
    assert "document.querySelectorAll('.period-btn').forEach(function(btn) {" not in js


def test_budget_setup_page_does_not_render_turtle_icon(auth_client):
    response = auth_client.get("/budget/items/?month=2026-04", follow_redirects=True)

    assert response.status_code == 200
    html = response.data.decode()
    assert "Budget Setup" in html
    assert "Your take-home pay and any side income. This is the money you can allocate across the rest of the budget." in html
    assert "Your take-home pay and any side income — used to show how much is available to allocate." not in html
    assert "Set aside money for future goals. Items marked <em>linked</em> use the monthly payment from that account." in html
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
