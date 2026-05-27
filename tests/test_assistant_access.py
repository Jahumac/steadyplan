import re


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _extract_assistant_token(html):
    match = re.search(r'data-assistant-token-value="([^"]+)"', html)
    assert match, "Expected assistant token value in rendered HTML"
    return match.group(1)



def test_assistant_token_is_limited_to_assistant_endpoints(app, client, make_user):
    uid, _, _ = make_user(username="assistant-scope-user")

    with app.app_context():
        from app.models import create_api_token

        token = create_api_token(
            uid,
            label="Pip",
            token_kind="assistant",
            scopes=["assistant:read"],
        )

    allowed = client.get(
        "/api/v1/assistant/portfolio-overview",
        headers=_bearer(token),
    )
    assert allowed.status_code == 200

    denied = client.get(
        "/api/v1/accounts",
        headers=_bearer(token),
    )
    assert denied.status_code == 403
    assert denied.get_json()["error"] == "insufficient_scope"



def test_assistant_token_without_read_scope_is_rejected(app, client, make_user):
    uid, _, _ = make_user(username="assistant-no-read")

    with app.app_context():
        from app.models import create_api_token

        token = create_api_token(
            uid,
            label="Pip write-only",
            token_kind="assistant",
            scopes=["assistant:budget_write"],
        )

    resp = client.get(
        "/api/v1/assistant/month-summary/2026-05",
        headers=_bearer(token),
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "insufficient_scope"



def test_settings_can_create_regenerate_and_revoke_assistant_token(app, client, make_user):
    uid, username, password = make_user(username="assistant-settings-user")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    create_resp = client.post(
        "/settings/assistant-access/create",
        data={
            "label": "Pip",
            "scopes": ["assistant:read", "assistant:budget_write"],
        },
        follow_redirects=True,
    )
    assert create_resp.status_code == 200
    create_html = create_resp.get_data(as_text=True)
    assert "Assistant access" in create_html
    assert "Assistant token created" in create_html
    first_token = _extract_assistant_token(create_html)

    with app.app_context():
        from app.models import fetch_api_tokens

        tokens = fetch_api_tokens(uid, token_kind="assistant")
        assert len(tokens) == 1
        first_id = tokens[0]["id"]
        assert tokens[0]["token_kind"] == "assistant"
        assert tokens[0]["scopes"] == ["assistant:read", "assistant:budget_write"]

    first_token_resp = client.get(
        "/api/v1/assistant/portfolio-overview",
        headers=_bearer(first_token),
    )
    assert first_token_resp.status_code == 200

    second_view = client.get("/settings/")
    assert "data-assistant-token-value=" not in second_view.get_data(as_text=True)

    regen_resp = client.post(
        f"/settings/assistant-access/{first_id}/regenerate",
        follow_redirects=True,
    )
    assert regen_resp.status_code == 200
    regen_html = regen_resp.get_data(as_text=True)
    assert "Assistant token regenerated" in regen_html
    second_token = _extract_assistant_token(regen_html)
    assert second_token != first_token

    old_token_resp = client.get(
        "/api/v1/assistant/portfolio-overview",
        headers=_bearer(first_token),
    )
    assert old_token_resp.status_code == 401

    new_token_resp = client.get(
        "/api/v1/assistant/portfolio-overview",
        headers=_bearer(second_token),
    )
    assert new_token_resp.status_code == 200

    with app.app_context():
        from app.models import fetch_api_tokens

        tokens = fetch_api_tokens(uid, token_kind="assistant")
        assert len(tokens) == 1
        second_id = tokens[0]["id"]

    revoke_resp = client.post(
        f"/settings/assistant-access/{second_id}/revoke",
        follow_redirects=True,
    )
    assert revoke_resp.status_code == 200
    revoke_html = revoke_resp.get_data(as_text=True)
    assert "Assistant token revoked" in revoke_html

    revoked_token_resp = client.get(
        "/api/v1/assistant/portfolio-overview",
        headers=_bearer(second_token),
    )
    assert revoked_token_resp.status_code == 401

    with app.app_context():
        from app.models import fetch_api_tokens

        assert fetch_api_tokens(uid, token_kind="assistant") == []
