# SteadyPlan JSON API

Bearer-token HTTP JSON API for external clients (Android, desktop, scripts).

**Base URL:** `http://<your-host>:<port>/api/v1`
**Auth:** `Authorization: Bearer <token>` on every request.
**Response type:** `application/json`.

---

## Minting a token

SteadyPlan now supports two token styles:

- **General API token** — created from the server CLI, keeps the legacy broad API access.
- **Assistant token** — created from **Settings → Assistant access** in the web UI, limited to assistant endpoints and explicit scopes.

Tokens are created from the command line on the server:

```bash
python scripts/api_token.py create <username> "my android phone"
```

The token prints once. Save it — it is not recoverable. To list or revoke:

```bash
python scripts/api_token.py list <username>
python scripts/api_token.py revoke <token_id>
```

Assistant tokens are created and rotated in the Settings page so the raw value is only shown once.

Tokens are stored in the `api_tokens` table alongside `last_used_at`, `token_kind`, and scope metadata so you
can see which tokens are active.

---

## Error format

Non-2xx responses always return:

```json
{ "error": "<code>", "message": "<human-readable>" }
```

Codes currently used: `missing_token`, `invalid_token`, `insufficient_scope`, `not_found`,
`bad_request`, `method_not_allowed`, `server_error`.

---

## Endpoints
All endpoints are scoped to the token's user unless stated otherwise. Most are GET; a small set of POST endpoints exists for deliberate, user-scoped writes.

### `GET /me`
Current user info.
```json
{ "id": 1, "username": "alice", "is_admin": true, "token_kind": "assistant", "scopes": ["assistant:read"] }
```

### `GET /accounts`
List all active accounts for the user.
```json
{ "accounts": [ { "id": 1, "name": "...", "wrapper_type": "...", ... } ] }
```

### `GET /accounts/<id>`
Single account with its holdings embedded.
```json
{ "id": 1, "name": "...", "holdings": [ ... ] }
```

### `GET /holdings`
Every holding across every account.

### `GET /goals`
List goals.

### `GET /overview`
Aggregate snapshot.
```json
{ "total_value": 123456.78, "monthly_contribution": 1000, "account_count": 5 }
```

### `GET /budget/<YYYY-MM>`
Budget for a specific month. Falls back to default amounts if no entries
exist yet for that month.

### `GET /assumptions`
Growth rate, retirement age, ISA/LISA allowances, etc.

### `GET /assistant/month-summary/<YYYY-MM>`
Assistant-oriented read-only monthly budget roll-up using the same source rules as the Budget page. Assistant tokens need the `assistant:read` scope.

Returns:
- `summary.total_income`
- `summary.total_expenses`
- `summary.pre_salary_total`
- `summary.take_home_outgoings`
- `summary.planned_savings`
- `summary.planned_debt_payments`
- `summary.available_after_budget`
- `summary.savings_rate`
- `signals[]` for obvious caution flags such as no income budgeted or a planned deficit
- `sections[]` with the underlying rows and source (`default`, `inherited`, `manual_override`, `linked_account`, `linked_debt`)

```json
{
  "month": "2026-04",
  "month_label": "April 2026",
  "summary": {
    "total_income": 3000,
    "total_expenses": 2250,
    "pre_salary_total": 300,
    "take_home_outgoings": 1950,
    "planned_savings": 500,
    "planned_debt_payments": 150,
    "available_after_budget": 1050,
    "savings_rate": 16.67
  },
  "signals": [
    {
      "level": "info",
      "code": "pre_salary_contributions_excluded",
      "message": "Pre-salary contributions are shown for visibility but excluded from take-home affordability."
    }
  ],
  "sections": [
    {
      "key": "income",
      "label": "Income",
      "total": 3000,
      "rows": [
        {
          "name": "Salary",
          "amount": 3000,
          "source": "default",
          "pre_salary": false
        }
      ]
    }
  ]
}
```

### `GET /assistant/portfolio-overview`
Assistant-oriented read-only portfolio snapshot for questions like current net worth, how much is accessible now, and how much sits in each account.

Important behaviour:
- uses **effective account values**, so holdings-based accounts use live holdings totals plus uninvested cash
- splits totals into `accessible`, `restricted`, and `locked` using the same conservative classification rules as the Planning insights service
- returns per-account access labels/reasons so the assistant can explain *why* something is or is not counted as accessible

```json
{
  "summary": {
    "total_net_worth": 2384,
    "accessible_total": 1284,
    "restricted_total": 400,
    "locked_total": 700,
    "accessible_pct": 53.86,
    "restricted_pct": 16.78,
    "locked_pct": 29.36,
    "account_count": 3
  },
  "accounts": [
    {
      "name": "ISA Portfolio",
      "wrapper_type": "Stocks & Shares ISA",
      "effective_value": 1284,
      "holdings_value": 1234,
      "uninvested_cash": 50,
      "accessible_value": 1284,
      "access_type": "accessible",
      "access_label": "Accessible before pension age"
    }
  ]
}
```

### `GET /assistant/affordability/<YYYY-MM>?amount=...&spread_months=...`
Assistant-oriented read-only affordability check for a proposed purchase.

Important behaviour:
- compares the purchase against that month’s `available_after_budget`
- also checks whether the purchase could be covered by assets classed as accessible before pension age
- keeps those two concepts separate, because **accessible assets are not the same thing as spare cash**
- `spread_months` is optional and defaults to `1`

```json
{
  "month": "2026-04",
  "month_label": "April 2026",
  "purchase": {
    "amount": 1800,
    "spread_months": 3,
    "monthly_cost": 600
  },
  "assessment": {
    "verdict": "yes",
    "verdict_reason": "It fits inside the planned monthly budget headroom.",
    "budget_affordable": true,
    "accessible_funding_available": true
  },
  "budget": {
    "available_after_budget": 1400,
    "remaining_after_purchase": 800
  },
  "access": {
    "accessible_total": 2000,
    "restricted_total": 0,
    "locked_total": 9000,
    "accessible_after_purchase": 200
  },
  "signals": [
    {
      "level": "info",
      "code": "spread_applied",
      "message": "Affordability is being assessed as 3 monthly payments of 600.00, not a single upfront hit."
    }
  ]
}
```

### `GET /health`  _(no auth)_
Liveness probe for uptime monitors. Returns 200 with DB status and last
backup time (file presence only), or 503 if the DB is unreachable.
```json
{
  "ok": true,
  "checks": { "database": "ok", "last_backup": "2026-04-14T03:00:02" },
  "timestamp": "2026-04-14T12:00:00+00:00"
}
```

---

## Write endpoints

All writes require auth and are scoped to the token's user (attempting
to mutate another user's data returns 404).

### `POST /accounts/<id>/balance`
Update a manual-valuation account's balance. Also records a monthly
snapshot so history stays consistent with the monthly-review flow.
```json
{ "current_value": 12345.67, "month": "2026-04" }    ← month optional
```

### `POST /contributions/isa`
Log an ISA contribution.
```json
{ "account_id": 3, "amount": 500, "date": "2026-04-10", "note": "optional" }
```

### `POST /contributions/pension`
Log a pension contribution. `kind` is one of: `personal`, `employer`,
`salary_sacrifice`.
```json
{ "account_id": 7, "amount": 400, "date": "2026-04-10",
  "kind": "personal", "note": "optional" }
```

### `POST /dividends`
Log a dividend receipt.
```json
{ "account_id": 2, "amount": 50, "date": "2026-04-10", "note": "optional" }
```

### `POST /monthly-review/<YYYY-MM>/complete`
Mark a month's review as complete. Takes a snapshot of every account's
effective current value (same as the web UI's "mark complete" button).

Snapshot rules on completion:
- Holdings-based accounts: always snapshot from effective holdings value.
- Manual/Premium Bonds accounts: snapshot only if their balance was updated in that review (prevents silently recording stale balances as fresh historical truth).
```json
{ "notes": "all good" }    ← notes optional
```
Returns the review id, status, and how many account snapshots were taken.

---

## Example

```bash
TOKEN=<your-token>
curl -H "Authorization: Bearer $TOKEN" https://steadyplan.example.com/api/v1/overview
```

---

## Stability

Breaking changes will go under `/api/v2`. New fields may be added to
existing responses without warning — clients must ignore unknown keys.

Writes are intentionally kept small and endpoint-by-endpoint so the API stays safe as it grows.
