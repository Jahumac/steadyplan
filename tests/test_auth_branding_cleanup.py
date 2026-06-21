from pathlib import Path

import app.routes.auth as auth_routes
from tests.path_helpers import STATIC_ROOT


def test_login_page_uses_brand_logo_without_auth_mascot_icon(client, make_user):
    make_user(username="auth-cleanup-user", password="password123")

    response = client.get("/login", follow_redirects=True)

    assert response.status_code == 200
    html = response.data.decode()
    assert "Sign in" in html
    assert "Private finance planning," in html
    assert "on your own server." in html
    assert "Slow and steady" not in html
    assert "wins the race." not in html
    assert "Estimate retirement" in html
    assert "run retirement projections" not in html
    assert "Estimate retirement by account" in html
    assert "Retirement projections by account" not in html
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
    assert "Start privately," in html
    assert "on your own server." in html
    assert "Estimate retirement by account" in html
    assert "Retirement projections by account" not in html
    assert "Slow and steady," not in html
    assert 'brand/steadyplan-mark.png' in html
    assert 'class="auth-brand-mark auth-brand-mark--float"' in html
    assert 'auth-brand-icon' not in html
    assert 'icon-192.png' not in html
    assert 'turtle-wave' not in html


def test_auth_css_no_longer_contains_auth_brand_icon_or_auth_turtle_classes():
    css = STATIC_ROOT.joinpath("css/styles.css").read_text()

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
    assert STATIC_ROOT.joinpath("brand/steadyplan-mark.png").exists()
    assert STATIC_ROOT.joinpath("brand/steadyplan-app-icon-1024.png").exists()
    assert STATIC_ROOT.joinpath("icons/icon-180.png").exists()
    assert STATIC_ROOT.joinpath("icons/icon-192.png").exists()
    assert STATIC_ROOT.joinpath("icons/icon-512.png").exists()
    assert STATIC_ROOT.joinpath("icons/favicon-32.png").exists()
    assert STATIC_ROOT.joinpath("icons/favicon-16.png").exists()
