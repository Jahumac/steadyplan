"""The House page — "will I have enough by the date I need it?"

Before this page the app could only answer "when will I get there?". A house purchase
asks the inverse question, and it needs two things the schema did not have: a target
date on the goal, and a projection measured *at* that date rather than at the target.
"""
from datetime import date

import pytest

from app.routes.house import build_house_plan, find_house_goal, months_between


# ── months_between ──────────────────────────────────────────────────────────

def test_months_between_counts_whole_months():
    assert months_between(date(2026, 11, 1), date(2029, 5, 1)) == 30


def test_months_between_rounds_a_part_month_up():
    """The deposit is needed somewhere inside May, so May counts."""
    assert months_between(date(2026, 11, 1), date(2029, 5, 15)) == 31


def test_months_between_never_goes_negative():
    assert months_between(date(2029, 5, 1), date(2026, 11, 1)) == 0


# ── find_house_goal ─────────────────────────────────────────────────────────

def _goal(name="House", tags="House", target=33000.0, target_date=None, gid=1):
    return {"id": gid, "name": name, "selected_tags": tags,
            "target_value": target, "target_date": target_date}


def test_find_house_goal_prefers_the_tag_over_the_name():
    """Tags decide which accounts fund the goal, so they win over a name match."""
    by_name = _goal(name="House deposit", tags="Long-Term", gid=1)
    by_tag = _goal(name="Property", tags="House", gid=2)
    assert find_house_goal([by_name, by_tag])["id"] == 2


def test_find_house_goal_falls_back_to_a_name_match():
    assert find_house_goal([_goal(name="House", tags="Cash", gid=7)])["id"] == 7


def test_find_house_goal_returns_none_when_there_is_no_house_goal():
    assert find_house_goal([_goal(name="Retirement", tags="Retirement")]) is None


# ── build_house_plan ────────────────────────────────────────────────────────

ASSUMPTIONS = {
    "date_of_birth": "1982-11-24", "current_age": 43, "retirement_age": 60,
    "annual_growth_rate": 0.07, "salary_day": 28,
}


def _account(value, tags="House", monthly=0.0, inflows=None):
    return {
        "id": 1, "name": "My Lifetime ISA", "wrapper_type": "Lifetime ISA",
        "category": "Investment", "tags": tags, "current_value": value,
        "monthly_contribution": monthly, "monthly_cash_park": 0,
        "valuation_mode": "manual", "growth_mode": "custom",
        "growth_rate_override": 0.038, "uninvested_cash": 0.0,
        "cash_interest_rate": 0.038, "annual_fee_pct": 0,
        "platform_fee_pct": 0, "fund_fee_pct": 0, "contribution_fee_pct": 0,
        "_one_off_inflows": inflows or [],
    }


TODAY = date(2026, 11, 1)


def test_no_goal_means_no_plan():
    assert build_house_plan(None, [], {}, ASSUMPTIONS, today=TODAY)["state"] == "no_goal"


def test_target_met_is_reported_as_reached():
    plan = build_house_plan(_goal(target=4000.0), [_account(5000.0)], {}, ASSUMPTIONS, today=TODAY)
    assert plan["status"] == "reached"


def test_missing_date_says_it_cannot_judge():
    plan = build_house_plan(_goal(target=33000.0), [_account(4282.0)], {}, ASSUMPTIONS, today=TODAY)
    assert plan["status"] == "no_date"
    assert plan["current"] == 4282.0


def test_on_track_when_the_projection_clears_the_target():
    """£12k now, £400/mo, ~30 months -> well past a £20k target."""
    plan = build_house_plan(
        _goal(target=20000.0, target_date="2029-05-01"),
        [_account(12000.0, monthly=400.0)], {}, ASSUMPTIONS, today=TODAY,
    )
    assert plan["status"] == "on_track"
    assert plan["projected"] > 20000
    assert plan["gap"] < 0


def test_short_reports_the_gap_and_the_monthly_top_up_needed():
    plan = build_house_plan(
        _goal(target=50000.0, target_date="2029-05-01"),
        [_account(4282.0)], {}, ASSUMPTIONS, today=TODAY,
    )
    assert plan["status"] == "short"
    assert plan["projected"] < 50000
    assert plan["gap"] == pytest.approx(50000 - plan["projected"])
    # £X over 31 months is a coherent per-month figure
    assert plan["per_month_needed"] == pytest.approx(plan["gap"] / plan["months"])


def test_a_past_date_is_flagged_rather_than_projected():
    plan = build_house_plan(
        _goal(target=33000.0, target_date="2026-01-01"),
        [_account(4282.0)], {}, ASSUMPTIONS, today=TODAY,
    )
    assert plan["status"] == "past_due"
    assert plan["gap"] == 33000 - 4282.0


def test_lump_sum_targets_are_reachable_when_monthly_is_zero():
    """The house case: no monthly contribution, funded by dated top-ups."""
    inflows = [
        {"month_key": "2027-04", "amount": 4000.0, "kind": "contribution"},
        {"month_key": "2027-06", "amount": 1000.0, "kind": "bonus"},
    ]
    plan = build_house_plan(
        _goal(target=9000.0, target_date="2027-12-01"),
        [_account(4282.0, inflows=inflows)], {}, ASSUMPTIONS, today=TODAY,
    )
    assert plan["monthly"] == 0
    assert plan["status"] == "on_track", "lump sums must count towards being on track"


# ── route + persistence ─────────────────────────────────────────────────────

def test_house_page_requires_login(app, client, make_user):
    # A user must exist, otherwise the app redirects to first-run /setup instead.
    make_user(username="houselogin", password="password123")
    resp = client.get("/house/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_house_page_renders_an_empty_state_without_a_goal(auth_client):
    resp = auth_client.get("/house/")
    assert resp.status_code == 200
    assert b"Not set up yet" in resp.data


def test_goal_target_date_is_stored_and_read_back(app, make_user):
    from app.models import create_goal, fetch_all_goals

    uid, _, _ = make_user(username="housedate", password="password123")
    with app.app_context():
        create_goal({"name": "House", "target_value": 33000.0,
                     "goal_type": "Tagged Goal", "selected_tags": "House",
                     "notes": "", "target_date": "2029-05-01"}, uid)
        goal = [g for g in fetch_all_goals(uid) if g["name"] == "House"][0]
    assert goal["target_date"] == "2029-05-01"


def test_blank_target_date_is_stored_as_null(app, make_user):
    from app.models import create_goal, fetch_all_goals

    uid, _, _ = make_user(username="housedate2", password="password123")
    with app.app_context():
        create_goal({"name": "House", "target_value": 1.0, "goal_type": "Tagged Goal",
                     "selected_tags": "", "notes": "", "target_date": ""}, uid)
        goal = [g for g in fetch_all_goals(uid) if g["name"] == "House"][0]
    assert goal["target_date"] is None


def test_house_page_is_in_the_navigation(auth_client):
    """A screen nobody can reach is the exact problem this page was built to fix."""
    resp = auth_client.get("/goals/")
    assert resp.status_code == 200
    assert b'href="/house/"' in resp.data


# ── household ───────────────────────────────────────────────────────────────

def test_a_solo_user_has_a_household_of_one(app, make_user):
    from app.models import fetch_household_members

    uid, uname, _ = make_user(username="solo", password="password123")
    with app.app_context():
        members = fetch_household_members(uid)
    assert [m["username"] for m in members] == [uname]


def test_linking_adds_both_sides(app, make_user):
    from app.models import fetch_household_members, link_household_member

    a, aname, _ = make_user(username="partner-a", password="password123")
    b, bname, _ = make_user(username="partner-b", password="password123")
    with app.app_context():
        ok, msg = link_household_member(a, bname)
        assert ok, msg
        assert {m["username"] for m in fetch_household_members(a)} == {aname, bname}
        # the link is symmetric — b sees a too
        assert {m["username"] for m in fetch_household_members(b)} == {aname, bname}


def test_linking_an_unknown_username_is_refused(app, make_user):
    from app.models import link_household_member

    uid, _, _ = make_user(username="partner-c", password="password123")
    with app.app_context():
        ok, msg = link_household_member(uid, "nobody-here")
    assert not ok
    assert "No user called" in msg


def test_you_cannot_link_yourself(app, make_user):
    from app.models import link_household_member

    uid, uname, _ = make_user(username="partner-d", password="password123")
    with app.app_context():
        ok, _ = link_household_member(uid, uname)
    assert not ok


def test_two_existing_households_are_not_merged(app, make_user):
    """Merging silently would expose one group's accounts to another."""
    from app.models import link_household_member

    a, aname, _ = make_user(username="hh-a", password="password123")
    b, bname, _ = make_user(username="hh-b", password="password123")
    c, cname, _ = make_user(username="hh-c", password="password123")
    d, dname, _ = make_user(username="hh-d", password="password123")
    with app.app_context():
        assert link_household_member(a, bname)[0]      # household 1: a + b
        assert link_household_member(c, dname)[0]      # household 2: c + d
        ok, msg = link_household_member(c, aname)      # try to merge them
    assert not ok
    assert "different household" in msg


def test_a_solo_user_may_join_an_existing_household(app, make_user):
    """Joining is not merging: the solo user has nothing to expose."""
    from app.models import fetch_household_members, link_household_member

    a, aname, _ = make_user(username="hh-f", password="password123")
    b, bname, _ = make_user(username="hh-g", password="password123")
    c, cname, _ = make_user(username="hh-h", password="password123")
    with app.app_context():
        assert link_household_member(a, bname)[0]
        ok, msg = link_household_member(c, aname)
        assert ok, msg
        assert {m["username"] for m in fetch_household_members(c)} == {aname, bname, cname}


def test_unlinking_the_second_member_clears_the_household(app, make_user):
    from app.models import (
        fetch_household_members, link_household_member, unlink_household_member,
    )

    a, aname, _ = make_user(username="hh-d", password="password123")
    b, bname, _ = make_user(username="hh-e", password="password123")
    with app.app_context():
        link_household_member(a, bname)
        ok, msg = unlink_household_member(a, b)
        assert ok, msg
        assert [m["username"] for m in fetch_household_members(a)] == [aname]
        assert [m["username"] for m in fetch_household_members(b)] == [bname]


def test_house_page_sums_accounts_across_the_household(app, client, make_user):
    """The whole point: one joint number, not two halves added up by hand."""
    from app.models import (
        create_account, create_goal, fetch_assumptions, link_household_member, update_assumptions,
    )

    a, aname, pw = make_user(username="joint-a", password="password123")
    b, bname, _ = make_user(username="joint-b", password="password123")

    def mk(name, value):
        return {"id": None, "name": name, "provider": "P", "wrapper_type": "Lifetime ISA",
                "category": "Investment", "tags": "House", "current_value": value,
                "monthly_contribution": 0, "monthly_cash_park": 0, "pension_contribution_day": 0,
                "goal_value": None, "valuation_mode": "manual", "growth_mode": "custom",
                "growth_rate_override": 0.038, "owner": "", "is_active": 1, "notes": "",
                "last_updated": "2026-11-01", "employer_contribution": 0,
                "contribution_method": "standard", "annual_fee_pct": 0, "platform_fee_pct": 0,
                "platform_fee_flat": 0, "platform_fee_cap": 0, "fund_fee_pct": 0,
                "contribution_fee_pct": 0, "uninvested_cash": 0, "cash_interest_rate": 0.038,
                "interest_payment_day": 0}

    with app.app_context():
        for uid in (a, b):
            s = dict(fetch_assumptions(uid))
            s.update({"annual_growth_rate": 0.07, "salary_day": 28, "current_age": 43,
                      "date_of_birth": "1982-11-24", "retirement_age": 60})
            update_assumptions(s, uid)
        create_account(mk("A LISA", 4000.0), a)
        create_account(mk("B LISA", 1000.0), b)
        create_goal({"name": "House", "target_value": 25000.0, "goal_type": "Tagged Goal",
                     "selected_tags": "House", "notes": "", "target_date": "2029-05-01"}, a)
        link_household_member(a, bname)

    client.post("/login", data={"username": aname, "password": pw})
    html = client.get("/house/").get_data(as_text=True)
    assert "£5,000" in html, "joint total must include the other member's account"
    assert bname in html


def test_an_unlinked_users_accounts_do_not_leak(app, client, make_user):
    from app.models import create_account, create_goal, fetch_assumptions, update_assumptions

    a, aname, pw = make_user(username="leak-a", password="password123")
    b, bname, _ = make_user(username="leak-b", password="password123")

    def mk(name, value):
        return {"id": None, "name": name, "provider": "P", "wrapper_type": "Lifetime ISA",
                "category": "Investment", "tags": "House", "current_value": value,
                "monthly_contribution": 0, "monthly_cash_park": 0, "pension_contribution_day": 0,
                "goal_value": None, "valuation_mode": "manual", "growth_mode": "custom",
                "growth_rate_override": 0.038, "owner": "", "is_active": 1, "notes": "",
                "last_updated": "2026-11-01", "employer_contribution": 0,
                "contribution_method": "standard", "annual_fee_pct": 0, "platform_fee_pct": 0,
                "platform_fee_flat": 0, "platform_fee_cap": 0, "fund_fee_pct": 0,
                "contribution_fee_pct": 0, "uninvested_cash": 0, "cash_interest_rate": 0.038,
                "interest_payment_day": 0}

    with app.app_context():
        for uid in (a, b):
            s = dict(fetch_assumptions(uid))
            s.update({"annual_growth_rate": 0.07, "salary_day": 28, "current_age": 43,
                      "date_of_birth": "1982-11-24", "retirement_age": 60})
            update_assumptions(s, uid)
        create_account(mk("A LISA", 4000.0), a)
        create_account(mk("B LISA", 9999.0), b)
        create_goal({"name": "House", "target_value": 25000.0, "goal_type": "Tagged Goal",
                     "selected_tags": "House", "notes": "", "target_date": "2029-05-01"}, a)

    client.post("/login", data={"username": aname, "password": pw})
    html = client.get("/house/").get_data(as_text=True)
    assert "£9,999" not in html
    assert "£4,000" in html
