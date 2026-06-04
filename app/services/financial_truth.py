from datetime import datetime, timezone

from app.calculations import effective_account_value
from app.models import (
    fetch_all_accounts,
    fetch_holding_totals_by_account,
    fetch_monthly_review,
    mark_review_item_updated,
    save_account_daily_snapshots,
    save_daily_snapshot,
    update_account,
    upsert_monthly_snapshot,
)


def recompute_user_daily_snapshots(user_id):
    holdings_totals = fetch_holding_totals_by_account(user_id)
    accounts = fetch_all_accounts(user_id)
    account_values = [(a["id"], effective_account_value(a, holdings_totals)) for a in accounts]
    save_daily_snapshot(user_id, sum(value for _, value in account_values))
    save_account_daily_snapshots(user_id, account_values)



def apply_account_balance_update(account, user_id, new_balance, month_key, review_id=None, recompute_daily=True):
    if (account.get("wrapper_type") or "").lower() == "premium bonds":
        new_balance = min(float(new_balance), 50000.0)
    else:
        new_balance = float(new_balance)

    payload = dict(account)
    payload["current_value"] = new_balance
    payload["last_updated"] = datetime.now(timezone.utc).isoformat()
    update_account(payload, user_id)
    upsert_monthly_snapshot(int(account["id"]), month_key, new_balance)
    if recompute_daily:
        recompute_user_daily_snapshots(user_id)

    resolved_review_id = review_id
    if resolved_review_id is None:
        review = fetch_monthly_review(month_key, user_id)
        if review is not None:
            resolved_review_id = review["id"]
    if resolved_review_id is not None:
        mark_review_item_updated(resolved_review_id, int(account["id"]), "balance_updated")

    return new_balance
