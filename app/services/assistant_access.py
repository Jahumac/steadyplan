from app.models import (
    ASSISTANT_SCOPE_BUDGET_WRITE,
    ASSISTANT_SCOPE_READ,
    ASSISTANT_SCOPE_TRANSACTIONS_WRITE,
)


def assistant_scope_options(include_reserved=False):
    options = [
        {
            "key": ASSISTANT_SCOPE_READ,
            "label": "Read-only assistant answers",
            "hint": "Lets this token answer portfolio, monthly budget, and affordability questions without changing your data.",
        },
        {
            "key": ASSISTANT_SCOPE_BUDGET_WRITE,
            "label": "Budget write",
            "hint": "Lets this token update one month's amount on an existing manual, unlinked budget item. It does not allow broader budget, account, or transaction edits.",
        },
    ]
    if include_reserved:
        options.append(
            {
                "key": ASSISTANT_SCOPE_TRANSACTIONS_WRITE,
                "label": "Transaction write (reserved)",
                "hint": "Reserved for future assistant transaction entry endpoints. Safe to leave off today.",
            }
        )
    return options


def assistant_scope_label_map(include_reserved=False):
    return {
        opt["key"]: opt["label"]
        for opt in assistant_scope_options(include_reserved=include_reserved)
    }


def assistant_scope_label(scope, *, include_reserved=False):
    scope_text = str(scope or "").strip().lower()
    return assistant_scope_label_map(include_reserved=include_reserved).get(
        scope_text,
        scope_text or "This permission",
    )


def assistant_scope_labels(scopes, *, include_reserved=False):
    labels = []
    label_map = assistant_scope_label_map(include_reserved=include_reserved)
    for scope in scopes or [ASSISTANT_SCOPE_READ]:
        scope_text = str(scope or "").strip().lower()
        labels.append(label_map.get(scope_text, scope_text or ASSISTANT_SCOPE_READ))
    return labels


def assistant_action_label(action_type):
    action_text = str(action_type or "").strip().lower()
    return {
        "budget_item_month_entry_updated": "Budget month amount updated",
    }.get(action_text, action_text or "—")


def assistant_amount_change_label(before_amount, after_amount):
    if before_amount is None or after_amount is None:
        return "—"
    return f"£{float(before_amount):,.2f} → £{float(after_amount):,.2f}"


def assistant_target_label(target_label, target_type):
    label_text = str(target_label or "").strip()
    if label_text:
        return label_text
    target_text = str(target_type or "").strip().lower()
    return {
        "budget_item": "Budget item",
    }.get(target_text, target_text or "—")


def assistant_token_label(label):
    label_text = str(label or "").strip()
    return label_text or "Unlabelled assistant token"


def assistant_token_last_used_label(last_used_at):
    last_used_text = str(last_used_at or "").strip()
    return last_used_text or "Not used yet"


def assistant_token_secret_heading(action):
    action_text = str(action or "").strip().lower()
    return {
        "created": "New assistant token",
        "regenerated": "Replacement assistant token",
    }.get(action_text, "Assistant token")


def normalise_requested_assistant_scopes(raw_scopes):
    ordered = []
    valid = {opt["key"] for opt in assistant_scope_options(include_reserved=True)}
    for scope in raw_scopes or []:
        scope_text = str(scope or "").strip().lower()
        if scope_text in valid and scope_text not in ordered:
            ordered.append(scope_text)
    return ordered or [ASSISTANT_SCOPE_READ]


def pop_plaintext_assistant_token(session_store):
    token = session_store.pop("assistant_plaintext_token", None)
    if not token:
        return None
    return {
        "value": token,
        "label": assistant_token_label(session_store.pop("assistant_plaintext_label", None)),
        "scopes": session_store.pop("assistant_plaintext_scopes", []) or [],
        "action": session_store.pop("assistant_plaintext_action", "created"),
    }


def stash_plaintext_assistant_token(session_store, *, token, label, scopes, action):
    session_store["assistant_plaintext_token"] = token
    session_store["assistant_plaintext_label"] = assistant_token_label(label)
    session_store["assistant_plaintext_scopes"] = list(scopes or [])
    session_store["assistant_plaintext_action"] = action
