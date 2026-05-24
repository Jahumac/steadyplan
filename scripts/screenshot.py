#!/usr/bin/env python
"""Take screenshots of SteadyPlan pages at desktop and mobile widths.

Runs a headless Chromium via Playwright against a local SteadyPlan instance,
logs in, and dumps PNGs of every page listed in DEFAULT_PAGES at two
viewports (desktop + mobile). Useful for visual-regression spot-checks
after UI changes — run before and after a change and diff the folders.

Setup (one-time):
    .venv/bin/pip install playwright
    .venv/bin/playwright install chromium

Usage:
    # Flask must be running (python run.py on port 8000 by default)
    .venv/bin/python scripts/screenshot.py --user alice --password testpass123

Output: tests/screenshots/<timestamp>/<page>_<viewport>.png
"""
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.stderr.write(
        "playwright is not installed. Install with:\n"
        "    .venv/bin/pip install playwright\n"
        "    .venv/bin/playwright install chromium\n"
    )
    sys.exit(1)


DEFAULT_PAGES = [
    ("/", "overview"),
    ("/accounts/", "accounts"),
    ("/holdings/", "holdings"),
    ("/goals/", "goals"),
    ("/performance", "performance"),
    ("/projections", "projections"),
    ("/budget/", "budget"),
    ("/settings/", "settings"),
]

VIEWPORTS = [
    ("desktop", 1280, 800),
    ("mobile", 390, 844),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=os.getenv("SHELLY_URL", "http://localhost:8000"))
    parser.add_argument("--user", default=os.getenv("SHELLY_USER"))
    parser.add_argument("--password", default=os.getenv("SHELLY_PASSWORD"))
    parser.add_argument("--out", default=None,
                        help="Output directory (default: tests/screenshots/<timestamp>)")
    parser.add_argument("--page", action="append", default=None,
                        help="Page path to screenshot (can repeat; overrides defaults)")
    parser.add_argument("--full-page", action="store_true",
                        help="Capture full scrollable page instead of viewport")
    args = parser.parse_args()

    if not args.user or not args.password:
        sys.stderr.write("Provide --user and --password (or SHELLY_USER / SHELLY_PASSWORD env vars).\n")
        sys.exit(2)

    if args.page:
        pages = [(p, p.strip("/").replace("/", "_") or "root") for p in args.page]
    else:
        pages = DEFAULT_PAGES

    out = Path(args.out) if args.out else Path("tests/screenshots") / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    print(f"Screenshots → {out}")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for vp_name, width, height in VIEWPORTS:
                ctx = browser.new_context(viewport={"width": width, "height": height})
                page = ctx.new_page()

                # Log in once per viewport.
                page.goto(f"{args.url}/login")
                page.fill("input[name=username]", args.user)
                page.fill("input[name=password]", args.password)
                page.click("button[type=submit]")
                try:
                    page.wait_for_url(lambda u: "/login" not in u, timeout=5000)
                except Exception:
                    sys.stderr.write("Login did not redirect away from /login — check credentials.\n")
                    sys.exit(3)

                for path, label in pages:
                    print(f"  [{vp_name}] {path}")
                    page.goto(f"{args.url}{path}")
                    page.wait_for_load_state("networkidle")
                    page.screenshot(path=str(out / f"{label}_{vp_name}.png"),
                                    full_page=args.full_page)

                ctx.close()
        finally:
            browser.close()

    print(f"\n{len(pages) * len(VIEWPORTS)} screenshots saved.")


if __name__ == "__main__":
    main()
