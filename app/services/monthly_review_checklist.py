import json


MONTHLY_REVIEW_CHECKLIST_ITEMS = [
    {"key": "account_balances", "label": "Account balances reviewed"},
    {"key": "goals", "label": "Goals reviewed"},
    {"key": "debts", "label": "Debts reviewed"},
    {"key": "budget", "label": "Budget reviewed"},
    {"key": "assumptions", "label": "Projection assumptions reviewed"},
    {"key": "backup", "label": "Backup/export checked"},
]

_NOTES_SCHEMA_KEY = "__shelly_monthly_review_notes_v"
_NOTES_SCHEMA_VERSION = 1


def parse_monthly_review_notes(raw_notes):
    raw_notes = "" if raw_notes is None else str(raw_notes)
    raw_notes = raw_notes.strip()

    if raw_notes.startswith("{") and raw_notes.endswith("}"):
        try:
            data = json.loads(raw_notes)
        except Exception:
            data = None
        if isinstance(data, dict) and data.get(_NOTES_SCHEMA_KEY) == _NOTES_SCHEMA_VERSION:
            notes = (data.get("notes") or "").strip()
            checked = data.get("checked") or []
            if not isinstance(checked, list):
                checked = []
            checked_set = {str(k) for k in checked if k is not None}
            return {"notes": notes, "checked": checked_set, "is_structured": True}

    return {"notes": raw_notes, "checked": set(), "is_structured": False}


def encode_monthly_review_notes(notes, checked_keys):
    notes = "" if notes is None else str(notes)
    notes = notes.strip()
    checked = sorted({str(k) for k in (checked_keys or set()) if k})

    if not checked:
        return notes

    payload = {
        _NOTES_SCHEMA_KEY: _NOTES_SCHEMA_VERSION,
        "notes": notes,
        "checked": checked,
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def checked_count(checked_keys):
    allowed = {i["key"] for i in MONTHLY_REVIEW_CHECKLIST_ITEMS}
    return sum(1 for k in (checked_keys or set()) if k in allowed)

