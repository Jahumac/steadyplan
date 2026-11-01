from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required

from app.utils import valid_date, valid_tax_year
from app.calculations import (
    allowance_progress,
    apply_pension_carry_forward,
    calculate_isa_usage,
    calculate_pension_usage,
    current_age_from_assumptions,
    is_pension_account,
    pension_allowance_limits,
    uk_tax_year_label,
    uk_tax_year_start,
    uk_tax_year_end,
    ISA_WRAPPER_TYPES,
    LISA_ANNUAL_CAP,
    LISA_WRAPPER_TYPES,
    lisa_bonus_arrival_month,
    lisa_bonus_by_contribution,
)
from app.models import (
    add_isa_contribution,
    set_isa_bonus_received,
    delete_isa_contribution,
    delete_pension_carry_forward,
    fetch_all_accounts,
    fetch_account,
    fetch_assumptions,
    fetch_isa_contributions,
    fetch_isa_allowance_cash_flow_events,
    fetch_isa_overrides_for_tax_year,
    fetch_pension_overrides_for_tax_year,
    fetch_pension_carry_forward,
    fetch_tax_year_contributions,
    fetch_completed_tax_year_contributions,
    upsert_pension_carry_forward,
)


allowance_bp = Blueprint("allowance", __name__)


def _isa_usage_for_now(uid):
    """Current tax-year ISA/LISA usage.

    Shared by the overview render and the lump-sum guard so the figure the page
    shows and the figure the guard enforces cannot drift apart.
    """
    now_date = datetime.now().date()
    accounts = fetch_all_accounts(uid)
    assumptions = fetch_assumptions(uid)

    try:
        salary_day = int(assumptions["salary_day"]) if assumptions and assumptions["salary_day"] else 0
    except (KeyError, TypeError):
        salary_day = 0

    ty_start_date = uk_tax_year_start(now_date)
    ty_end_date = uk_tax_year_end(now_date)
    ty_start = ty_start_date.isoformat()
    ty_end = ty_end_date.isoformat()

    current_age = current_age_from_assumptions(assumptions) if assumptions else 0
    usage = calculate_isa_usage(
        accounts,
        fetch_isa_contributions(uid, ty_start, ty_end),
        now_date,
        salary_day,
        isa_overrides=fetch_isa_overrides_for_tax_year(uid, ty_start, ty_end),
        review_contributions=fetch_completed_tax_year_contributions(
            uid,
            ty_start_date.strftime("%Y-%m"),
            ty_end_date.strftime("%Y-%m"),
        ),
        allowance_events=fetch_isa_allowance_cash_flow_events(uid, ty_start, ty_end),
        lisa_contributions_allowed=(not current_age or current_age < 50),
    )
    return usage, current_age


@allowance_bp.route("/")
@login_required
def allowance_overview():
    uid = current_user.id
    now_date = datetime.now().date()
    accounts = fetch_all_accounts(uid)
    assumptions = fetch_assumptions(uid)

    try:
        salary_day = int(assumptions["salary_day"]) if assumptions and assumptions["salary_day"] else 0
    except (KeyError, TypeError):
        salary_day = 0
    ty_start_date = uk_tax_year_start(now_date)
    ty_end_date = uk_tax_year_end(now_date)
    ty_start = ty_start_date.isoformat()
    ty_end = ty_end_date.isoformat()
    ad_hoc = fetch_isa_contributions(uid, ty_start, ty_end)
    allowance_events = fetch_isa_allowance_cash_flow_events(uid, ty_start, ty_end)
    isa_overrides = fetch_isa_overrides_for_tax_year(uid, ty_start, ty_end)
    review_contribs = fetch_completed_tax_year_contributions(
        uid,
        ty_start_date.strftime("%Y-%m"),
        ty_end_date.strftime("%Y-%m"),
    )
    # LISA age warning — contributions stop at 50; warn at 49+
    current_age = current_age_from_assumptions(assumptions) if assumptions else 0
    usage = calculate_isa_usage(
        accounts, ad_hoc, now_date, salary_day,
        isa_overrides=isa_overrides,
        review_contributions=review_contribs,
        allowance_events=allowance_events,
        lisa_contributions_allowed=(not current_age or current_age < 50),
    )

    cash_flow_used_room = 0.0
    cash_flow_restored_room = 0.0
    cash_flow_used_count = 0
    cash_flow_restored_count = 0
    for event in allowance_events:
        effect = str(event.get("allowance_effect") or "none").strip().lower()
        raw_amount = abs(float(event.get("amount") or 0.0))
        if effect in {"subscription", "flexible_replacement"}:
            cash_flow_used_room += raw_amount
            cash_flow_used_count += 1
        elif effect == "flexible_withdrawal":
            cash_flow_restored_room += raw_amount
            cash_flow_restored_count += 1

    allowance_truth_checkpoint = {
        "monthly_total": float(usage.get("monthly_isa") or 0.0),
        "topups_total": float(usage.get("adhoc_isa") or 0.0),
        "adjustments_total": float(usage.get("allowance_adjustment_isa") or 0.0),
        "net_total": float(usage.get("isa_used") or 0.0),
        "cash_flow_used_room": cash_flow_used_room,
        "cash_flow_restored_room": cash_flow_restored_room,
        "cash_flow_used_count": cash_flow_used_count,
        "cash_flow_restored_count": cash_flow_restored_count,
    }

    isa_allowance = float(assumptions["isa_allowance"]) if assumptions else 20000
    lisa_allowance = float(assumptions["lisa_allowance"]) if assumptions else 4000

    has_lisa = any("Lifetime" in (a.get("wrapper_type") or "") or "LISA" in (a.get("wrapper_type") or "") for a in accounts)

    lisa_age_warning = current_age >= 49 if current_age else False
    lisa_months_remaining = max(0, round((50 - current_age) * 12)) if lisa_age_warning else 0

    # ISA accounts for the dropdown
    isa_accounts = [a for a in accounts if (a["wrapper_type"] or "") in ISA_WRAPPER_TYPES]

    pension_overrides = fetch_pension_overrides_for_tax_year(uid, ty_start, ty_end)
    pension_review_contribs = fetch_completed_tax_year_contributions(
        uid,
        ty_start_date.strftime("%Y-%m"),
        ty_end_date.strftime("%Y-%m"),
    )
    pension_usage = calculate_pension_usage(
        accounts,
        assumptions,
        now_date,
        salary_day,
        pension_overrides=pension_overrides,
        review_contributions=pension_review_contribs,
    )
    pension_limits = pension_allowance_limits(dict(assumptions) if assumptions else {})
    pension_accounts = [a for a in accounts if is_pension_account(dict(a))]

    carry_forward_entries = fetch_pension_carry_forward(uid)
    pension_limits_with_carry = apply_pension_carry_forward(
        pension_limits,
        carry_forward_entries,
    )

    taxable_accounts = [a for a in accounts if (a["wrapper_type"] or "") not in ISA_WRAPPER_TYPES and not is_pension_account(dict(a))]

    # ── CGT disposals ────────────────────────────────────────────────────────

    return render_template(
        "allowance.html",
        tax_year=uk_tax_year_label(now_date),
        usage=usage,
        allowance_truth_checkpoint=allowance_truth_checkpoint,
        pension_usage=pension_usage,
        pension_limits=pension_limits_with_carry,
        isa_allowance=isa_allowance,
        lisa_allowance=lisa_allowance,
        isa_progress=allowance_progress(usage["isa_used"], isa_allowance),
        lisa_progress=allowance_progress(usage["lisa_used"], lisa_allowance),
        pension_progress=allowance_progress(pension_usage["pension_used"], pension_limits_with_carry["effective_allowance"]),
        carry_forward_entries=carry_forward_entries,
        contributions=ad_hoc,
        contribution_bonus=lisa_bonus_by_contribution(ad_hoc, usage.get("monthly_lisa", 0.0)),
        contribution_bonus_month={c["id"]: lisa_bonus_arrival_month(c["contribution_date"]) for c in ad_hoc},
        isa_accounts=isa_accounts,
        pension_accounts=pension_accounts,
        taxable_accounts=taxable_accounts,
        today=now_date.isoformat(),
        current_month=now_date.strftime("%Y-%m"),
        active_page="budget",
        lisa_age_warning=lisa_age_warning,
        lisa_months_remaining=lisa_months_remaining,
        has_lisa=has_lisa,
    )


@allowance_bp.route("/add", methods=["POST"])
@login_required
def add_contribution():
    uid = current_user.id
    account_id = request.form.get("account_id", type=int)
    amount = request.form.get("amount", type=float)
    raw_date = request.form.get("contribution_date")
    contribution_date = valid_date(raw_date) or (None if raw_date else datetime.now().date().isoformat())
    note = request.form.get("note", "").strip() or None

    if not account_id or not amount or amount <= 0:
        flash("Please select an account and enter a valid amount.", "error")
        return redirect(url_for("allowance.allowance_overview"))

    if not contribution_date:
        flash("Please enter a valid date.", "error")
        return redirect(url_for("allowance.allowance_overview"))

    acc = fetch_account(account_id, uid)
    if not acc or (acc.get("wrapper_type") or "") not in ISA_WRAPPER_TYPES:
        flash("Please select one of your ISA accounts.", "error")
        return redirect(url_for("allowance.allowance_overview"))

    # Lifetime ISA has a hard £4,000 annual cap that is separate from (and inside)
    # the overall ISA allowance. Contributing past it is not merely "no bonus" —
    # a provider will reject the excess, so refuse it here with the real numbers.
    if (acc.get("wrapper_type") or "") in LISA_WRAPPER_TYPES:
        usage, current_age = _isa_usage_for_now(uid)

        lisa_used = float(usage.get("lisa_used") or 0.0)
        remaining = max(LISA_ANNUAL_CAP - lisa_used, 0.0)
        if amount > remaining + 0.005:
            flash(
                "Lifetime ISA limit reached: £{:,.2f} of £{:,.0f} already used this tax year, "
                "so only £{:,.2f} is left. £{:,.2f} would exceed the annual limit and the "
                "provider would reject the excess.".format(lisa_used, LISA_ANNUAL_CAP, remaining, amount),
                "error",
            )
            return redirect(url_for("allowance.allowance_overview"))
        if current_age and current_age >= 50:
            flash(
                "You are 50 or over, so no new Lifetime ISA contributions can be made.",
                "error",
            )
            return redirect(url_for("allowance.allowance_overview"))

    add_isa_contribution(uid, account_id, amount, contribution_date, note)
    flash(f"Recorded £{amount:,.2f} top-up.", "success")
    return redirect(url_for("allowance.allowance_overview"))


@allowance_bp.route("/bonus/<int:contribution_id>", methods=["POST"])
@login_required
def toggle_bonus_received(contribution_id):
    """Tick (or untick) that a Lifetime ISA government bonus has arrived."""
    uid = current_user.id
    received = (request.form.get("received") or "").strip() == "1"

    if set_isa_bonus_received(contribution_id, uid, received=received):
        flash("Lifetime ISA bonus marked as received." if received else "Lifetime ISA bonus marked as not received.", "success")
    else:
        flash("That contribution could not be found.", "error")

    return redirect(url_for("allowance.allowance_overview"))


@allowance_bp.route("/delete/<int:contribution_id>", methods=["POST"])
@login_required
def remove_contribution(contribution_id):
    delete_isa_contribution(contribution_id, current_user.id)
    flash("Contribution removed.", "success")
    return redirect(url_for("allowance.allowance_overview"))


@allowance_bp.route("/pension/carry-forward/add", methods=["POST"])
@login_required
def add_carry_forward():
    tax_year = valid_tax_year(request.form.get("tax_year"))
    unused = request.form.get("unused_allowance", type=float)
    if not tax_year or unused is None or unused < 0:
        flash("Please enter a valid tax year (e.g. 2023-24) and unused amount.", "error")
        return redirect(url_for("allowance.allowance_overview") + "#pension")
    upsert_pension_carry_forward(current_user.id, tax_year, unused)
    flash(f"Recorded £{unused:,.0f} carry-forward from {tax_year}.", "success")
    return redirect(url_for("allowance.allowance_overview") + "#pension")


@allowance_bp.route("/pension/carry-forward/delete/<int:entry_id>", methods=["POST"])
@login_required
def remove_carry_forward(entry_id):
    delete_pension_carry_forward(entry_id, current_user.id)
    flash("Carry-forward entry removed.", "success")
    return redirect(url_for("allowance.allowance_overview") + "#pension")
