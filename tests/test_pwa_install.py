"""PWA installability: manifest correctness and the in-app install affordance.

The app is installable as a standalone Android/desktop app. These tests guard the
pieces that silently break installability: a manifest that parses but points at
missing icons, shortcuts that 404, and a button that never gets revealed.
"""
import json
from pathlib import Path


def _manifest(app):
    path = Path(app.static_folder) / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifest_is_valid_json_with_required_pwa_fields(app):
    m = _manifest(app)

    # Minimum Chrome needs to offer installation.
    for key in ("name", "short_name", "start_url", "display", "icons"):
        assert key in m, f"manifest missing {key}"
    assert m["display"] in {"standalone", "fullscreen", "minimal-ui"}
    assert len(m["short_name"]) <= 12, "short_name gets truncated on home screens"
    assert m["scope"] == "/"


def test_manifest_icons_exist_on_disk_and_include_192_and_512(app):
    m = _manifest(app)
    static_root = Path(app.static_folder)

    sizes = set()
    for icon in m["icons"]:
        assert icon["type"] == "image/png"
        rel = icon["src"].lstrip("/")
        rel = rel[len("static/"):] if rel.startswith("static/") else rel
        assert (static_root / rel).is_file(), f"manifest icon missing on disk: {icon['src']}"
        sizes.add(icon["sizes"])

    # Chrome requires at least a 192 and a 512 for installability.
    assert {"192x192", "512x512"} <= sizes


def test_manifest_shortcuts_point_at_real_pages(app, client, make_user):
    m = _manifest(app)
    uid, username, password = make_user(username="pwa-shortcuts", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    shortcuts = m.get("shortcuts", [])
    assert shortcuts, "expected at least one shortcut"

    for shortcut in shortcuts:
        resp = client.get(shortcut["url"], follow_redirects=False)
        assert resp.status_code in (200, 302), (
            f"shortcut {shortcut['name']} -> {shortcut['url']} returned {resp.status_code}"
        )


def test_install_button_is_rendered_hidden_for_signed_in_users(app, client, make_user):
    uid, username, password = make_user(username="pwa-button", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    html = client.get("/").get_data(as_text=True)

    assert 'id="pwa-install-btn"' in html
    # Must start hidden: beforeinstallprompt decides whether to reveal it.
    assert "pwa-install" in html
    assert "hidden" in html


def test_install_button_is_inside_the_authenticated_guard(app):
    """The button must not render for anonymous visitors.

    Note: auth/login.html is a standalone template (it does not extend
    base.html), so fetching /login proves nothing here — assert the guard
    in the base template itself.
    """
    template = (
        Path(app.root_path) / "templates" / "base.html"
    ).read_text(encoding="utf-8")

    start = template.index("{% if current_user.is_authenticated %}")
    end = template.index("{% endif %}", start)
    guarded_region = template[start:end]

    assert 'id="pwa-install-btn"' in guarded_region


def test_install_prompt_wiring_exists_in_scripts(app):
    """The button is inert without the beforeinstallprompt handler in app.js."""
    js = (Path(app.static_folder) / "js" / "app.js").read_text(encoding="utf-8")
    assert "beforeinstallprompt" in js
    assert "appinstalled" in js
    assert "pwa-install-btn" in js
    # Prompt replay on click, and suppression once installed/standalone.
    assert "prompt()" in js
    assert "display-mode: standalone" in js
