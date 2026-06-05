from pathlib import Path


SITE_ROOT = Path("/opt/data/steadyplan/site")
README_PATH = Path("/opt/data/steadyplan/README.md")


def _read(relative_path: str) -> str:
    return (SITE_ROOT / relative_path).read_text()


def _read_readme() -> str:
    return README_PATH.read_text()


def test_homepage_trust_card_mentions_restore_preview_and_safety_backup():
    html = _read("index.html")

    assert "per-user JSON exports, whole-instance SQLite backups, restore preview checks, and automatic pre-restore safety backups" in html
    assert "See how JSON exports, whole-instance backups, and restore checks fit together" not in html


def test_tour_trust_copy_matches_restore_safety_story():
    html = _read("tour.html")

    assert "Backups, validated restore steps, optional lookups, and privacy." in html
    assert "A restore is previewed before anything is overwritten, and the app creates a fresh whole-instance SQLite backup before a confirmed overwrite can proceed." in html
    assert "restore preview checks with an automatic pre-restore safety backup" in html
    assert "validated restore flow and safety-backup story" in html


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


def test_docs_and_install_pages_explain_safest_evaluation_path():
    docs_index = _read("docs/index.html")
    install = _read("docs/install.html")
    reverse_proxy = _read("docs/reverse-proxy.html")

    assert "Safest way to evaluate" in docs_index
    assert "Start with the <a href=\"../tour.html\">product tour</a> and docs." in docs_index
    assert "A public read-only demo can be useful, but it should be treated as an explicit opt-in host choice rather than the default way to try SteadyPlan." in docs_index
    assert "Evaluate safely first" in install
    assert "Best order: screenshots/tour first, then your own local install on LAN or VPN if you want hands-on evaluation." in install
    assert "Public demo access can be useful, but only as a deliberate read-only setup by the host" in install
    assert "FORWARDED_ALLOW_IPS" in reverse_proxy
    assert "advanced choice rather than the default" in reverse_proxy



def test_public_site_projection_copy_uses_scenario_estimate_language():
    homepage = _read("index.html")
    about = _read("about.html")
    tour = _read("tour.html")
    concept_a = _read("concepts/concept-a/index.html")
    concept_b = _read("concepts/concept-b/index.html")
    readme = _read_readme()

    assert "Scenario estimates are illustrative and based on your inputs." in homepage
    assert "Projections are illustrative and based on your inputs." not in homepage
    assert "retirement scenario estimates" in homepage
    assert "retirement projections" not in homepage
    assert "Scenario estimates are illustrative and based on your inputs, assumptions, and scenarios." in about
    assert "Projections are illustrative and based on your inputs, assumptions, and scenarios." not in about
    assert "<h3>Scenario estimates</h3>" in tour
    assert '<p class="kicker">Scenario estimates</p>' in tour
    assert "Scenario estimates let you explore what changes if you adjust contributions, retirement timing, or assumptions." in tour
    assert "SteadyPlan scenario estimates screen with demo data" in tour
    assert "<h3>Projections</h3>" not in tour
    assert '<p class="kicker">Projections</p>' not in tour
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
    assert "### Retirement Projections" not in readme
    assert "Export projections to Excel (.xlsx) with per-account breakdowns." not in readme
    assert 'Projections show "with fees" vs "without fees"' not in readme
    assert "**Projections** — retirement projections with fee impact and scenario planner" not in readme
