from pathlib import Path

import app.routes.auth as auth_routes


def test_login_page_uses_brand_logo_without_auth_mascot_icon(client, make_user):
    make_user(username="auth-cleanup-user", password="password123")

    response = client.get("/login", follow_redirects=True)

    assert response.status_code == 200
    html = response.data.decode()
    assert "Sign in" in html
    assert 'brand/steadyplan-mark.png' in html
    assert 'class="auth-brand-mark auth-brand-mark--float"' in html
    assert 'auth-brand-icon' not in html
    assert 'icon-192.png' not in html
    assert 'turtle-bob' not in html


def test_setup_page_uses_brand_logo_without_auth_mascot_icon(client, monkeypatch):
    monkeypatch.setattr(auth_routes, "count_users", lambda: 0)

    response = client.get("/setup", follow_redirects=True)

    assert response.status_code == 200
    html = response.data.decode()
    assert "Create your account" in html
    assert 'brand/steadyplan-mark.png' in html
    assert 'class="auth-brand-mark auth-brand-mark--float"' in html
    assert 'auth-brand-icon' not in html
    assert 'icon-192.png' not in html
    assert 'turtle-wave' not in html


def test_auth_css_no_longer_contains_auth_brand_icon_or_auth_turtle_classes():
    css = Path("/opt/data/steadyplan/app/static/css/styles.css").read_text()

    assert ".auth-brand-mark {" in css
    assert ".auth-brand-mark--float {" in css
    assert "@keyframes brand-mark-float" in css
    assert "width: 84px;" in css
    assert "height: 84px;" in css
    assert "background: radial-gradient(circle at 50% 35%" in css
    assert "filter: drop-shadow(0 10px 26px rgba(15, 23, 42, 0.32))" in css
    assert ".auth-brand-icon {" not in css
    assert ".turtle-bob {" not in css
    assert ".turtle-wave {" not in css


def test_brand_png_assets_exist_for_shell_auth_and_pwa():
    assert Path("/opt/data/steadyplan/app/static/brand/steadyplan-mark.png").exists()
    assert Path("/opt/data/steadyplan/app/static/brand/steadyplan-app-icon-1024.png").exists()
    assert Path("/opt/data/steadyplan/app/static/icons/icon-180.png").exists()
    assert Path("/opt/data/steadyplan/app/static/icons/icon-192.png").exists()
    assert Path("/opt/data/steadyplan/app/static/icons/icon-512.png").exists()
    assert Path("/opt/data/steadyplan/app/static/icons/favicon-32.png").exists()
    assert Path("/opt/data/steadyplan/app/static/icons/favicon-16.png").exists()
