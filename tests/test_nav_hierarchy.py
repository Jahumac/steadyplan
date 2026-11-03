"""The shell nav is the thing the user actually experiences.

The app grew to eight top-level destinations where two of them were *also* tabs
inside a subnav. These tests pin the hierarchy down so it cannot quietly grow a
second door back into a family it already belongs to.
"""
import re


def _desktop_nav_links(html):
    nav = re.search(r"<nav>(.*?)</nav>", html, re.S).group(1)
    return [href for href in re.findall(r'<a href="([^"]+)"', nav) if href != "/logout"]


def test_desktop_nav_is_five_destinations(auth_client):
    html = auth_client.get("/", follow_redirects=True).get_data(as_text=True)

    assert _desktop_nav_links(html) == [
        "/",
        "/accounts/",
        "/budget/",
        "/house/",
        "/settings/",
    ]


def test_allowances_is_not_a_top_level_destination(auth_client):
    """It is a Budget tab; a second top-level entry made the shell longer for nothing."""
    html = auth_client.get("/", follow_redirects=True).get_data(as_text=True)

    links = _desktop_nav_links(html)
    assert "/allowance/" not in links
    assert 'class="active">Allowances</a>' not in html


def test_allowances_page_lights_up_the_budget_family(auth_client):
    resp = auth_client.get("/allowance/", follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # the section it belongs to is highlighted in the shell...
    assert 'href="/budget/" class="active">Budget</a>' in html
    # ...and it is still reachable as a tab inside that family
    assert 'href="/allowance/" class="subnav-active">Allowances</a>' in html


def test_house_page_links_straight_to_the_lisa_top_up_log(app, client, make_user):
    """The deposit and the LISA log are the same job — the log must be one tap away."""
    from app.models import create_goal

    uid, username, password = make_user(username="house-lisa-link", password="password123")
    with app.app_context():
        create_goal(
            {
                "name": "House",
                "target_value": 33000.0,
                "goal_type": "Tagged Goal",
                "selected_tags": "House",
                "notes": "",
                "target_date": "2029-05-01",
            },
            uid,
        )
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    resp = client.get("/house/")
    assert resp.status_code == 200
    assert b'href="/allowance/#isa-log-panel">Log a LISA top-up</a>' in resp.data
