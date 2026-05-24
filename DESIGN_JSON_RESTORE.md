# SteadyPlan — JSON Restore/Import (Design Note)

## Summary
SteadyPlan supports a user-scoped JSON export at `GET /settings/export.json` and a safe v1 restore/import flow. Restore treats backups as **scenario-free data ownership tooling**: validate first, then **replace the current user’s data** in one transaction. No merge mode, no partial import, and no cross-user leakage.

Implemented endpoints:
- Validate (dry-run): `POST /settings/restore/validate` (no DB writes)
- Commit restore: `POST /settings/restore/commit` (destructive; requires explicit confirmation)

Key implementation modules:
- `app/services/restore_validation.py` (validator)
- `app/services/restore_service.py` (transactional restore writer)

## Current Export Shape (Schema v1)
As of `export_schema_version == 1`, `/settings/export.json` returns a JSON object with the following top-level keys:

- `meta` (object)
- `assumptions` (object)
- `accounts` (array)
- `holdings` (array)
- `holding_catalogue` (array)
- `goals` (array)
- `debts` (array)
- `budget` (object)
- `history` (object)
- `planning` (object)

`meta` contains:

- `meta.exported_at` (ISO timestamp string)
- `meta.export_schema_version` (integer, currently `1`)
- `meta.app` (string, e.g. “SteadyPlan”)

Notes:

- `planning.allowance_tracking` is included and is user-scoped.
- Export is user-scoped and must not include other users’ data.
- Export should continue to exclude legacy `allowance_tracking` rows where `user_id IS NULL`.

## Proposed v1 Behaviour
### Restore Mode
v1 mode: **replace-only** for the currently logged-in user.

- Replace-only means: delete the current user’s SteadyPlan data and re-create it from the backup.
- Merge is explicitly deferred (conflict resolution, duplicate detection, ID collisions, and reference reconciliation are too risky for v1).
- Partial import is explicitly deferred (e.g. “import only goals”).

### Safety and UX Flow (Two-Step)
1. **Validate (dry run)**
   - User selects a JSON file.
   - App parses the file and validates structure + references.
   - App shows a restore preview summary:
     - `meta.exported_at`, `meta.export_schema_version`
     - counts per section (accounts, holdings, goals, budget entries, snapshots, overrides, allowance rows, etc.)
     - warnings/errors (blocking)
   - No DB writes.
   - If valid, the uploaded JSON is staged server-side (token + session-bound) so the user can commit without re-uploading.

2. **Confirm restore**
   - Clear warning: “This will delete and replace your current SteadyPlan data.”
   - Requires explicit confirmation:
     - checkbox `confirm_replace`
     - typed phrase `RESTORE`
   - On confirm: perform replace restore in a single transaction.
   - The staged file is re-validated before any DB writes.

### Placement
Restore UI should live in Settings under a clearly labelled “Restore / Danger” area (near reset), with conservative copy about overwrite risk.

### Staging security (implemented)
To prevent path traversal and accidental long-lived files:
- staged backups are stored under a dedicated staging directory
- a non-guessable token selects the staged file (validated against a strict token regex)
- the token is bound to the user’s session (session token + user_id + staged_at)
- staged restore previews expire after 1 hour (TTL)
- opportunistic cleanup removes expired staged files

## Schema / Versioning Rules
### Version gating
- Require `meta.export_schema_version` to exist and equal `1` for v1.
- If schema version is unknown (e.g. `>1`), reject with a clear message:
  - “This export is from a newer SteadyPlan version and can’t be restored here.”
- If schema version is missing/invalid, reject.

### Required sections (must match exporter output)
For `export_schema_version == 1`, require the presence and correct type for:

- `meta` (object)
- `assumptions` (object)
- `accounts` (array)
- `holdings` (array)
- `holding_catalogue` (array)
- `goals` (array)
- `debts` (array)
- `budget` (object with `sections`, `items`, `entries`)
- `history` (object)
- `planning` (object)

If the exporter’s output changes in future (new sections, renamed keys), the importer should reject unsupported schema versions rather than guessing.

## Data Validation Rules (v1)
Validation is strict in v1: **any error rejects the file**, and no writes occur.

### General checks
- File must parse as JSON object.
- Required top-level keys must exist and have correct types.
- Numeric fields must be finite (reject NaN/Infinity).
- Dates must match expected formats:
  - day dates: `YYYY-MM-DD`
  - month keys: `YYYY-MM`
  - tax years: `YYYY-YY` where applicable (e.g. `2026-27`)

### Referential integrity (examples)
Validate that references resolve *within the file*:
- `holdings[].account_id` references an account in `accounts`
- `holdings[].holding_catalogue_id` references a row in `holding_catalogue` (when present)
- `budget.entries[].budget_item_id` references a row in `budget.items`
- `budget.items[].linked_account_id` references a row in `accounts` (when present)
- `budget.items[].linked_debt_id` references a row in `debts` (when present)
- `history.monthly_snapshots[].account_id` references a row in `accounts`
- `planning.contribution_overrides[].account_id` references a row in `accounts`
- `planning.cash_flow_events[].account_id` references a row in `accounts`
- `planning.cash_flow_events[].counterparty_account_id` references a row in `accounts` (when present)

If any references cannot be resolved, reject the file.

## Identity and Ownership Rules
Restore/import must never trust identity/ownership data embedded in the file.

### User ownership
- Ignore/strip any `user_id` values found in the backup file (including `NULL`).
- Assign all imported rows that are user-scoped to `current_user.id`.
- Never import data for other users.

### Allowance tracking (explicit rules)
- Export continues to exclude legacy DB rows where `allowance_tracking.user_id IS NULL`.
- Import should:
  - ignore/strip any `user_id` value provided for allowance tracking rows (including `NULL`)
  - import valid `allowance_tracking` rows and assign them to `current_user.id`
  - never trust ownership from the file

## ID Strategy (Remap IDs)
Exported numeric `id` values cannot be inserted verbatim because:
- they may collide with existing rows
- multiple users may exist
- SQLite auto-increment sequences may differ

### v1 approach
During restore, create new rows and build maps:
- `account_id_map: old_id -> new_id`
- `catalogue_id_map: old_id -> new_id`
- `debt_id_map: old_id -> new_id`
- `budget_item_id_map: old_id -> new_id`
- `monthly_review_id_map: old_id -> new_id` (if restoring review IDs rather than reconstructing by month)

All foreign keys in imported rows must be rewritten using the maps.

## Transaction / Rollback Strategy
### One transaction for replace restore
- Validation completes fully before any deletion/write.
- Restore runs inside a single DB transaction:
  1. `BEGIN`
  2. delete current user’s data only
  3. insert restored data (with ID remapping + user_id assignment)
  4. `COMMIT`
- If any error occurs after `BEGIN`, `ROLLBACK` so the user’s current data remains intact.

### Deletion scope
Deletion must be limited to `current_user.id` only (never touch other users). It should reuse the same user-scoped deletion behaviour as “Start fresh”.

## Implementation Notes (v1)
The restore writer ignores `user_id` values embedded in the backup, assigns ownership to the current user, remaps IDs, and performs all work in one transaction. Any validation or write failure results in a full rollback and a safe user-facing error.

## Test Plan (v1)
Restore is covered by tests for:

- Validation:
  - valid backup passes validation, returns expected counts
  - corrupt JSON rejected
  - unsupported schema rejected
  - missing required sections rejected
  - broken references rejected
- Ownership:
  - imported `user_id` ignored; all rows assigned to current user
  - no cross-user leakage (two users in DB; restore for one does not touch the other)
  - legacy/NULL ownership never imported for another user
- Transaction safety:
  - forced failure mid-restore triggers rollback
  - after rollback, original data remains unchanged
- Replace scope:
  - deletes only current user’s data; does not delete other users’ rows

## Open Questions / Risks
- `allowance_tracking.user_id` may be nullable in some DBs due to legacy rows. Import must not assume NOT NULL and must always assign ownership during write.
- `planning.cash_flow_events.counterparty_account_id` remapping: should v1 reject if the referenced account is missing from the file, or set it to NULL? Recommendation for v1: reject to keep integrity strict.
- If export shape changes without a schema bump, import should treat this as invalid; exporter and importer must stay locked via `meta.export_schema_version`.
