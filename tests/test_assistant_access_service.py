from app.services.assistant_access import (
    assistant_scope_label,
    assistant_scope_labels,
    assistant_scope_options,
    assistant_target_label,
    assistant_token_label,
    assistant_token_last_used_label,
    assistant_token_secret_heading,
    normalise_requested_assistant_scopes,
    pop_plaintext_assistant_token,
    stash_plaintext_assistant_token,
)


def test_assistant_scope_helpers_share_one_contract():
    assert assistant_scope_label("assistant:read") == "Read-only assistant answers"
    assert assistant_scope_label("assistant:budget_write") == "Budget write"
    assert assistant_scope_label("assistant:transactions_write", include_reserved=True) == "Transaction write (reserved)"
    assert assistant_scope_labels(["assistant:read", "assistant:budget_write"]) == [
        "Read-only assistant answers",
        "Budget write",
    ]
    options = assistant_scope_options(include_reserved=True)
    assert [opt["key"] for opt in options] == [
        "assistant:read",
        "assistant:budget_write",
        "assistant:transactions_write",
    ]



def test_assistant_scope_normalisation_and_token_session_helpers():
    assert normalise_requested_assistant_scopes([
        " assistant:budget_write ",
        "assistant:read",
        "assistant:budget_write",
        "not-real",
    ]) == ["assistant:budget_write", "assistant:read"]
    assert normalise_requested_assistant_scopes([]) == ["assistant:read"]

    session_store = {}
    stash_plaintext_assistant_token(
        session_store,
        token="secret-token",
        label="  ",
        scopes=["assistant:read"],
        action="created",
    )
    assert session_store["assistant_plaintext_label"] == "Unlabelled assistant token"

    payload = pop_plaintext_assistant_token(session_store)
    assert payload == {
        "value": "secret-token",
        "label": "Unlabelled assistant token",
        "scopes": ["assistant:read"],
        "action": "created",
    }
    assert session_store == {}
    assert pop_plaintext_assistant_token(session_store) is None



def test_assistant_display_helpers_cover_fallbacks():
    assert assistant_target_label("", "budget_item") == "Budget item"
    assert assistant_target_label("Phone sinking fund", "budget_item") == "Phone sinking fund"
    assert assistant_token_label("  ") == "Unlabelled assistant token"
    assert assistant_token_last_used_label("") == "Not used yet"
    assert assistant_token_secret_heading("regenerated") == "Replacement assistant token"
