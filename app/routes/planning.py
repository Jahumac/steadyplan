from flask import Blueprint, render_template, request
from flask_login import current_user, login_required

from app.calculations import effective_account_value, projection_start_month_key
from app.models import (
    fetch_all_accounts,
    fetch_assumptions,
    fetch_contribution_overrides,
    fetch_holding_totals_by_account,
)
from app.services.planning_insights import (
    build_accessible_security_summary,
    build_retirement_income_summary,
)
from app.utils import optional_float

planning_bp = Blueprint("planning", __name__)


def _float_arg(name, default=0.0):
    return optional_float(request.args.get(name), default=default)


@planning_bp.route("/")
@login_required
def planning():
    uid = current_user.id
    assumptions = fetch_assumptions(uid)
    raw_accounts = fetch_all_accounts(uid)
    holdings_totals = fetch_holding_totals_by_account(uid)
    start_month = projection_start_month_key(assumptions)

    accounts = []
    for account in raw_accounts:
        row = dict(account)
        row["current_value"] = effective_account_value(account, holdings_totals)
        row["_contribution_overrides"] = fetch_contribution_overrides(account["id"])
        row["_projection_start_month"] = start_month
        accounts.append(row)

    access_summary = build_accessible_security_summary(accounts, assumptions)
    income_summary = build_retirement_income_summary(
        access_summary,
        assumptions,
        desired_income=_float_arg("desired_income", 0.0),
        state_pension_annual=_float_arg("state_pension_annual", 12000.0),
        pension_access_age=_float_arg("pension_access_age", 58.0),
        state_pension_age=_float_arg("state_pension_age", 68.0),
    )

    return render_template(
        "planning.html",
        access_summary=access_summary,
        income_summary=income_summary,
        assumptions=assumptions,
        active_page="planning",
    )
