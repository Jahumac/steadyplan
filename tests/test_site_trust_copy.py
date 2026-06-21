from pathlib import Path
from tests.path_helpers import DOCS_ROOT, REPO_ROOT, SITE_ROOT


SITE_ROOT = SITE_ROOT
README_PATH = REPO_ROOT / "README.md"
VOICE_AND_COPY_PATH = DOCS_ROOT / "VOICE_AND_COPY.md"
PRODUCT_TRUTH_PATH = DOCS_ROOT / "PRODUCT_TRUTH.md"
CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"
SITE_README_PATH = SITE_ROOT / "README.md"
ROADMAP_PATH = REPO_ROOT / "STEADYPLAN_ROADMAP_2026-05-29.md"
ROADMAP_EXECUTION_PATH = DOCS_ROOT / "plans/2026-05-29-roadmap-execution.md"


def _read(relative_path: str) -> str:
    return (SITE_ROOT / relative_path).read_text()


def _read_readme() -> str:
    return README_PATH.read_text()


def _read_voice_and_copy() -> str:
    return VOICE_AND_COPY_PATH.read_text()


def _read_product_truth() -> str:
    return PRODUCT_TRUTH_PATH.read_text()


def _read_changelog() -> str:
    return CHANGELOG_PATH.read_text()


def _read_site_readme() -> str:
    return SITE_README_PATH.read_text()


def _read_roadmap() -> str:
    return ROADMAP_PATH.read_text()


def _read_roadmap_execution() -> str:
    return ROADMAP_EXECUTION_PATH.read_text()


def test_homepage_trust_card_mentions_restore_preview_and_safety_backup():
    html = _read("index.html")

    assert 'content="SteadyPlan is a self-hosted UK finance planning and visibility tool. Understand where you are, what is cash-accessible now, what invested money is still reachable, what is restricted, and how today’s choices connect to long-term scenarios."' in html
    assert 'content="SteadyPlan is a self-hosted UK finance planning and visibility tool. Understand where you are, what’s available now vs locked for later, and how today’s choices connect to long-term scenarios."' not in html
    assert "SteadyPlan uses a local SQLite database, keeps backup and restore guidance close to the product, and now groups Settings into everyday setup, safety and recovery, and optional access so the trust story is explicit rather than implied." in html
    assert "SteadyPlan uses a local SQLite database, keeps backup and restore guidance close to the product, and now surfaces Diagnostics plus trust-posture checks so the trust story is explicit rather than implied." not in html
    assert "See how JSON exports, whole-instance backups, and restore checks fit together" not in html


def test_tour_trust_copy_matches_restore_safety_story():
    html = _read("tour.html")

    assert "SteadyPlan stores your data locally in a SQLite database on your own server/NAS/desktop. There is no hosted account and no public signup, and the safest hands-on evaluation path is still your own local install." in html
    assert "Optional external price lookups can contact providers for ticker data. Everything else stays local unless you choose otherwise." in html
    assert "<h2 class=\"section-title\">Data ownership</h2>" in html
    assert "Cash-accessible, invested-accessible, restricted, and locked-for-later money" in html
    assert "Long-term planning is easier when you separate cash you could reach now, invested money you could sell, money with conditions, and money reserved for later." in html
    assert "Settings keeps safety and recovery links visible" in html
    assert "Settings groups data ownership, JSON export, restore checks, backup health, assistant scope, and read-only broker review so trust is inspectable without digging through one long admin page." in html
    assert "Diagnostics keep trust visible" not in html
    assert "Settings keeps backup health, restore boundaries, assistant scope, and read-only broker review close to the product so trust is inspectable." not in html
    assert "Accessible vs locked money" not in html
    assert "Long-term planning is easier when you keep “available now” separate from money reserved for later." not in html


def test_docs_hub_and_backups_page_explain_automatic_pre_restore_backup():
    docs_index = _read("docs/index.html")
    backups = _read("docs/backups.html")

    assert "restore preview checks plus the automatic pre-restore safety backup" in docs_index
    assert "Trust checkpoint" in backups
    assert "In-app restore is a validated, two-step overwrite flow for one user at a time." in backups
    assert "During in-app restore, SteadyPlan validates the export first and then creates a fresh whole-instance SQLite backup automatically before confirmed overwrite." in backups
    assert "If that safety backup cannot be created, restore stops and leaves current data unchanged." in backups
    assert "You validate the export first, then confirm overwrite for that user only." in backups
    assert "download a per-user JSON export and create a whole-instance SQLite backup from Diagnostics" not in backups


def test_backup_boundary_copy_distinguishes_json_exports_from_whole_instance_backups():
    privacy = _read("docs/privacy.html")
    readme = _read_readme()
    changelog = _read_changelog()

    assert "Per-user JSON exports are useful, portable safety copies for one user." in privacy
    assert "They are not the same as a whole-instance appdata backup" in privacy
    assert "Per-user JSON exports are useful, portable backups" not in privacy
    assert "### JSON Export & Restore" in readme
    assert "Download a user-scoped JSON export from **Settings**, and restore from that file" in readme
    assert "validate a JSON export in Settings" in readme
    assert "- Data Health, JSON export/restore, Diagnostics, and trust-posture checks close to the product" in readme
    assert "### Backup & Restore (JSON)" not in readme
    assert "Export a user-scoped JSON backup from **Settings**" not in readme
    assert "validate a JSON backup in Settings" not in readme
    assert "- JSON backup/export and restore flow (done)." not in readme
    assert "User JSON export in Settings and a hardened JSON restore flow" in changelog
    assert "User JSON backup/export in Settings and a hardened JSON restore flow" not in changelog


def test_docs_and_install_pages_explain_safest_evaluation_path():
    docs_index = _read("docs/index.html")
    install = _read("docs/install.html")
    reverse_proxy = _read("docs/reverse-proxy.html")
    tour = _read("tour.html")
    readme = _read_readme()

    assert "Safest way to evaluate" in docs_index
    assert "Start with the <a href=\"../tour.html\">product tour</a> and docs." in docs_index
    assert "A public read-only demo can be useful, but it should be treated as an explicit opt-in host choice rather than the default way to try SteadyPlan." in docs_index
    assert "Evaluate safely first" in install
    assert "Best order: screenshots/tour first, then your own local install on LAN or VPN if you want hands-on evaluation." in install
    assert "Public demo access can be useful, but only as a deliberate read-only setup by the host" in install
    assert "docker compose pull" in install
    assert "A plain restart on its own will keep the old image." in install
    assert "Safest default is LAN/VPN access. Public exposure requires a trusted reverse proxy and HTTPS." in tour
    assert "Documentation" in tour
    assert "Safest order: screenshots/tour first, then your own local install on LAN or VPN for hands-on evaluation." in readme
    assert "the host can offer `/demo` (or the “Open read-only demo” button on the login page) for sample-data evaluation." in readme
    assert "Treat that public demo as an explicit host choice, not the default trust path for real use." in readme
    assert "Then you can use `/demo` (or the “Try demo” button on the login page)." not in readme
    assert "FORWARDED_ALLOW_IPS" in reverse_proxy
    assert "advanced choice rather than the default" in reverse_proxy



def test_public_site_supports_manual_dark_mode_toggle():
    homepage = _read("index.html")
    about = _read("about.html")
    docs_index = _read("docs/index.html")
    site_css = _read("assets/site.css")
    theme_toggle_js = _read("assets/theme-toggle.js")
    site_readme = _read_site_readme()

    assert '<meta name="color-scheme" content="light dark">' in homepage
    assert 'data-theme-toggle' in homepage
    assert 'site.css?v=20260608a' in homepage
    assert 'theme-toggle.js?v=20260607a' in homepage
    assert 'class="window-body brand-showcase-panel"' in homepage
    assert 'class="brand-showcase-mark"' in homepage
    assert 'opacity:0.95' not in homepage
    assert 'class="window-body brand-showcase-panel"' in about
    assert 'class="brand-showcase-mark"' in about
    assert 'opacity:0.95' not in about
    assert '<meta name="color-scheme" content="light dark">' in docs_index
    assert 'data-theme-toggle' in docs_index
    assert 'site.css?v=20260608a' in docs_index
    assert 'theme-toggle.js?v=20260607a' in docs_index
    assert ':root[data-theme="dark"] {' in site_css
    assert '.theme-toggle[aria-pressed="true"] {' in site_css
    assert '.brand-showcase-panel {' in site_css
    assert '.brand-showcase-mark {' in site_css
    assert "steadyplan-site-theme" in theme_toggle_js
    assert "Switch to dark mode" in theme_toggle_js
    assert "Switch to light mode" in theme_toggle_js
    assert "roadmap.html" in site_readme
    assert "manual light/dark toggle" in site_readme
    assert "live Cloudflare Pages deployment" in site_readme
    assert "future static host deployment" not in site_readme


def test_repo_docs_match_current_monthly_update_assistant_and_roadmap_story():
    readme = _read_readme()
    changelog = _read_changelog()
    roadmap = _read_roadmap()
    roadmap_execution = _read_roadmap_execution()

    assert "### Monthly Update" in readme
    assert "### Broker snapshot review beta" in readme
    assert "Settings includes an optional **Trading 212 broker snapshot review (beta)** flow with saved broker snapshot connections." in readme
    assert "These saved broker snapshot connections stay read-only and currently focus on Invest and Stocks ISA accounts." in readme
    assert "Settings includes an optional **Trading 212 broker snapshot review (beta)** flow with read-only broker access." not in readme
    assert "This currently focuses on Invest and Stocks ISA accounts." not in readme
    assert "### Read-only broker connection beta" not in readme
    assert "### Assistant access" in readme
    assert "### Diagnostics & backup health" in readme
    assert "Public site supports a manual light/dark toggle without a build step" in readme
    assert "Settings at a glance now groups everyday setup, safety and recovery, and optional access." in changelog
    assert "Account creation templates now visibly select and fill in the account name, wrapper type, and balance method." in changelog
    assert "Settings density pass groups everyday setup, safety and recovery, and optional access." not in changelog
    assert "Account creation template cards were polished." not in changelog
    assert "Monthly Review" not in readme
    assert "It's designed specifically for **UK investors** — ISAs, SIPPs, Lifetime ISAs, workplace pensions, and taxable accounts (GIAs) — with GBP currency, UK tax year tracking, CSV import from major UK brokers, and an optional Trading 212 broker snapshot review beta for preview-first broker account review." in readme
    assert "It's designed specifically for **UK investors** — ISAs, SIPPs, Lifetime ISAs, workplace pensions, and taxable accounts (GIAs) — with GBP currency, UK tax year tracking, CSV import from major UK brokers, and an optional Trading 212 broker snapshot review beta for API-first account review." not in readme
    assert "See where you stand today, what is available now vs later, and how monthly decisions connect to long-term scenario estimates" not in readme
    assert "Settings includes optional scoped **Assistant access** for a personal Pip setup." in readme
    assert "Optional Trading 212 broker snapshot review beta with saved broker snapshot connections and a preview-before-apply review flow" in readme
    assert "Optional Trading 212 broker snapshot review beta with preview-before-apply review flow" not in readme
    assert "Optional read-only Trading 212 connection beta with preview-before-apply review flow" not in readme
    assert "Public website with Tour, Roadmap, docs hub, and optional read-only demo path" in readme
    assert "taxable accounts (GIAs)" in readme
    assert "taxable account (GIA)" in readme
    assert "│   ├── planning.py        # Cash-accessible, invested-accessible, restricted, and locked-for-later money view and insights" in readme
    assert "workplace pensions, GIAs" not in readme
    assert "Workplace Pension, GIA, and more" not in readme
    assert "│   ├── planning.py        # Accessible, restricted, and locked money view and insights" not in readme
    assert "│   ├── planning.py        # Accessible vs locked money view and insights" not in readme
    assert "understand cash-accessible, invested-accessible, restricted, and locked-for-later money" in roadmap
    assert "see cash-accessible, invested-accessible, restricted, and locked-for-later money" in roadmap
    assert "clear scenario-estimate caveats" in roadmap
    assert "clear projection caveats" not in roadmap
    assert "## Current standing (June 2026)" in roadmap
    assert "preview-first broker review without forcing users away from manual/CSV tracking" in roadmap
    assert "API-first broker review" not in roadmap
    assert "Overview, Monthly Update, Planning, and the main compact-screen flows have had substantial answer-first cleanup" in roadmap
    assert "## Phase 5 — keep the safe evaluation path clear" in roadmap
    assert "The read-only demo path and sample data now exist, so the remaining work is to keep the evaluation story honest and easy to follow." in roadmap
    assert "### Options to explore\n- demo mode" not in roadmap
    assert "- decision on demo approach" not in roadmap
    assert "Cash-accessible, invested-accessible, restricted, and locked-for-later money" in roadmap_execution
    assert "trust surfaces such as Diagnostics, backup/restore boundaries, assistant access, and safe demo guidance are now shipped" in roadmap_execution
    assert "Accessible vs locked money" not in roadmap_execution
    assert "accessible vs locked money" not in roadmap
    assert "available vs restricted/locked money" not in roadmap
    assert "understand what is accessible vs locked" not in roadmap
    assert "what is accessible vs locked?" not in roadmap_execution
    assert "Public roadmap page and a manual light/dark toggle on the public website." in changelog
    assert "Scoped assistant access in Settings with UI-managed tokens, permission labels, and recent write activity." in changelog
    assert "Settings now frames assistant tokens as Personal Pip access for users who run their own Pip setup." in changelog
    assert "Settings now frames assistant tokens as a default Pip setup." not in changelog
    assert "Refreshed the roadmap, GitHub docs, and public site so they match the current first-use flows, Monthly Update, Diagnostics, safe demo/evaluation path, and optional broker snapshot review beta." in changelog
    assert "Refreshed the roadmap, GitHub docs, and public site so they match the current first-use flows, Monthly Update, Diagnostics, safe demo/evaluation path, and optional read-only broker beta." not in changelog


def test_performance_docs_explain_imported_baseline_reconciliation():
    readme = _read_readme()
    voice_and_copy = _read_voice_and_copy()
    changelog = _read_changelog()

    assert "Performance reporting separates **Opening / Imported** starting balances from later **Contributed** cash flow and **Gain / Interest**" in readme
    assert "first tracked values do not look like investment performance or regular savings" in readme
    assert "Annualised return is shown only after 12 monthly return periods" in readme
    assert "XLSX export includes a “How to read” guide explaining the same terms" in readme
    assert "Use the same terms in app, docs, and exports: “Opening / Imported”, “Contributed”, and “Gain / Interest”." in voice_and_copy
    assert "Hide annualised return until there are 12 monthly return periods" in voice_and_copy
    assert "Performance reporting now separates Opening / Imported starting balances from later Contributed cash flow and Gain / Interest, hides annualised return until 12 monthly return periods, and includes a workbook “How to read” guide." in changelog
    assert "Contributed / Initial funding" not in readme
    assert "first tracked values look like investment performance" not in readme
    assert "Performance reporting separates opening/imported starting balances from later contributions and gain/interest" not in readme
    assert "dramatic early annualised percentages" not in readme



def test_public_site_projection_copy_uses_scenario_estimate_language():
    homepage = _read("index.html")
    about = _read("about.html")
    tour = _read("tour.html")
    concept_a = _read("concepts/concept-a/index.html")
    concept_b = _read("concepts/concept-b/index.html")
    readme = _read_readme()
    voice_and_copy = _read_voice_and_copy()
    product_truth = _read_product_truth()
    changelog = _read_changelog()

    assert "Scenario estimates use your inputs and assumptions. They are not guarantees." in homepage
    assert "Scenario estimates are based on your inputs. No promises." not in homepage
    assert "Projections are scenario estimates based on your inputs. No promises." not in homepage
    assert "Projections are illustrative and based on your inputs." not in homepage
    assert "Scenario estimates" in homepage
    assert "retirement projections" not in homepage
    assert "Built and maintained as a one-person project, with AI-assisted development, testing, and careful iteration." in about
    assert "Projections are illustrative and based on your inputs, assumptions, and scenarios." not in about
    assert "<h2 class=\"section-title\">Scenario estimates</h2>" in tour
    assert 'content="Feature-led tour of SteadyPlan. See what each area does and why it exists, with grounded notes and demo screenshots."' in tour
    assert "The scenario estimates view is built around assumptions you control. The goal is to support long-term thinking while staying clear about what is entered data and what is scenario-estimate output." in tour
    assert "Scenario estimates use your inputs and assumptions. They are not guarantees." in tour
    assert "Estimates are based on your inputs and assumptions." not in tour
    assert "what is entered data and what is forecast output" not in tour
    assert "<h3>Scenarios, not guarantees</h3>" in tour
    assert "<h3>Scenarios, not promises</h3>" not in tour
    assert "Scenario estimates are assumptions-based tools to explore trade-offs, not a guarantee of outcomes." in tour
    assert "SteadyPlan scenario estimates summary card (demo data)" in tour
    assert "<h3>Projections</h3>" not in tour
    assert 'content="Product tour of SteadyPlan’s main screens using demo data: Overview, holdings, planning, projections, and trust/data-ownership flows."' not in tour
    assert "Projections let you explore what changes if you adjust contributions, retirement timing, or assumptions." not in tour
    assert "Projections are assumptions-based scenario estimates to explore trade-offs, not a guarantee of outcomes." not in tour
    assert "The projections view is built around assumptions you control. The goal is to support long-term thinking while staying clear about what is entered data and what is forecast output." not in tour
    assert "SteadyPlan projections screen with demo data" not in tour
    assert "<strong>Scenario estimates</strong>" in concept_a
    assert "No bank linking. Scenario estimates use inputs and assumptions; they are not guarantees. Just visibility and planning." in concept_a
    assert "No bank linking. No promises. Just visibility and planning." not in concept_a
    assert "<strong>Projections</strong>" not in concept_a
    assert "No bank linking. No cloud sync. Scenario estimates use inputs and assumptions; they are not guarantees." in concept_b
    assert "Scenario estimates are assumptions-based estimates." not in concept_b
    assert "<strong>Scenario estimates</strong>" in concept_b
    assert "Projections are assumptions-based estimates." not in concept_b
    assert "<strong>Projections</strong>" not in concept_b
    assert "### Retirement scenario estimates" in readme
    assert "Year-by-year and month-by-month scenario estimates using saved balances, contribution settings, and growth assumptions." in readme
    assert "These scenario estimates are not guarantees." in readme
    assert "scenario estimates based on current balances, monthly contributions, and growth assumptions" not in readme
    assert "Export scenario estimates to Excel (.xlsx) with per-account breakdowns." in readme
    assert 'Scenario estimates show "with fees" vs "without fees"' in readme
    assert "**Scenario estimates** — retirement scenario estimates with fee impact and scenario planner" in readme
    assert 'Compare actual performance against an assumptions-based "on-plan" growth line.' in readme
    assert "├── calculations.py        # Scenario estimates, returns, goal tracking, tax year logic" in readme
    assert "│   ├── projections.py     # Scenario estimates views and account series endpoints" in readme
    assert "│   ├── export.py          # Excel export (scenario estimates, budget, performance)" in readme
    assert "![Scenario estimates](Screenshots/demo/projections_desktop.png)" in readme
    assert "### Retirement Projections" not in readme
    assert "Export projections to Excel (.xlsx) with per-account breakdowns." not in readme
    assert 'Projections show "with fees" vs "without fees"' not in readme
    assert "**Projections** — retirement projections with fee impact and scenario planner" not in readme
    assert 'Compare actual performance against a projected "on-plan" growth line.' not in readme
    assert "├── calculations.py        # Projections, returns, goal tracking, tax year logic" not in readme
    assert "│   ├── projections.py     # Retirement projection engine" not in readme
    assert "│   ├── export.py          # Excel export (projections + budget)" not in readme
    assert "![Projections](Screenshots/demo/projections_desktop.png)" not in readme
    assert "- Scenario estimate: calculated outcome based on assumptions" in voice_and_copy
    assert "### Scenario estimates" in voice_and_copy
    assert "Explain scenarios as assumption-based estimates, not guarantees." in voice_and_copy
    assert "Track progress, not guarantees." in voice_and_copy
    assert "Scenario estimate certainty and disclaimers" in voice_and_copy
    assert "- After: “Scenario estimate at retirement”" in voice_and_copy
    assert "- After: “Projected at retirement (estimate)” / “Scenario estimate at retirement”" not in voice_and_copy
    assert "you will / you’ll have (for scenario estimates)" in voice_and_copy
    assert "Explain scenarios, not promises." not in voice_and_copy
    assert "Track progress, not promises." not in voice_and_copy
    assert "### Scenario estimate certainty" in voice_and_copy
    assert "2. Scenario estimate labels and estimate disclaimers" in voice_and_copy
    assert "Overview/Review/Scenario estimates/etc." in voice_and_copy
    assert "Always use “scenario estimate” / “scenario estimates” and “based on assumptions”; avoid “projection” / “projections” in user-facing copy." in voice_and_copy
    assert "- Projected: calculated scenario outcome based on assumptions" not in voice_and_copy
    assert "### Projections" not in voice_and_copy
    assert "Projection certainty and disclaimers" not in voice_and_copy
    assert "you will / you’ll have (for projections)" not in voice_and_copy
    assert "### Projections certainty" not in voice_and_copy
    assert "2. Projections labels and estimate disclaimers" not in voice_and_copy
    assert "Overview/Review/Projections/etc." not in voice_and_copy
    assert "Always use “scenario estimate”, “projection”, “based on assumptions”." not in voice_and_copy
    assert "intimidated by financial admin, scenario estimates, and long-term planning." in product_truth
    assert "Assumptions, scenario estimates, and confirmed numbers should not blur together." in product_truth
    assert "understand cash-accessible, invested-accessible, restricted, and locked-for-later money" in product_truth
    assert "See cash-accessible, invested-accessible, restricted, and locked-for-later money" in product_truth
    assert "Users should understand what cash they can use now, what invested money is still reachable, what has penalties/restrictions, and what is for later retirement." in product_truth
    assert "intimidated by financial admin, projections, and long-term planning." not in product_truth
    assert "Assumptions, estimates, projections, and confirmed numbers should not blur together." not in product_truth
    assert "understand what is accessible now vs restricted or locked for later" not in product_truth
    assert "See accessible, restricted, and locked money" not in product_truth
    assert "See accessible vs locked money" not in product_truth
    assert "Users should understand what they can use now, what has penalties/restrictions, and what is for later retirement." not in product_truth
    assert "Scenario estimate copy replaces leftover projections wording." in changelog
    assert "Projection copy frames projections as scenario estimates." not in changelog
