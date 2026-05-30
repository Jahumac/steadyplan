import datetime
from typing import List, Dict, Any

from app.models._conn import get_connection
from app.models import (
    fetch_all_accounts,
    fetch_all_goals,
    fetch_assumptions,
    get_user_by_id,
)

HEALTH_STATUS_GOOD = "good"
HEALTH_STATUS_WARNING = "warning"
HEALTH_STATUS_INFO = "info"

def build_data_health_summary(user_id: int) -> Dict[str, Any]:
    """
    Builds a read-only summary of the user's data health.
    Identifies potential areas of concern like missing data or stale entries.
    """
    health_items: List[Dict[str, str]] = []
    overall_status = HEALTH_STATUS_GOOD

    with get_connection() as conn:
        user = get_user_by_id(user_id)
        if not user:
            return {
                "overall_status": HEALTH_STATUS_WARNING,
                "summary_message": "User not found.",
                "health_items": [],
            }

        # --- Check 1: Accounts ---
        accounts = fetch_all_accounts(user_id)
        if not accounts:
            health_items.append({
                "status": HEALTH_STATUS_WARNING,
                "title": "No accounts set up",
                "explanation": "You haven't added any financial accounts yet. Add accounts to track your finances.",
                "link": "/accounts/?mode=create",
                "cta_text": "Add your first account",
            })
            overall_status = HEALTH_STATUS_WARNING
        else:
            stale_accounts = []
            for account in accounts:
                # Check for recent monthly snapshots or account daily snapshots
                # Assuming 'snapshot_date' is YYYY-MM-DD
                latest_snapshot_row = conn.execute(
                    """
                    SELECT MAX(snapshot_date) as max_date FROM monthly_snapshots
                    WHERE account_id = ?
                    UNION ALL
                    SELECT MAX(snapshot_date) as max_date FROM account_daily_snapshots
                    WHERE account_id = ?
                    ORDER BY max_date DESC
                    LIMIT 1
                    """,
                    (account["id"], account["id"])
                ).fetchone()

                if latest_snapshot_row and latest_snapshot_row.get("max_date") is not None:
                    latest_date = datetime.datetime.strptime(latest_snapshot_row["max_date"], "%Y-%m-%d").date()
                    if (datetime.date.today() - latest_date).days > 60: # More than 60 days old
                        stale_accounts.append(account["name"])
                else:
                    stale_accounts.append(account["name"]) # No snapshots found

            if stale_accounts:
                health_items.append({
                    "status": HEALTH_STATUS_WARNING,
                    "title": "Some accounts have stale or missing history",
                    "explanation": f"The following accounts have no recent balance history: {', '.join(stale_accounts)}. Update them to ensure accurate projections.",
                    "link": "/history",
                })
                if overall_status == HEALTH_STATUS_GOOD:
                    overall_status = HEALTH_STATUS_WARNING

        # --- Check 2: Goals ---
        goals = fetch_all_goals(user_id)
        if not goals:
            health_items.append({
                "status": HEALTH_STATUS_WARNING,
                "title": "No financial goals set",
                "explanation": "You haven't set any financial goals yet. Define your goals to track progress.",
                "link": "/goals/?mode=create",
                "cta_text": "Set your first goal",
            })
            if overall_status == HEALTH_STATUS_GOOD:
                overall_status = HEALTH_STATUS_WARNING
        else:
            goals_missing_target = []
            for goal in goals:
                if not goal.get("target_value"):
                    goals_missing_target.append(goal["name"])
            if goals_missing_target:
                health_items.append({
                    "status": HEALTH_STATUS_WARNING,
                    "title": "Some goals are missing a target amount",
                    "explanation": f"The following goals are missing a target amount: {', '.join(goals_missing_target)}. Update them to track progress effectively.",
                    "link": "/goals",
                    "cta_text": "Review goals",
                })
                if overall_status == HEALTH_STATUS_GOOD:
                    overall_status = HEALTH_STATUS_WARNING

        # --- Check 3: Assumptions ---
        assumptions = conn.execute(
            "SELECT * FROM assumptions WHERE user_id = ?", (user_id,)
        ).fetchone()
        
        if assumptions:
            if assumptions.get("retirement_age") == 60 and assumptions.get("retirement_goal_value") == 1000000:
                health_items.append({
                    "status": HEALTH_STATUS_INFO,
                    "title": "Default retirement assumptions in use",
                    "explanation": "Your retirement age and goal value are set to default values. Consider updating them to reflect your personal plans.",
                    "link": "/settings#assumptions",
                })
        else:
            health_items.append({
                "status": HEALTH_STATUS_WARNING,
                "title": "No assumptions set up",
                "explanation": "You haven't set up your financial assumptions. These are crucial for projections.",
                "link": "/settings#assumptions",
            })
            if overall_status == HEALTH_STATUS_GOOD:
                overall_status = HEALTH_STATUS_WARNING

        # --- Check 4: Budget entries for current month ---
        current_month_key = datetime.date.today().strftime("%Y-%m")
        budget_entries_count_row = conn.execute(
            """
            SELECT COUNT(*) as count FROM budget_entries
            WHERE month_key = ? AND budget_item_id IN (
                SELECT id FROM budget_items WHERE user_id = ?
            )
            """,
            (current_month_key, user_id)
        ).fetchone()
        budget_entries_count = budget_entries_count_row["count"] if budget_entries_count_row else 0

        if budget_entries_count == 0:
            health_items.append({
                "status": HEALTH_STATUS_INFO,
                "title": "No budget entries for the current month",
                "explanation": f"You have no budget entries for {current_month_key}. Consider adding some to track your spending.",
                "link": "/budget",
            })

    summary_message = "Looks good!"
    if overall_status == HEALTH_STATUS_WARNING:
        summary_message = "Worth checking."
    elif overall_status == HEALTH_STATUS_INFO and health_items:
        summary_message = "Some information to review."

    return {
        "overall_status": overall_status,
        "summary_message": summary_message,
        "health_items": health_items,
    }
