from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_ROOT = REPO_ROOT / "site"
APP_ROOT = REPO_ROOT / "app"
STATIC_ROOT = APP_ROOT / "static"
TEMPLATES_ROOT = APP_ROOT / "templates"
DOCS_ROOT = REPO_ROOT / "docs"
