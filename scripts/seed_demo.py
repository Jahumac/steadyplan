"""Populate the demo account with realistic UK investor data.

Usage:
    python scripts/seed_demo.py [--username demo] [--password demo123] [--create-user]

Creates 7 months of history (Oct 2025 – Apr 2026) with realistic accounts,
holdings, goals, budget, and monthly reviews so the app looks compelling.
Safe to re-run: clears the demo user's data first.
"""
import argparse
import sys
from datetime import datetime, timezone, date, timedelta

sys.path.insert(0, ".")

from app import create_app
from app.models import get_connection, init_db
from app.models.users import create_user, get_user_by_username
from app.models.accounts import (
    create_account,
    add_holding,
    add_holding_catalogue_item,
    update_catalogue_price,
)
from app.models.goals import create_goal
from app.models.budget import create_budget_item, upsert_budget_entry, fetch_budget_sections
from app.models.planning_snapshots import upsert_monthly_snapshot
from app.models.planning_reviews import (
    fetch_or_create_monthly_review,
    ensure_monthly_review_items,
    update_monthly_review,
    fetch_monthly_review_items,
    update_monthly_review_item,
)
from app.models.planning_assumptions import update_assumptions, fetch_assumptions
from app.models.planning_allowances import add_isa_contribution, add_pension_contribution


# ── Config ────────────────────────────────────────────────────────────────────

MONTHS = [
    "2025-10", "2025-11", "2025-12",
    "2026-01", "2026-02", "2026-03", "2026-04",
]

NOW = datetime.now(timezone.utc).isoformat()
TODAY = date.today().isoformat()


# ── Account snapshots over time ───────────────────────────────────────────────
# Each dict: account_name → value for that month.
# Apr 2026 = current live value stored on the account.

ACCOUNT_HISTORY = {
    #                         Oct-25   Nov-25   Dec-25   Jan-26   Feb-26   Mar-26   Apr-26
    "Vanguard S&S ISA":      [14200,   14850,   14500,   15300,   15900,   16400,   17100],
    "Moneybox LISA":         [ 5100,    5350,    5280,    5500,    5650,    5820,    6050],
    "Standard Life Pension": [ 8200,    8600,    9000,    9400,    9800,   10300,   10800],
    "Vanguard SIPP":         [22000,   23200,   22800,   24100,   24900,   25800,   26900],
    "Marcus Cash ISA":       [ 3100,    3250,    3400,    3400,    3400,    3400,    3500],
    "Emergency Fund":        [ 5000,    5000,    5000,    5000,    6000,    6000,    6000],
}

# Monthly contributions per account (used for review items)
CONTRIBUTIONS = {
    "Vanguard S&S ISA":       500,
    "Moneybox LISA":          333,
    "Standard Life Pension":  400,
    "Vanguard SIPP":          400,
    "Marcus Cash ISA":          0,
    "Emergency Fund":           0,
}



def seed(username="demo"):
    app = create_app()
    with app.app_context():
        init_db()

        user = get_user_by_username(username)
        if user is None:
            raise RuntimeError(f"No user '{username}' found.")
        uid = user.id
        print(f"Seeding demo data for user '{username}' (id={uid})…")

        # ── Wipe existing data ────────────────────────────────────────────────
        with get_connection() as conn:
            # Clear FK-dependent tables first, then core tables
            conn.execute("DELETE FROM account_daily_snapshots WHERE account_id IN (SELECT id FROM accounts WHERE user_id = ?)", (uid,))
            conn.execute("DELETE FROM portfolio_daily_snapshots WHERE user_id = ?", (uid,))
            conn.execute("DELETE FROM isa_contributions WHERE user_id = ?", (uid,))
            conn.execute("DELETE FROM pension_contributions WHERE user_id = ?", (uid,))
            conn.execute("DELETE FROM dividend_records WHERE user_id = ?", (uid,))
            conn.execute("DELETE FROM cgt_disposals WHERE user_id = ?", (uid,))
            conn.execute("DELETE FROM pension_carry_forward WHERE user_id = ?", (uid,))
            conn.execute("DELETE FROM holdings WHERE account_id IN (SELECT id FROM accounts WHERE user_id = ?)", (uid,))
            conn.execute("DELETE FROM contribution_overrides WHERE account_id IN (SELECT id FROM accounts WHERE user_id = ?)", (uid,))
            conn.execute("DELETE FROM monthly_snapshots WHERE account_id IN (SELECT id FROM accounts WHERE user_id = ?)", (uid,))
            conn.execute("DELETE FROM monthly_review_items WHERE review_id IN (SELECT id FROM monthly_reviews WHERE user_id = ?)", (uid,))
            conn.execute("DELETE FROM monthly_reviews WHERE user_id = ?", (uid,))
            conn.execute("DELETE FROM budget_entries WHERE budget_item_id IN (SELECT id FROM budget_items WHERE user_id = ?)", (uid,))
            conn.execute("DELETE FROM budget_items WHERE user_id = ?", (uid,))
            conn.execute("DELETE FROM budget_sections WHERE user_id = ?", (uid,))
            conn.execute("DELETE FROM accounts WHERE user_id = ?", (uid,))
            conn.execute("DELETE FROM goals WHERE user_id = ?", (uid,))
            conn.execute("DELETE FROM assumptions WHERE user_id = ?", (uid,))
            conn.execute("DELETE FROM holding_catalogue WHERE user_id = ?", (uid,))
            conn.commit()

        # ── Assumptions ───────────────────────────────────────────────────────
        fetch_assumptions(uid)  # creates the row if missing
        update_assumptions({
            "annual_growth_rate": 0.07,
            "retirement_age": 60,
            "date_of_birth": "1990-06-15",
            "retirement_goal_value": 800000,
            "isa_allowance": 20000,
            "lisa_allowance": 4000,
            "dividend_allowance": 500,
            "annual_income": 55000,
            "pension_annual_allowance": 60000,
            "mpaa_enabled": 0,
            "mpaa_allowance": 10000,
            "target_dev_pct": 0.80,
            "target_em_pct": 0.20,
            "emergency_fund_target": 6000,
            "dashboard_name": "Alex (Demo)",
            "salary_day": 25,
            "update_day": 1,
            "retirement_date_mode": "birthday",
            "tax_band": "basic",
            "auto_update_prices": 0,
            "update_time_morning": "08:30",
            "update_time_evening": "18:00",
            "benchmark_rate": 0.07,
            "updated_at": NOW,
        }, uid)
        print("  ✓ Assumptions")

        # ── Accounts ──────────────────────────────────────────────────────────
        account_ids = {}

        isa_id = create_account({
            "name": "Vanguard S&S ISA",
            "provider": "Vanguard",
            "wrapper_type": "Stocks & Shares ISA",
            "category": "ISA",
            "tags": "ISA,Retirement",
            "current_value": ACCOUNT_HISTORY["Vanguard S&S ISA"][-1],
            "monthly_contribution": CONTRIBUTIONS["Vanguard S&S ISA"],
            "goal_value": None,
            "valuation_mode": "holdings",
            "growth_mode": "default",
            "growth_rate_override": None,
            "owner": "Alex",
            "notes": "Global equities — 80% developed, 20% emerging markets.",
            "last_updated": TODAY,
            "fund_fee_pct": 0.12,
            "platform_fee_pct": 0.15,
        }, uid)
        account_ids["Vanguard S&S ISA"] = isa_id

        lisa_id = create_account({
            "name": "Moneybox LISA",
            "provider": "Moneybox",
            "wrapper_type": "Lifetime ISA",
            "category": "ISA",
            "tags": "ISA,Retirement,LISA",
            "current_value": ACCOUNT_HISTORY["Moneybox LISA"][-1],
            "monthly_contribution": CONTRIBUTIONS["Moneybox LISA"],
            "goal_value": None,
            "valuation_mode": "holdings",
            "growth_mode": "default",
            "growth_rate_override": None,
            "owner": "Alex",
            "notes": "25% government bonus on up to £4,000/year. Locked until 60.",
            "last_updated": TODAY,
            "fund_fee_pct": 0.22,
            "platform_fee_pct": 0.45,
        }, uid)
        account_ids["Moneybox LISA"] = lisa_id

        wp_id = create_account({
            "name": "Standard Life Pension",
            "provider": "Standard Life",
            "wrapper_type": "Workplace Pension",
            "category": "Pension",
            "tags": "Pension,Retirement",
            "current_value": ACCOUNT_HISTORY["Standard Life Pension"][-1],
            "monthly_contribution": CONTRIBUTIONS["Standard Life Pension"],
            "goal_value": None,
            "valuation_mode": "manual",
            "growth_mode": "default",
            "growth_rate_override": None,
            "owner": "Alex",
            "notes": "5% employee + 5% employer match. Total 10% of salary.",
            "last_updated": TODAY,
            "employer_contribution": 230,
        }, uid)
        account_ids["Standard Life Pension"] = wp_id

        sipp_id = create_account({
            "name": "Vanguard SIPP",
            "provider": "Vanguard",
            "wrapper_type": "SIPP",
            "category": "Pension",
            "tags": "Pension,Retirement",
            "current_value": ACCOUNT_HISTORY["Vanguard SIPP"][-1],
            "monthly_contribution": CONTRIBUTIONS["Vanguard SIPP"],
            "goal_value": None,
            "valuation_mode": "holdings",
            "growth_mode": "default",
            "growth_rate_override": None,
            "owner": "Alex",
            "notes": "Self-invested pension. Monthly net contribution £400 (£500 gross with basic rate relief).",
            "last_updated": TODAY,
            "fund_fee_pct": 0.12,
            "platform_fee_pct": 0.15,
        }, uid)
        account_ids["Vanguard SIPP"] = sipp_id

        cash_isa_id = create_account({
            "name": "Marcus Cash ISA",
            "provider": "Goldman Sachs (Marcus)",
            "wrapper_type": "Cash ISA",
            "category": "ISA",
            "tags": "ISA,Cash",
            "current_value": ACCOUNT_HISTORY["Marcus Cash ISA"][-1],
            "monthly_contribution": CONTRIBUTIONS["Marcus Cash ISA"],
            "goal_value": None,
            "valuation_mode": "manual",
            "growth_mode": "custom",
            "growth_rate_override": 0.045,
            "owner": "Alex",
            "notes": "4.5% AER easy-access cash ISA.",
            "last_updated": TODAY,
        }, uid)
        account_ids["Marcus Cash ISA"] = cash_isa_id

        ef_id = create_account({
            "name": "Emergency Fund",
            "provider": "Monzo",
            "wrapper_type": "Current Account",
            "category": "Cash",
            "tags": "Emergency Fund,Cash",
            "current_value": ACCOUNT_HISTORY["Emergency Fund"][-1],
            "monthly_contribution": CONTRIBUTIONS["Emergency Fund"],
            "goal_value": 6000,
            "valuation_mode": "manual",
            "growth_mode": "custom",
            "growth_rate_override": 0.04,
            "owner": "Alex",
            "notes": "3 months of expenses target. Kept in a high-interest pot.",
            "last_updated": TODAY,
        }, uid)
        account_ids["Emergency Fund"] = ef_id

        print(f"  ✓ Accounts ({len(account_ids)} created)")

        # ── Holdings catalogue + holdings ─────────────────────────────────────
        # Prices as at April 2026 (realistic approximate values)
        funds = [
            # (ticker, name, asset_type, bucket, price_gbp, currency)
            ("VHVG",  "Vanguard FTSE Developed World ETF",  "ETF", "Equities", 37.42, "GBP"),
            ("VFEG",  "Vanguard FTSE Emerging Markets ETF", "ETF", "Equities", 7.18,  "GBP"),
            ("VWRP",  "Vanguard FTSE All-World ETF",        "ETF", "Equities", 108.50,"GBP"),
        ]

        cat_ids = {}
        for ticker, name, asset_type, bucket, price, currency in funds:
            cid = add_holding_catalogue_item({
                "holding_name": name,
                "ticker": ticker,
                "asset_type": asset_type,
                "bucket": bucket,
            }, uid)
            update_catalogue_price(cid, price, currency, 0.0, NOW)
            cat_ids[ticker] = (cid, price)

        # ISA: 80% VHVG, 20% VFEG
        isa_val = ACCOUNT_HISTORY["Vanguard S&S ISA"][-1]
        vhvg_cid, vhvg_price = cat_ids["VHVG"]
        vfeg_cid, vfeg_price = cat_ids["VFEG"]
        vhvg_val = round(isa_val * 0.80, 2)
        vfeg_val = round(isa_val * 0.20, 2)
        add_holding({"account_id": isa_id, "holding_catalogue_id": vhvg_cid, "holding_name": "Vanguard FTSE Developed World ETF", "ticker": "VHVG", "asset_type": "ETF", "bucket": "Equities", "value": vhvg_val, "units": round(vhvg_val / vhvg_price, 4), "price": vhvg_price, "notes": ""}, uid)
        add_holding({"account_id": isa_id, "holding_catalogue_id": vfeg_cid, "holding_name": "Vanguard FTSE Emerging Markets ETF", "ticker": "VFEG", "asset_type": "ETF", "bucket": "Equities", "value": vfeg_val, "units": round(vfeg_val / vfeg_price, 4), "price": vfeg_price, "notes": ""}, uid)

        # LISA: 100% VWRP
        lisa_val = ACCOUNT_HISTORY["Moneybox LISA"][-1]
        vwrp_cid, vwrp_price = cat_ids["VWRP"]
        add_holding({"account_id": lisa_id, "holding_catalogue_id": vwrp_cid, "holding_name": "Vanguard FTSE All-World ETF", "ticker": "VWRP", "asset_type": "ETF", "bucket": "Equities", "value": lisa_val, "units": round(lisa_val / vwrp_price, 4), "price": vwrp_price, "notes": ""}, uid)

        # SIPP: 80% VHVG, 20% VFEG
        sipp_val = ACCOUNT_HISTORY["Vanguard SIPP"][-1]
        vhvg_sipp_val = round(sipp_val * 0.80, 2)
        vfeg_sipp_val = round(sipp_val * 0.20, 2)
        add_holding({"account_id": sipp_id, "holding_catalogue_id": vhvg_cid, "holding_name": "Vanguard FTSE Developed World ETF", "ticker": "VHVG", "asset_type": "ETF", "bucket": "Equities", "value": vhvg_sipp_val, "units": round(vhvg_sipp_val / vhvg_price, 4), "price": vhvg_price, "notes": ""}, uid)
        add_holding({"account_id": sipp_id, "holding_catalogue_id": vfeg_cid, "holding_name": "Vanguard FTSE Emerging Markets ETF", "ticker": "VFEG", "asset_type": "ETF", "bucket": "Equities", "value": vfeg_sipp_val, "units": round(vfeg_sipp_val / vfeg_price, 4), "price": vfeg_price, "notes": ""}, uid)

        print("  ✓ Holdings")

        # ── Goals ─────────────────────────────────────────────────────────────
        create_goal({
            "name": "Retirement Fund",
            "target_value": 800000,
            "goal_type": "retirement",
            "selected_tags": "Retirement",
            "notes": "Target £800k invested by age 60.",
        }, uid)
        create_goal({
            "name": "Emergency Fund",
            "target_value": 6000,
            "goal_type": "savings",
            "selected_tags": "Emergency Fund",
            "notes": "3 months of living expenses.",
        }, uid)
        create_goal({
            "name": "Home deposit",
            "target_value": 60000,
            "goal_type": "savings",
            "selected_tags": "Home deposit",
            "notes": "Aiming for a 10% deposit on a modest place. Demo data only.",
        }, uid)
        create_goal({
            "name": "Long-term goal",
            "target_value": 20000,
            "goal_type": "savings",
            "selected_tags": "Long-term",
            "notes": "A flexible long-term pot (renovations / career break). Demo data only.",
        }, uid)
        print("  ✓ Goals")

        # ── Budget sections + items ───────────────────────────────────────────
        # fetch_budget_sections auto-creates the 5 default sections
        fetch_budget_sections(uid)

        budget_items = [
            # (name, section, default_amount, sort_order)
            ("Salary",                   "income",        3600,  0),
            ("Freelance",                "income",         250,  1),
            ("Rent",                     "fixed",         1100,  0),
            ("Council Tax",              "fixed",          110,  1),
            ("Utilities (Gas/Electric)", "fixed",           85,  2),
            ("Internet",                 "fixed",           35,  3),
            ("Phone",                    "fixed",           25,  4),
            ("Gym",                      "fixed",           45,  5),
            ("Subscriptions",            "fixed",           30,  6),
            ("Student Loan",             "debt",           150,  0),
            ("S&S ISA (Vanguard)",       "investment",     500,  0),
            ("LISA (Moneybox)",          "investment",     333,  1),
            ("SIPP (Vanguard)",          "investment",     400,  2),
            ("Workplace Pension",        "investment",     230,  3),
            ("Groceries",               "discretionary",   250,  0),
            ("Eating Out",              "discretionary",   120,  1),
            ("Transport",               "discretionary",    80,  2),
            ("Clothing",                "discretionary",    50,  3),
            ("Entertainment",           "discretionary",    60,  4),
            ("Miscellaneous",           "discretionary",    75,  5),
        ]
        item_ids = {}
        for name, section, amount, order in budget_items:
            iid = create_budget_item({"name": name, "section": section, "default_amount": amount, "sort_order": order}, uid)
            item_ids[name] = iid
        print(f"  ✓ Budget items ({len(item_ids)} items)")

        # Budget entries for a few months (slight variations from defaults)
        entry_overrides = {
            "2025-10": {"Freelance": 0, "Eating Out": 95, "Clothing": 120, "Miscellaneous": 90},
            "2025-11": {"Freelance": 350, "Eating Out": 180, "Subscriptions": 55, "Miscellaneous": 60},
            "2025-12": {"Freelance": 0, "Eating Out": 250, "Entertainment": 150, "Miscellaneous": 200, "Clothing": 180},
            "2026-01": {"Freelance": 400, "Eating Out": 80, "Miscellaneous": 50},
            "2026-02": {"Freelance": 250, "Eating Out": 110, "Miscellaneous": 70},
            "2026-03": {"Freelance": 300, "Eating Out": 130, "Miscellaneous": 65},
        }
        for month_key, overrides in entry_overrides.items():
            for item_name, amount in overrides.items():
                if item_name in item_ids:
                    upsert_budget_entry(month_key, item_ids[item_name], amount, uid)
        print("  ✓ Budget entries")

        # ── Monthly snapshots + reviews ───────────────────────────────────────
        account_name_to_id = {name: aid for name, aid in account_ids.items()}

        for i, month_key in enumerate(MONTHS):
            # Snapshot every account for this month
            for acc_name, history in ACCOUNT_HISTORY.items():
                acc_id = account_name_to_id[acc_name]
                upsert_monthly_snapshot(acc_id, month_key, history[i])

            # Create and complete the monthly review
            review = fetch_or_create_monthly_review(month_key, uid)
            ensure_monthly_review_items(review["id"], uid)
            items = fetch_monthly_review_items(review["id"])

            for item in items:
                acc_name = item["account_name"]
                is_holdings = item["valuation_mode"] == "holdings"
                is_manual = item["valuation_mode"] == "manual"
                expected = CONTRIBUTIONS.get(acc_name, 0)
                update_monthly_review_item({
                    "id": item["id"],
                    "expected_contribution": expected,
                    "contribution_confirmed": 1 if expected > 0 else 0,
                    "holdings_updated": 1 if is_holdings else 0,
                    "balance_updated": 1 if is_manual else 0,
                    "notes": "",
                })

            # Mark all as complete except the current month (leave in_progress)
            if month_key == MONTHS[-1]:
                update_monthly_review(review["id"], "in_progress", "", uid)
            else:
                update_monthly_review(review["id"], "complete",
                                      _review_notes(month_key), uid)

        print(f"  ✓ Monthly reviews ({len(MONTHS)} months, last left in_progress)")

        # ── ISA contributions (for allowance tracker) ─────────────────────────
        # Tax year 2025-26: ISA £500/month, LISA £333/month, Cash ISA £100/month
        for m, y in [(10, 2025), (11, 2025), (12, 2025), (1, 2026), (2, 2026), (3, 2026)]:
            d = f"{y}-{m:02d}-25"
            add_isa_contribution(uid, isa_id, 500, d)
            add_isa_contribution(uid, lisa_id, 333, f"{y}-{m:02d}-01")
            add_pension_contribution(uid, sipp_id, 400, "personal", d)
        add_isa_contribution(uid, cash_isa_id, 100, "2025-10-01", "Opening contribution")
        add_isa_contribution(uid, cash_isa_id, 100, "2025-11-01")
        add_isa_contribution(uid, cash_isa_id, 100, "2025-12-01")
        print("  ✓ ISA + pension contributions")

        # ── Portfolio daily snapshots (last 90 days) ──────────────────────────
        _seed_daily_snapshots(uid, account_ids)
        print("  ✓ Daily snapshots (last 90 days)")

        print("\nDone! Log in as 'demo' to see the seeded data.")


def _review_notes(month_key):
    notes = {
        "2025-10": "Good month. Markets up, stayed the course.",
        "2025-11": "Picked up some extra freelance work. Boosted savings rate.",
        "2025-12": "Christmas spending spike but investments still contributed.",
        "2026-01": "Fresh start. Increased SIPP contribution from this month.",
        "2026-02": "Quiet month. Everything on track.",
        "2026-03": "Markets dipped slightly but long-term plan unchanged.",
    }
    return notes.get(month_key, "")


def _seed_daily_snapshots(uid, account_ids):
    """Write 90 days of daily portfolio + account snapshots with gentle drift."""
    import math, random
    random.seed(42)  # reproducible

    today = date.today()
    start = today - timedelta(days=89)

    # April 2026 ending values
    end_values = {name: ACCOUNT_HISTORY[name][-1] for name in ACCOUNT_HISTORY}
    # March 2026 starting values
    start_values = {name: ACCOUNT_HISTORY[name][-2] for name in ACCOUNT_HISTORY}

    days = [(start + timedelta(days=d)) for d in range(90)]
    n = len(days)

    with get_connection() as conn:
        for i, d in enumerate(days):
            day_str = d.isoformat()
            t = i / (n - 1)  # 0.0 → 1.0
            total = 0.0
            for acc_name, acc_id in account_ids.items():
                sv = start_values[acc_name]
                ev = end_values[acc_name]
                # Linear interpolation + small daily noise
                base = sv + (ev - sv) * t
                noise = base * random.uniform(-0.003, 0.003)
                val = round(max(base + noise, 0), 2)
                total += val
                conn.execute(
                    "INSERT OR REPLACE INTO account_daily_snapshots (user_id, account_id, snapshot_date, value) VALUES (?, ?, ?, ?)",
                    (uid, acc_id, day_str, val),
                )
            conn.execute(
                "INSERT OR REPLACE INTO portfolio_daily_snapshots (user_id, snapshot_date, total_value) VALUES (?, ?, ?)",
                (uid, day_str, round(total, 2)),
            )
        conn.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed demo account with realistic data")
    parser.add_argument("--username", default="demo", help="Demo username (default: demo)")
    parser.add_argument("--password", default="demo123", help="Password to use if creating the demo user")
    parser.add_argument(
        "--create-user",
        action="store_true",
        help="Create the user if missing (useful for local/demo screenshots)",
    )
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        init_db()
        user = get_user_by_username(args.username)
        if user is None:
            if not args.create_user:
                print(f"No user '{args.username}' found. Create the account first via the web UI, or pass --create-user.")
                sys.exit(1)
            create_user(args.username, args.password, is_admin=False)
            user = get_user_by_username(args.username)
        if user is None:
            print(f"Failed to create user '{args.username}'.")
            sys.exit(1)

    seed(args.username)
