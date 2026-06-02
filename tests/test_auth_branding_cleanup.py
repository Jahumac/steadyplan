from pathlib import Path

import app.routes.auth as auth_routes


def test_login_page_uses_brand_logo_without_auth_mascot_icon(client, make_user):
    make_user(username="auth-cleanup-user", password="password123")

    response = client.get("/login", follow_redirects=True)

    assert response.status_code == 200
    html = response.data.decode()
    assert "Sign in" in html
    assert 'brand/steadyplan-badge.svg' in html
    assert 'class="auth-brand-mark"' in html
    assert 'auth-brand-icon' not in html
    assert 'icon-192.png' not in html
    assert 'turtle-bob' not in html


def test_setup_page_uses_brand_logo_without_auth_mascot_icon(client, monkeypatch):
    monkeypatch.setattr(auth_routes, "count_users", lambda: 0)

    response = client.get("/setup", follow_redirects=True)

    assert response.status_code == 200
    html = response.data.decode()
    assert "Create your account" in html
    assert 'brand/steadyplan-badge.svg' in html
    assert 'class="auth-brand-mark"' in html
    assert 'auth-brand-icon' not in html
    assert 'icon-192.png' not in html
    assert 'turtle-wave' not in html


def test_auth_css_no_longer_contains_auth_brand_icon_or_auth_turtle_classes():
    css = Path("/opt/data/steadyplan/app/static/css/styles.css").read_text()

    assert ".auth-brand-mark {" in css
    assert ".auth-brand-icon {" not in css
    assert ".turtle-bob {" not in css
    assert ".turtle-wave {" not in css


def test_brand_svg_assets_exist_for_shell_auth_and_pwa():
    assert Path("/opt/data/steadyplan/app/static/brand/steadyplan-mark.svg").exists()
    assert Path("/opt/data/steadyplan/app/static/brand/steadyplan-badge.svg").exists()
    assert Path("/opt/data/steadyplan/app/static/brand/steadyplan-pwa-source.svg").exists()
