from pathlib import Path


SITE_ROOT = Path("/opt/data/steadyplan/site")
README_PATH = Path("/opt/data/steadyplan/README.md")
VOICE_AND_COPY_PATH = Path("/opt/data/steadyplan/docs/VOICE_AND_COPY.md")
PRODUCT_TRUTH_PATH = Path("/opt/data/steadyplan/docs/PRODUCT_TRUTH.md")
CHANGELOG_PATH = Path("/opt/data/steadyplan/CHANGELOG.md")


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


def test_homepage_trust_card_mentions_restore_preview_and_safety_backup():
    html = _read("index.html")

    assert "SteadyPlan uses a local SQLite database and keeps backup and restore guidance close to the product so trust is explicit." in html
    assert "See how JSON exports, whole-instance backups, and restore checks fit together" not in html


def test_tour_trust_copy_matches_restore_safety_story():
    html = _read("tour.html")

    assert "SteadyPlan stores your data locally in a SQLite database on your own server/NAS/desktop. There is no hosted account and no public signup." in html
    assert "Optional external price lookups can contact providers for ticker data. Everything else stays local unless you choose otherwise." in html
    assert "<h2 class=\"section-title\">Data ownership</h2>" in html


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
    assert "- JSON export and restore flow (done)." in readme
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

    assert "Projections are scenario estimates based on your inputs. No promises." in homepage
    assert "Projections are illustrative and based on your inputs." not in homepage
    assert "Scenario estimates" in homepage
    assert "retirement projections" not in homepage
    assert "Built and maintained as a one-person project, with AI-assisted development, testing, and careful iteration." in about
    assert "Projections are illustrative and based on your inputs, assumptions, and scenarios." not in about
    assert "<h2 class=\"section-title\">Scenario estimates</h2>" in tour
    assert 'content="Feature-led tour of SteadyPlan. See what each area does and why it exists, with grounded notes and demo screenshots."' in tour
    assert "The projections view is built around assumptions you control. The goal is to support long-term thinking while staying clear about what is entered data and what is forecast output." in tour
    assert "SteadyPlan scenario estimates summary card (demo data)" in tour
    assert "<h3>Projections</h3>" not in tour
    assert 'content="Product tour of SteadyPlan’s main screens using demo data: Overview, holdings, planning, projections, and trust/data-ownership flows."' not in tour
    assert "Projections let you explore what changes if you adjust contributions, retirement timing, or assumptions." not in tour
    assert "SteadyPlan projections screen with demo data" not in tour
    assert "<strong>Scenario estimates</strong>" in concept_a
    assert "<strong>Projections</strong>" not in concept_a
    assert "Scenario estimates are assumptions-based estimates." in concept_b
    assert "<strong>Scenario estimates</strong>" in concept_b
    assert "Projections are assumptions-based estimates." not in concept_b
    assert "<strong>Projections</strong>" not in concept_b
    assert "### Retirement scenario estimates" in readme
    assert "Year-by-year and month-by-month scenario estimates based on current balances, monthly contributions, and growth assumptions." in readme
    assert "Export scenario estimates to Excel (.xlsx) with per-account breakdowns." in readme
    assert 'Scenario estimates show "with fees" vs "without fees"' in readme
    assert "**Scenario estimates** — retirement scenario estimates with fee impact and scenario planner" in readme
    assert 'Compare actual performance against an assumptions-based "on-plan" growth line.' in readme
    assert "├── calculations.py        # Scenario estimates, returns, goal tracking, tax year logic" in readme
    assert "│   ├── projections.py     # Retirement scenario estimate engine" in readme
    assert "│   ├── export.py          # Excel export (scenario estimates + budget)" in readme
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
    assert "Scenario estimate certainty and disclaimers" in voice_and_copy
    assert "you will / you’ll have (for scenario estimates)" in voice_and_copy
    assert "### Scenario estimate certainty" in voice_and_copy
    assert "2. Scenario estimate labels and estimate disclaimers" in voice_and_copy
    assert "Overview/Review/Scenario estimates/etc." in voice_and_copy
    assert "- Projected: calculated scenario outcome based on assumptions" not in voice_and_copy
    assert "### Projections" not in voice_and_copy
    assert "Projection certainty and disclaimers" not in voice_and_copy
    assert "you will / you’ll have (for projections)" not in voice_and_copy
    assert "### Projections certainty" not in voice_and_copy
    assert "2. Projections labels and estimate disclaimers" not in voice_and_copy
    assert "Overview/Review/Projections/etc." not in voice_and_copy
    assert "intimidated by financial admin, scenario estimates, and long-term planning." in product_truth
    assert "Assumptions, scenario estimates, and confirmed numbers should not blur together." in product_truth
    assert "intimidated by financial admin, projections, and long-term planning." not in product_truth
    assert "Assumptions, estimates, projections, and confirmed numbers should not blur together." not in product_truth
    assert "Scenario estimate copy replaces leftover projections wording." in changelog
    assert "Projection copy frames projections as scenario estimates." not in changelog
