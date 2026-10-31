"""Content Security Policy.

The app's CSP had no test, which is how an unreachable 'unsafe-inline' +
'unsafe-eval' relaxation for "/sandbox.html" survived in `app/__init__.py` — the
React sandbox demo is served by the public site, not by Flask. These tests pin the
strict policy and stop a relaxed branch coming back.
"""
import pytest


def _csp(resp):
    return resp.headers.get("Content-Security-Policy", "")


def _script_src(csp):
    for directive in csp.split(";"):
        directive = directive.strip()
        if directive.startswith("script-src"):
            return directive
    return ""


def test_login_page_sends_a_csp(app, client):
    csp = _csp(client.get("/login"))
    assert csp, "no Content-Security-Policy header"
    assert "default-src 'self'" in csp


def test_script_src_never_allows_unsafe_eval(app, client):
    """'unsafe-eval' must never be granted to app pages."""
    csp = _csp(client.get("/login"))
    assert "unsafe-eval" not in _script_src(csp)


def test_script_src_never_allows_unsafe_inline(app, client):
    """All app JS lives in external files precisely so this can stay locked down."""
    csp = _csp(client.get("/login"))
    script_src = _script_src(csp)
    assert "unsafe-inline" not in script_src
    assert "'self'" in script_src


@pytest.mark.parametrize("path", ["/sandbox.html", "/sandbox", "/site/sandbox.html"])
def test_sandbox_paths_get_no_relaxed_policy(app, client, path):
    """The React sandbox is served by the public site, not Flask.

    Any request for it here must not be handed a weakened CSP.
    """
    resp = client.get(path)
    assert "unsafe-eval" not in _script_src(_csp(resp))


def test_authenticated_pages_keep_the_strict_policy(app, client, make_user):
    uid, username, password = make_user(username="csp-check", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    for path in ("/", "/accounts/", "/settings/"):
        csp = _csp(client.get(path))
        assert csp, f"no CSP on {path}"
        script_src = _script_src(csp)
        assert "unsafe-eval" not in script_src, path
        assert "unsafe-inline" not in script_src, path
