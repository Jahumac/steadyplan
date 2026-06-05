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



def test_assistant_budget_write_scope_allows_narrow_budget_write(app, client, make_user):
    uid, _, _ = make_user(username="assistant-budget-write")

    with app.app_context():
        from app.models import create_api_token, create_budget_item, fetch_budget_sections

        fetch_budget_sections(uid)
        item_id = create_budget_item(
            {
                "name": "Phone sinking fund",
                "section": "discretionary",
                "default_amount": 50,
                "notes": "",
                "sort_order": 0,
            },
            uid,
        )
        token = create_api_token(
            uid,
            label="Pip budget write",
            token_kind="assistant",
            scopes=["assistant:budget_write"],
        )

    resp = client.post(
        f"/api/v1/assistant/budget-items/{item_id}/month-entry",
        headers=_bearer(token),
        json={"month": "2026-05", "amount": 799},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["amount"] == 799



def test_assistant_read_only_token_cannot_write_budget_entry(app, client, make_user):
    uid, _, _ = make_user(username="assistant-budget-readonly")

    with app.app_context():
        from app.models import create_api_token, create_budget_item, fetch_budget_sections

        fetch_budget_sections(uid)
        item_id = create_budget_item(
            {
                "name": "Phone sinking fund",
                "section": "discretionary",
                "default_amount": 50,
                "notes": "",
                "sort_order": 0,
            },
            uid,
        )
        token = create_api_token(
            uid,
            label="Pip read only",
            token_kind="assistant",
            scopes=["assistant:read"],
        )

    resp = client.post(
        f"/api/v1/assistant/budget-items/{item_id}/month-entry",
        headers=_bearer(token),
        json={"month": "2026-05", "amount": 799},
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "insufficient_scope"



def test_settings_can_create_regenerate_and_revoke_assistant_token(app, client, make_user):
    uid, username, password = make_user(username="assistant-settings-user")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    settings_resp = client.get("/settings/")
    settings_html = settings_resp.get_data(as_text=True)
    assert settings_resp.status_code == 200
    assert "Give Pip scoped access to SteadyPlan" in settings_html
    assert "This creates a dedicated assistant token for SteadyPlan. Unlike a general API token, it only works with assistant endpoints and you can revoke or regenerate it here." in settings_html
    assert "A local label to help you recognise this token later." in settings_html
    assert "Permissions" in settings_html
    assert "Read-only assistant answers" in settings_html
    assert "Budget write" in settings_html
    assert "Transaction write (reserved)" not in settings_html
    assert "Reserved for future assistant transaction entry endpoints. Safe to leave off today." not in settings_html
    assert "Let Pip use SteadyPlan safely" not in settings_html
    assert "assistant-friendly endpoints" not in settings_html
    assert "Just a friendly label so you know what this token is for." not in settings_html

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
    assert "Permissions: Read-only assistant answers, Budget write" in create_html
    assert "Permissions: assistant:read" not in create_html
    assert "Permissions: assistant:budget_write" not in create_html
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
    second_view_html = second_view.get_data(as_text=True)
    assert "data-assistant-token-value=" not in second_view_html
    assert "Read-only assistant answers, Budget write" in second_view_html
    assert "assistant:read, assistant:budget_write" not in second_view_html

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



def test_assistant_write_is_logged_and_visible_in_settings(app, client, make_user):
    uid, username, password = make_user(username="assistant-audit-user")

    with app.app_context():
        from app.models import create_api_token, create_budget_item, fetch_budget_sections

        fetch_budget_sections(uid)
        item_id = create_budget_item(
            {
                "name": "Phone sinking fund",
                "section": "discretionary",
                "default_amount": 50,
                "notes": "",
                "sort_order": 0,
            },
            uid,
        )
        token = create_api_token(
            uid,
            label="Pip budget write",
            token_kind="assistant",
            scopes=["assistant:budget_write"],
        )

    write_resp = client.post(
        f"/api/v1/assistant/budget-items/{item_id}/month-entry",
        headers=_bearer(token),
        json={"month": "2026-05", "amount": 799},
    )
    assert write_resp.status_code == 200

    with app.app_context():
        from app.models import fetch_assistant_audit_events

        events = fetch_assistant_audit_events(uid)
        assert len(events) == 1
        assert events[0]["token_label"] == "Pip budget write"
        assert events[0]["action_type"] == "budget_item_month_entry_updated"
        assert events[0]["target_label"] == "Phone sinking fund"
        assert events[0]["month_key"] == "2026-05"
        assert events[0]["after_state"]["amount"] == 799
        assert events[0]["before_state"]["amount"] == 50

    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    settings_resp = client.get("/settings/")
    settings_html = settings_resp.get_data(as_text=True)
    assert settings_resp.status_code == 200
    assert "Recent assistant activity" in settings_html
    assert "Phone sinking fund" in settings_html
    assert "2026-05" in settings_html
    assert "799" in settings_html
