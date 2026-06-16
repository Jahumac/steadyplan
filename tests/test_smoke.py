"""Smoke tests — one GET per blueprint, plus the core write/auth paths.

These don't test business logic; they catch the class of bug where a route
crashes because of a template rename, missing import, or broken query.
"""


def test_setup_required_without_users(client):
    # First visit with no users should redirect to /setup
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert "/setup" in resp.headers.get("Location", "")


def test_setup_creates_admin_and_logs_in(client):
    resp = client.post("/setup", data={
        "username": "admin",
        "password": "testpass123",
        "confirm_password": "testpass123",
    }, follow_redirects=False)
    assert resp.status_code in (301, 302)
    # After setup, user should be logged in and see overview
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 200


def test_auth_pages_use_lifetime_isa_marketing_copy(client, app, make_user):
    setup_resp = client.get("/setup")
    assert setup_resp.status_code == 200
    setup_html = setup_resp.get_data(as_text=True)
    assert "ISA, Lifetime ISA &amp; pension allowance tracking" in setup_html
    assert "ISA, LISA &amp; pension allowance tracking" not in setup_html

    make_user(username="auth-copy-user", password="password123")
    login_resp = client.get("/login")
    assert login_resp.status_code == 200
    login_html = login_resp.get_data(as_text=True)
    assert "ISA, Lifetime ISA &amp; pension allowance tracking" in login_html
    assert "ISA, LISA &amp; pension allowance tracking" not in login_html


def test_login_rejects_bad_password(app, client, make_user):
    make_user(username="bob", password="rightpass123")
    resp = client.post("/login", data={"username": "bob", "password": "wrong"},
                       follow_redirects=False)
    # Stays on login page (renders 200) rather than redirecting to overview
    assert resp.status_code == 200
    assert b"Invalid" in resp.data or b"invalid" in resp.data


def test_login_demo_callout_explains_read_only_boundaries(app, client, make_user):
    app.config.update(DEMO_PUBLIC_LOGIN_ENABLED=True, DEMO_READ_ONLY_USERNAME="demo")
    make_user(username="demo", password="password123")

    resp = client.get("/login")

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Read-only demo" in html
    assert "Take a quick look with sample data" in html
    assert "demo account with demo data only" in html
    assert "No password is needed here, and writes are blocked." in html
    assert "For hands-on evaluation you trust, use your own install on LAN or VPN." in html
    assert "Open read-only demo" in html
    assert "Try demo (read-only)" not in html
    assert "Take a quick look without risking real data" not in html


def test_demo_overview_orients_sample_data_without_hiding_read_only_boundary(app, client, make_user):
    app.config.update(DEMO_PUBLIC_LOGIN_ENABLED=True, DEMO_READ_ONLY_USERNAME="demo")
    make_user(username="demo", password="password123")

    login_resp = client.get("/demo", follow_redirects=False)
    assert login_resp.status_code in (301, 302)

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "You are viewing demo data" in html
    assert "This is sample data only. Writes are blocked, so you can explore without changing anything." in html
    assert "Start with Overview, then Planning, Monthly Update, and Settings → Safety and recovery." in html
    assert "Start with Overview, then Planning, Monthly Update, and Settings → Data ownership." not in html
    assert 'href="/planning/"' in html
    assert 'href="/monthly-review/"' in html
    assert 'href="/settings/"' in html
    assert "Demo mode lets you change sample data" not in html


def test_normal_overview_does_not_show_demo_orientation(app, client, make_user):
    _, username, password = make_user(username="regular-overview", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "You are viewing demo data" not in html
    assert "This is sample data only. Writes are blocked" not in html


def test_demo_monthly_review_get_does_not_create_review_rows(app, client, make_user):
    app.config.update(DEMO_PUBLIC_LOGIN_ENABLED=True, DEMO_READ_ONLY_USERNAME="demo")
    uid, _, _ = make_user(username="demo", password="password123")

    login_resp = client.get("/demo", follow_redirects=False)
    assert login_resp.status_code in (301, 302)

    month_key = "2026-05"
    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            before = conn.execute(
                "SELECT COUNT(*) AS c FROM monthly_reviews WHERE user_id = ? AND month_key = ?",
                (uid, month_key),
            ).fetchone()["c"]

    resp = client.get(f"/monthly-review/?month={month_key}")
    assert resp.status_code == 200

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            after = conn.execute(
                "SELECT COUNT(*) AS c FROM monthly_reviews WHERE user_id = ? AND month_key = ?",
                (uid, month_key),
            ).fetchone()["c"]

    assert int(before) == 0
    assert int(after) == 0


def test_demo_overview_get_does_not_create_due_monthly_review(app, client, make_user):
    app.config.update(DEMO_PUBLIC_LOGIN_ENABLED=True, DEMO_READ_ONLY_USERNAME="demo")
    uid, _, _ = make_user(username="demo", password="password123")

    with app.app_context():
        from datetime import date
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute("UPDATE assumptions SET salary_day = 1 WHERE user_id = ?", (uid,))
            conn.commit()
        month_key = date.today().strftime("%Y-%m")
        with get_connection() as conn:
            before = conn.execute(
                "SELECT COUNT(*) AS c FROM monthly_reviews WHERE user_id = ? AND month_key = ?",
                (uid, month_key),
            ).fetchone()["c"]

    login_resp = client.get("/demo", follow_redirects=False)
    assert login_resp.status_code in (301, 302)

    resp = client.get("/")
    assert resp.status_code == 200

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            after = conn.execute(
                "SELECT COUNT(*) AS c FROM monthly_reviews WHERE user_id = ? AND month_key = ?",
                (uid, month_key),
            ).fetchone()["c"]

    assert int(before) == 0
    assert int(after) == 0


def test_demo_read_only_blocks_non_post_mutations(app, client, make_user):
    app.config.update(DEMO_PUBLIC_LOGIN_ENABLED=True, DEMO_READ_ONLY_USERNAME="demo")
    make_user(username="demo", password="password123")

    login_resp = client.get("/demo", follow_redirects=False)
    assert login_resp.status_code in (301, 302)

    resp = client.open(
        "/api/v1/accounts/1/balance",
        method="PATCH",
        headers={"Accept": "application/json"},
    )

    assert resp.status_code == 403
    assert resp.get_json() == {"error": "Demo account is read-only"}


def test_unauthenticated_redirects_to_login(app, client, make_user):
    # Need at least one user so the app doesn't redirect to /setup
    make_user()
    resp = client.get("/accounts/", follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert "/login" in resp.headers.get("Location", "")


def test_api_ping(client):
    resp = client.get("/api/ping")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}


# ── One GET per blueprint's landing page (authenticated) ──────────────────────

import pytest

# Blueprints that expose a landing page. Holdings has no index route —
# it's detail-only (/holdings/<id>) and an API. That's worth knowing.
BLUEPRINT_PAGES = [
    "/",
    "/accounts/",
    "/goals/",
    "/projections/",
    "/settings/",
    "/monthly-review/",
    "/budget/",
    "/budget/contribution-calendar",
    "/performance/",
    "/allowance/",
]


@pytest.mark.parametrize("path", BLUEPRINT_PAGES)
def test_authenticated_page_loads(auth_client, path):
    resp = auth_client.get(path, follow_redirects=True)
    # Accept 200 (renders) or 404 only if route is genuinely optional.
    # The whole point of a smoke test: a crash (500) fails loudly.
    assert resp.status_code in (200, 302), (
        f"GET {path} returned {resp.status_code}"
    )
