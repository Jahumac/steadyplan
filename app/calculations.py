from calendar import monthrange
from datetime import date, datetime, timedelta, timezone

PRICE_STALE_AFTER_HOURS = 36     # >36h since last successful fetch ⇒ stale badge on holdings
SCHEDULER_STALE_AFTER_HOURS = 24  # >24h since last scheduler run ⇒ alert on overview


def is_price_stale(price_updated_at, now=None):
    """Return True if the stored price is older than PRICE_STALE_AFTER_HOURS.

    Clients should render a warning badge; the price itself is still the
    last known good value (not blanked out).
    """
    if not price_updated_at:
        return True
    now = now or datetime.now(timezone.utc)
    for fmt in ("%Y-%m-%d %H:%M UTC", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            ts = datetime.strptime(price_updated_at, fmt)
            ts = ts.replace(tzinfo=timezone.utc)
            return (now - ts) > timedelta(hours=PRICE_STALE_AFTER_HOURS)
        except (ValueError, TypeError):
            continue
    return True  # unparseable ⇒ assume stale so users notice



def age_from_dob(dob_str, today=None):
    if not dob_str:
        return 0.0
    today = today or date.today()
    try:
        dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return 0.0
    age_years = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        age_years -= 1
    months_since_birthday = (today.month - dob.month) % 12
    if today.day < dob.day:
        months_since_birthday = max(months_since_birthday - 1, 0)
    return age_years + months_since_birthday / 12.0


def current_age_from_assumptions(assumptions):
    """Get the user's current age, preferring date_of_birth over legacy current_age."""
    if not assumptions:
        return 0.0
    dob = _safe_get(assumptions, "date_of_birth")
    if dob:
        return age_from_dob(dob)
    # Legacy fallback
    return to_float(_safe_get(assumptions, "current_age", 0))


TAX_BAND_RATES = {"basic": 0.20, "higher": 0.40, "additional": 0.45}
LISA_ANNUAL_CAP = 4000  # Max personal contribution per tax year
LISA_BONUS_RATE = 0.25


def contribution_breakdown(account, assumptions=None):
    """Calculate the full contribution breakdown for an account.

    Returns a dict:
        personal        — what you pay each month (from your bank / salary)
        tax_relief      — basic-rate relief added by provider (SIPP / relief-at-source pension)
        government_bonus— LISA 25% bonus
        employer        — employer contribution (workplace pension)
        total_into_pot  — the amount actually going into the account each month
        self_assessment — additional relief reclaimable by higher/additional-rate taxpayers
        method_label    — human-readable description of the method
    """
    personal = to_float(_safe_get(account, "monthly_contribution", 0))
    employer = to_float(_safe_get(account, "employer_contribution", 0))
    wrapper = (_safe_get(account, "wrapper_type") or "")
    method = (_safe_get(account, "contribution_method") or "standard")

    tax_band = "basic"
    if assumptions:
        tax_band = (_safe_get(assumptions, "tax_band") or "basic")

    tax_relief = 0.0
    government_bonus = 0.0
    self_assessment = 0.0
    method_label = ""

    is_sipp = "SIPP" in wrapper
    is_workplace = "Workplace" in wrapper or "workplace" in wrapper
    is_lisa = "Lifetime" in wrapper or "LISA" in wrapper
    is_pension = is_sipp or is_workplace

    if is_sipp:
        # SIPP: always relief at source. You pay net, provider claims basic rate.
        # Gross = personal / 0.80 = personal * 1.25
        tax_relief = personal * 0.25  # 25% of your net payment
        method_label = "Relief at source"
        # Higher/additional-rate taxpayers can reclaim the difference via self-assessment
        band_rate = TAX_BAND_RATES.get(tax_band, 0.20)
        if band_rate > 0.20:
            gross = personal + tax_relief  # what's in the pension
            self_assessment = gross * (band_rate - 0.20)  # goes to YOU, not the pension

    elif is_workplace:
        if method == "salary_sacrifice":
            # Salary sacrifice: contributions are pre-tax, no relief needed
            # personal = your gross contribution, employer = their contribution
            tax_relief = 0
            method_label = "Salary sacrifice"
        else:
            # Relief at source (NEST-style): you pay net, provider claims 20%
            tax_relief = personal * 0.25
            method_label = "Relief at source"
            band_rate = TAX_BAND_RATES.get(tax_band, 0.20)
            if band_rate > 0.20:
                gross = personal + tax_relief
                self_assessment = gross * (band_rate - 0.20)

    elif is_lisa:
        if current_age_from_assumptions(assumptions) >= 50:
            # Lifetime ISA contributions and government bonuses stop from age 50.
            personal = 0.0
            government_bonus = 0.0
            method_label = "Lifetime ISA contributions stop at age 50"
        else:
            # 25% government bonus, capped at £4,000/year personal contributions
            annual_personal = personal * 12
            eligible = min(annual_personal, LISA_ANNUAL_CAP)
            government_bonus = (eligible * LISA_BONUS_RATE) / 12  # monthly equivalent
            method_label = "Lifetime ISA bonus (25%)"

    gross_into_pot = personal + tax_relief + government_bonus + employer

    # Contribution fee (e.g. Nest's 1.8%) — taken from each contribution before it's invested
    contribution_fee_pct = to_float(_safe_get(account, "contribution_fee_pct", 0))
    contribution_fee = gross_into_pot * (contribution_fee_pct / 100.0)
    total_into_pot = gross_into_pot - contribution_fee

    return {
        "personal": personal,
        "tax_relief": tax_relief,
        "government_bonus": government_bonus,
        "employer": employer,
        "contribution_fee": contribution_fee,
        "total_into_pot": total_into_pot,
        "self_assessment": self_assessment,
        "method_label": method_label,
    }



def future_value(current_value, monthly_contribution, annual_growth_rate, years):
    monthly_rate = annual_growth_rate / 12
    months = int(years * 12)

    future_current = current_value * ((1 + monthly_rate) ** months)

    if monthly_rate == 0:
        future_contrib = monthly_contribution * months
    else:
        future_contrib = monthly_contribution * (((1 + monthly_rate) ** months - 1) / monthly_rate)

    return future_current + future_contrib



def add_months_to_key(month_key, offset):
    y, m = [int(x) for x in month_key.split("-")]
    m = m + offset
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


def projection_start_month_key(assumptions=None, today=None):
    """Month whose contribution should be considered next in projections.

    Before the monthly review-ready date, the current month's contribution may
    still be pending/settling, so a current-month budget override matters. Once
    the review-ready date has passed, projections move on to next month to avoid
    counting a contribution that should already be reflected in balances.
    """
    today = today or date.today()
    salary_day = 0
    try:
        salary_day = int(_safe_get(assumptions, "salary_day", 0) or 0)
    except (TypeError, ValueError):
        salary_day = 0

    current_key = f"{today.year:04d}-{today.month:02d}"
    if salary_day and today >= review_ready_date(today.year, today.month, salary_day):
        return add_months_to_key(current_key, 1)
    return current_key


def month_key_to_index(month_key):
    try:
        year, month = str(month_key).split("-")
        return int(year) * 12 + int(month)
    except (AttributeError, TypeError, ValueError):
        return None



def override_span_months(override):
    start = month_key_to_index(_safe_get(override, "from_month"))
    end = month_key_to_index(_safe_get(override, "to_month"))
    if start is None or end is None:
        return None
    return max(end - start, 0)



def select_best_matching_override(overrides, month_key):
    """Return the narrowest matching override; on ties prefer the newest record."""
    best = None
    best_span = None
    best_order = None

    for override in overrides or []:
        try:
            from_month = override["from_month"]
            to_month = override["to_month"]
        except (KeyError, TypeError):
            continue
        if not (from_month <= month_key <= to_month):
            continue

        span = override_span_months(override)
        try:
            order = int(_safe_get(override, "id", 0) or 0)
        except (TypeError, ValueError):
            order = 0

        if best is None:
            best = override
            best_span = span
            best_order = order
            continue

        if best_span is None and span is not None:
            best = override
            best_span = span
            best_order = order
            continue

        if span is not None and best_span is not None and span < best_span:
            best = override
            best_span = span
            best_order = order
            continue

        if span == best_span and order >= (best_order or 0):
            best = override
            best_span = span
            best_order = order

    return best



def contribution_override_for_month(account, month_key):
    """Return a personal monthly contribution override for account/month, if any."""
    override = select_best_matching_override(_safe_get(account, "_contribution_overrides", []) or [], month_key)
    return to_float(override["override_amount"]) if override is not None else None


def projected_personal_contribution(account, month_key):
    """Personal contribution planned for a projected month before wrappers add uplifts."""
    override = contribution_override_for_month(account, month_key) if month_key else None
    if override is not None:
        return override
    return to_float(_safe_get(account, "monthly_contribution", 0))


def _tax_year_start_for_month_key(month_key, assumptions=None):
    """Return the UK tax-year start year for a projected contribution month."""
    try:
        year_text, month_text = str(month_key).split("-")
        year = int(year_text)
        month = int(month_text)
    except (AttributeError, TypeError, ValueError):
        return None

    salary_day = 0
    try:
        salary_day = int(_safe_get(assumptions, "salary_day", 0) or 0)
    except (TypeError, ValueError):
        salary_day = 0

    if month > 4:
        return year
    if month < 4:
        return year - 1
    return year if salary_day >= 6 else year - 1


def _lisa_projected_prior_personal_in_tax_year(account, assumptions, month_index):
    start_month = _safe_get(account, "_projection_start_month")
    if not start_month or month_index <= 0:
        return 0.0

    month_key = add_months_to_key(start_month, month_index)
    tax_year_start = _tax_year_start_for_month_key(month_key, assumptions)
    if tax_year_start is None:
        return 0.0

    total = 0.0
    for idx in range(month_index):
        prior_key = add_months_to_key(start_month, idx)
        if _tax_year_start_for_month_key(prior_key, assumptions) == tax_year_start:
            total += projected_personal_contribution(account, prior_key)
    return total


def projected_contribution_breakdown(account, assumptions=None, month_index=0):
    """Projected contribution breakdown for one month, including overrides.

    This keeps one-off Lifetime ISA temporary plans as real one-off payments:
    a £4,000 projected month earns a £1,000 Lifetime ISA bonus in that month,
    rather than being treated as a £4,000/month annualised contribution.
    """
    start_month = _safe_get(account, "_projection_start_month")
    month_key = add_months_to_key(start_month, month_index) if start_month else None
    override = contribution_override_for_month(account, month_key) if month_key else None
    adjusted = dict(account)
    if override is not None:
        adjusted["monthly_contribution"] = override

    breakdown = contribution_breakdown(adjusted, assumptions)
    wrapper = (_safe_get(account, "wrapper_type") or "")
    is_lisa = "Lifetime" in wrapper or "LISA" in wrapper
    if not is_lisa:
        return breakdown

    if current_age_from_assumptions(assumptions) + month_index / 12.0 >= 50:
        breakdown["personal"] = 0.0
        breakdown["government_bonus"] = 0.0
        breakdown["total_into_pot"] = 0.0
        breakdown["method_label"] = "Lifetime ISA contributions stop at age 50"
        return breakdown

    personal = projected_personal_contribution(account, month_key) if month_key else to_float(adjusted.get("monthly_contribution", 0))
    prior_personal = _lisa_projected_prior_personal_in_tax_year(account, assumptions, month_index)
    eligible = max(min(personal, LISA_ANNUAL_CAP - prior_personal), 0.0)
    government_bonus = eligible * LISA_BONUS_RATE
    contribution_fee_pct = to_float(_safe_get(account, "contribution_fee_pct", 0))
    gross_into_pot = personal + government_bonus + to_float(_safe_get(account, "employer_contribution", 0))
    contribution_fee = gross_into_pot * (contribution_fee_pct / 100.0)

    breakdown["personal"] = personal
    breakdown["tax_relief"] = 0.0
    breakdown["government_bonus"] = government_bonus
    breakdown["contribution_fee"] = contribution_fee
    breakdown["total_into_pot"] = gross_into_pot - contribution_fee
    breakdown["method_label"] = "Lifetime ISA bonus (25%)"
    return breakdown


def projection_monthly_contribution(account, assumptions=None, month_index=0):
    """Effective contribution for a projected month, including overrides.

    Overrides replace the account's personal monthly contribution for matching
    months, then the normal account rules add tax relief, LISA bonus, employer
    contribution, and contribution fees.
    """
    return projected_contribution_breakdown(account, assumptions, month_index)["total_into_pot"]


def effective_monthly_contribution(account, assumptions=None):
    return contribution_breakdown(account, assumptions)["total_into_pot"]


def convert_to_gbp(amount, from_currency, fx_rates=None):
    """Convert an amount from a source currency to GBP.

    fx_rates should be a dict like {'USD': 1.25, 'EUR': 1.17} (how many per 1 GBP).
    If rates are missing, returns the amount unchanged (legacy behavior).
    """
    if not amount or not from_currency:
        return to_float(amount)

    if from_currency == "GBp":  # Pence to Pounds (must check before upper-casing)
        return to_float(amount) / 100.0

    if from_currency.upper() == "GBP":
        return to_float(amount)

    currency = from_currency.upper()

    if not fx_rates or currency not in fx_rates:
        return to_float(amount)

    # Conversion: GBP = Amount / Rate
    # e.g. $100 / 1.25 = £80
    return to_float(amount) / to_float(fx_rates[currency])


def to_float(val, default=0.0):
    try:
        return float(val or default)
    except (ValueError, TypeError):
        return default


def _safe_get(row, key, default=None):
    """Get a value from a sqlite3.Row or dict, returning default if missing or None."""
    try:
        v = row[key]
        return v if v is not None else default
    except (KeyError, IndexError):
        return default


def effective_account_value(account, holdings_totals=None):
    """Return the value of the account based on its valuation mode and uninvested cash."""
    holdings_totals = holdings_totals or {}
    uninvested = to_float(_safe_get(account, "uninvested_cash", 0))
    if account["valuation_mode"] == "holdings":
        return to_float(holdings_totals.get(account["id"], 0)) + uninvested
    return to_float(account["current_value"]) + uninvested


def total_invested(accounts, holdings_totals=None):
    return sum(effective_account_value(a, holdings_totals) for a in accounts)



def tag_totals(accounts, holdings_totals=None):
    totals = {}
    for account in accounts:
        tags = [t.strip() for t in (account["tags"] or "").split(",") if t.strip()]
        value = effective_account_value(account, holdings_totals)
        for tag in tags:
            totals[tag] = totals.get(tag, 0.0) + value
    return totals


def goal_current_value(selected_tags, accounts, holdings_totals=None):
    """Return the combined value of accounts matching any of the selected tags.
    Each account is counted once even if it matches multiple tags."""
    if not selected_tags:
        return 0.0
    tag_set = set(selected_tags)
    total = 0.0
    for account in accounts:
        account_tags = {t.strip() for t in (account.get("tags") or "").split(",") if t.strip()}
        if account_tags & tag_set:
            total += effective_account_value(account, holdings_totals)
    return total


def total_monthly_contributions(accounts, assumptions=None):
    """Sum of monthly contributions across accounts, full into-pot.

    Includes tax relief, LISA bonus, employer match, and contribution fees so
    the figure matches what's actually landing in pots each month — same
    convention used by the Performance page and Overview chip.
    """
    return sum(effective_monthly_contribution(a, assumptions) for a in accounts)



def _safe_year_anniversary(dob, year):
    last_day = monthrange(year, dob.month)[1]
    return date(year, dob.month, min(dob.day, last_day))


def _retirement_target_date(dob_str, retirement_age, mode="birthday"):
    if not dob_str:
        return None
    try:
        dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    retire_year = dob.year + int(retirement_age)
    if mode == "end_of_year":
        return date(retire_year, 12, 31)
    elif mode == "end_of_tax_year":
        if (dob.month, dob.day) < (4, 6):
            return date(retire_year, 4, 5)
        else:
            return date(retire_year + 1, 4, 5)
    else:
        return _safe_year_anniversary(dob, retire_year)


def years_to_retirement(current_age, retirement_age, assumptions=None):
    """Return years remaining to retirement.

    If assumptions with DOB and retirement_date_mode are available, uses
    an exact date calculation. Otherwise falls back to simple subtraction.
    """
    if assumptions:
        dob = _safe_get(assumptions, "date_of_birth")
        mode = _safe_get(assumptions, "retirement_date_mode") or "birthday"
        if dob:
            target = _retirement_target_date(dob, retirement_age, mode)
            if target:
                today = date.today()
                delta = target - today
                return max(delta.days / 365.25, 0)
    return max(retirement_age - current_age, 0)


def effective_fee_pct(account):
    """Compute the total effective annual fee as a percentage.

    Combines platform fee and fund fee into a single figure.
    Platform fees can be a percentage (e.g. 0.15 for 0.15%), a flat annual £
    amount (converted to an approximate % based on current value), or both.
    If a platform fee cap is set, the percentage-based platform fee is capped
    at that £ amount relative to the current value.

    Returns fee as a percentage value (e.g. 0.37 means 0.37%).
    """
    platform_pct = to_float(_safe_get(account, "platform_fee_pct", 0))
    platform_flat = to_float(_safe_get(account, "platform_fee_flat", 0))
    platform_cap = to_float(_safe_get(account, "platform_fee_cap", 0))
    fund_pct = to_float(_safe_get(account, "fund_fee_pct", 0))

    # If no granular fees are set, fall back to legacy annual_fee_pct
    if platform_pct == 0 and platform_flat == 0 and fund_pct == 0:
        return to_float(_safe_get(account, "annual_fee_pct", 0))

    current_value = to_float(_safe_get(account, "current_value", 0))

    # Platform fee: percentage-based, possibly capped
    if platform_pct > 0 and platform_cap > 0 and current_value > 0:
        # The cap limits the £ amount charged; convert cap to equivalent %
        pct_cost = current_value * (platform_pct / 100.0)
        actual_cost = min(pct_cost, platform_cap)
        effective_platform_pct = (actual_cost / current_value) * 100.0
    else:
        effective_platform_pct = platform_pct

    # Platform fee: flat annual amount converted to approximate %
    # When current_value is 0, flat fees can't be expressed as a %; they're
    # ignored until the account has a balance (avoids division by zero).
    if platform_flat > 0 and current_value > 0:
        effective_platform_pct += (platform_flat / current_value) * 100.0

    # Cap at a reasonable maximum to avoid nonsensical projections
    total = min(effective_platform_pct + fund_pct, 25.0)
    return total


def account_growth_rate(account, assumptions):
    """Return the effective annual growth rate for an account, net of fees.

    Uses the granular fee fields (platform_fee_pct, platform_fee_flat,
    platform_fee_cap, fund_fee_pct) when available, falling back to the
    legacy annual_fee_pct column.
    """
    if account["growth_mode"] == "custom" and account["growth_rate_override"] is not None:
        gross = to_float(account["growth_rate_override"])
    else:
        gross = to_float(assumptions["annual_growth_rate"]) if assumptions else 0.0
    fee = effective_fee_pct(account)
    return max(gross - fee / 100.0, 0.0)


def account_gross_growth_rate(account, assumptions):
    """Return the gross annual growth rate (before fees) for display purposes."""
    if account["growth_mode"] == "custom" and account["growth_rate_override"] is not None:
        return to_float(account["growth_rate_override"])
    return to_float(assumptions["annual_growth_rate"]) if assumptions else 0.0


def _project_account_month_by_month(account, assumptions, month_count, rate):
    """Project account value month by month so budget overrides can apply."""
    from .models.accounts import is_premium_bonds_account, PREMIUM_BONDS_MAX_BALANCE
    value = to_float(account["current_value"])
    monthly_rate = rate / 12.0
    current_age = current_age_from_assumptions(assumptions)
    is_lisa = account["wrapper_type"] == "Lifetime ISA"
    is_pb = is_premium_bonds_account(account)
    months = max(int(month_count), 0)

    for idx in range(months):
        value *= (1 + monthly_rate)
        if not is_lisa or (current_age + idx / 12.0) < 50:
            value += projection_monthly_contribution(account, assumptions, idx)
        # Premium Bonds can't compound past £50k — NS&I would pay overflow
        # as cash prizes, so the balance line stays flat at the cap.
        if is_pb and value > PREMIUM_BONDS_MAX_BALANCE:
            value = PREMIUM_BONDS_MAX_BALANCE
    return value


def projected_account_value_at_year(account, assumptions, yr):
    """Project account value at `yr` years from now, respecting LISA contribution cap at 50."""
    return _project_account_month_by_month(account, assumptions, int(yr * 12), account_growth_rate(account, assumptions))


def projected_account_value_at_month(account, assumptions, month_count):
    """Project account value at `month_count` months from now, respecting LISA cap at 50."""
    return _project_account_month_by_month(account, assumptions, month_count, account_growth_rate(account, assumptions))


def projected_account_value_at_month_no_fees(account, assumptions, month_count):
    """Same as projected_account_value_at_month but using gross growth rate."""
    return _project_account_month_by_month(account, assumptions, month_count, account_gross_growth_rate(account, assumptions))


def projected_account_value(account, assumptions):
    if not assumptions:
        return 0.0
    current_age = current_age_from_assumptions(assumptions)
    retirement_age = to_float(assumptions["retirement_age"])
    months = int(years_to_retirement(current_age, retirement_age, assumptions) * 12)
    return _project_account_month_by_month(account, assumptions, months, account_growth_rate(account, assumptions))


def projected_account_value_no_fees(account, assumptions):
    """Same as projected_account_value but using the gross growth rate (ignoring fees)."""
    if not assumptions:
        return 0.0
    current_age = current_age_from_assumptions(assumptions)
    retirement_age = to_float(assumptions["retirement_age"])
    months = int(years_to_retirement(current_age, retirement_age, assumptions) * 12)
    return _project_account_month_by_month(account, assumptions, months, account_gross_growth_rate(account, assumptions))


def projected_account_value_at_year_no_fees(account, assumptions, yr):
    """Same as projected_account_value_at_year but using gross growth rate."""
    return _project_account_month_by_month(account, assumptions, int(yr * 12), account_gross_growth_rate(account, assumptions))


def projected_total_retirement_value(accounts, assumptions):
    if not assumptions:
        return 0.0
    return sum(projected_account_value(account, assumptions) for account in accounts)


def projected_accounts(accounts, assumptions):
    if not assumptions:
        return []
    rows = []
    for account in accounts:
        current = to_float(account["current_value"])
        personal = to_float(account["monthly_contribution"])
        first_month_override = None
        start_month = _safe_get(account, "_projection_start_month")
        if start_month:
            first_month_override = contribution_override_for_month(account, start_month)
        contribution_account = dict(account)
        if first_month_override is not None:
            contribution_account["monthly_contribution"] = first_month_override
        breakdown = contribution_breakdown(contribution_account, assumptions)
        effective_contribution = breakdown["total_into_pot"]
        growth = account_growth_rate(account, assumptions)
        projected = projected_account_value(account, assumptions)
        proj_no_fees = projected_account_value_no_fees(account, assumptions)
        rows.append({
            "account_id": account.get("id"),
            "name": account["name"],
            "provider": account["provider"],
            "wrapper_type": account["wrapper_type"],
            "current_value": current,
            "monthly_contribution": personal,
            "effective_contribution": effective_contribution,
            "tax_relief": breakdown["tax_relief"],
            "government_bonus": breakdown["government_bonus"],
            "employer": breakdown["employer"],
            "contribution_fee": breakdown["contribution_fee"],
            "contribution_fee_pct": to_float(_safe_get(account, "contribution_fee_pct", 0)),
            "self_assessment": breakdown["self_assessment"],
            "method_label": breakdown["method_label"],
            "projected_value": projected,
            "growth_rate": growth,
            "gross_growth_rate": account_gross_growth_rate(account, assumptions),
            "annual_fee_pct": effective_fee_pct(account),
            "platform_fee_pct": to_float(_safe_get(account, "platform_fee_pct", 0)),
            "platform_fee_flat": to_float(_safe_get(account, "platform_fee_flat", 0)),
            "platform_fee_cap": to_float(_safe_get(account, "platform_fee_cap", 0)),
            "fund_fee_pct": to_float(_safe_get(account, "fund_fee_pct", 0)),
            "growth_mode": account["growth_mode"],
            "projected_no_fees": proj_no_fees,
            "fee_impact": proj_no_fees - projected,
        })
    return rows


def compute_performance_series(monthly_data, assumed_rate, assumed_monthly, benchmark_rate=None):
    """Compute actual vs projected performance from monthly snapshot data.

    Args:
        monthly_data: list of (month_key, total_balance, total_contribution)
        assumed_rate: annual growth rate assumption (e.g. 0.07)
        assumed_monthly: current total monthly contribution

    Returns a dict ready to pass to the performance template, or None if no data.

    The benchmark_values key is intentionally None — it exists as a slot for a
    future benchmark data source (API or manual entry) without template changes.
    """
    if not monthly_data:
        return None

    from datetime import datetime as _dt
    month_keys   = [m[0] for m in monthly_data]
    balances     = [m[1] for m in monthly_data]
    contribs     = [m[2] for m in monthly_data]
    carried_counts = [m[3] if len(m) > 3 else 0 for m in monthly_data]
    fixed_gains = [m[4] if len(m) > 4 else None for m in monthly_data]
    imported_baselines = [float(m[5] or 0) if len(m) > 5 else 0.0 for m in monthly_data]

    def _fmt(mk):
        try:
            return _dt.strptime(mk, "%Y-%m").strftime("%b %Y")
        except (ValueError, TypeError):
            return mk

    display_labels = [_fmt(mk) for mk in month_keys]

    # ── Modified Dietz monthly returns ────────────────────────────────────
    # Assumes contributions arrive mid-month (weight = 0.5)
    monthly_returns = []
    for i in range(1, len(monthly_data)):
        start = balances[i - 1]
        end   = balances[i]
        cf    = contribs[i]
        imported = imported_baselines[i] if i < len(imported_baselines) else 0.0
        total_flow = cf + imported
        fixed_gain = fixed_gains[i] if i < len(fixed_gains) else None
        gain = float(fixed_gain) if fixed_gain is not None else (end - start - total_flow)
        denom = start + 0.5 * total_flow
        monthly_returns.append(gain / denom if denom > 0 else 0.0)

    # ── Chain-linked cumulative & annualised return ────────────────────────
    cum = 1.0
    for r in monthly_returns:
        cum *= (1 + r)
    total_return = cum - 1.0
    n = len(monthly_returns)
    # Require at least 3 months before annualising — with fewer data points
    # the figure is statistically meaningless and often alarming.
    annualised_return = ((cum ** (12.0 / n)) - 1) if n >= 3 else None

    # ── Projected "on plan" series from first recorded balance ────────────
    # Uses the contribution recorded for each month instead of today's normal
    # monthly amount. That keeps reduced/skipped months from budget/reviews from
    # making the plan line look wildly wrong.
    start_balance = balances[0]
    def _plan_values(rate):
        values = [round(start_balance, 0)]
        current = start_balance
        monthly_rate = rate / 12.0
        for i in range(1, len(monthly_data)):
            current = current * (1 + monthly_rate) + contribs[i]
            values.append(round(current, 0))
        return values

    projected_values = _plan_values(assumed_rate)

    # ── Month-by-month breakdown table ────────────────────────────────────
    rows = []
    first_month_has_initial_flow = (
        len(monthly_data) == 1
        and (
            abs(float(imported_baselines[0] if imported_baselines else 0.0)) > 0.005
            or (
                abs(float(contribs[0] or 0)) > 0.005
                and abs(float(contribs[0] or 0) - float(assumed_monthly or 0)) > 0.005
            )
        )
    )
    if first_month_has_initial_flow:
        closing = balances[0]
        cf = contribs[0]
        imported = imported_baselines[0] if imported_baselines else 0.0
        opening = max(closing - cf - imported, 0.0)
        fixed_gain = fixed_gains[0] if fixed_gains else None
        gain = float(fixed_gain) if fixed_gain is not None else (closing - opening - cf - imported)
        denom = opening + 0.5 * (cf + imported)
        r = gain / denom if denom > 0 else 0.0
        rows.append({
            "month_key": display_labels[0],
            "opening": round(opening, 2),
            "imported_baseline": round(imported, 2),
            "contribution": round(cf, 2),
            "market_gain": round(gain, 2),
            "closing": round(closing, 2),
            "return_pct": round(r * 100, 2),
            "carried_forward_count": carried_counts[0] if carried_counts else 0,
        })
    for i in range(1, len(monthly_data)):
        opening = balances[i - 1]
        closing = balances[i]
        cf      = contribs[i]
        imported = imported_baselines[i] if i < len(imported_baselines) else 0.0
        fixed_gain = fixed_gains[i] if i < len(fixed_gains) else None
        gain = float(fixed_gain) if fixed_gain is not None else (closing - opening - cf - imported)
        r       = monthly_returns[i - 1]
        rows.append({
            "month_key":    display_labels[i],
            "opening":      round(opening, 2),
            "imported_baseline": round(imported, 2),
            "contribution": round(cf, 2),
            "market_gain":  round(gain, 2),
            "closing":      round(closing, 2),
            "return_pct":   round(r * 100, 2),
            "carried_forward_count": carried_counts[i],
        })
    rows.reverse()   # most recent first

    # ── Totals for summary cards ──────────────────────────────────────────
    total_imported_baseline = sum(imported_baselines)
    if first_month_has_initial_flow:
        total_contributed = round(float(contribs[0] or 0), 2)
        total_market_gain = round(float(fixed_gains[0]) if fixed_gains and fixed_gains[0] is not None else float(balances[0] or 0) - total_contributed - total_imported_baseline, 2)
    else:
        total_contributed = sum(contribs[1:])   # exclude opening balance month
        total_market_gain = 0.0
        for i in range(1, len(balances)):
            fixed_gain = fixed_gains[i] if i < len(fixed_gains) else None
            total_market_gain += float(fixed_gain) if fixed_gain is not None else (balances[i] - balances[i - 1] - contribs[i] - imported_baselines[i])
    vs_plan = balances[-1] - projected_values[-1] if projected_values else 0

    return {
        "labels":            display_labels,
        "actual_values":     [round(b, 0) for b in balances],
        "projected_values":  projected_values,
        "benchmark_values":  _plan_values(benchmark_rate) if benchmark_rate is not None else None,
        "monthly_returns":   monthly_returns,
        "table_rows":        rows,
        "n_months":          n,
        "total_return":      round(total_return * 100, 2),
        "annualised_return": round(annualised_return * 100, 2) if annualised_return is not None else None,
        "total_contributed": round(total_contributed, 2),
        "total_imported_baseline": round(total_imported_baseline, 2),
        "total_market_gain": round(total_market_gain, 2),
        "vs_plan":           round(vs_plan, 2),
        "current_value":     round(balances[-1], 2) if balances else 0,
        "carried_forward_months": sum(1 for c in carried_counts if c),
    }


def progress_to_goal(current, target):
    if not target or target <= 0:
        return 0.0
    return current / target


def remaining_to_goal(current, target):
    return max(target - current, 0)


def allowance_progress(used, allowance):
    if not allowance or allowance <= 0:
        return 0.0
    return used / allowance


def uk_tax_year_label(today=None):
    today = today or date.today()
    start_year = today.year if (today.month > 4 or (today.month == 4 and today.day >= 6)) else today.year - 1
    end_year = start_year + 1
    return f"{start_year}/{str(end_year)[-2:]}"


def uk_tax_year_end(today=None):
    today = today or date.today()
    end_year = today.year + 1 if (today.month > 4 or (today.month == 4 and today.day >= 6)) else today.year
    return date(end_year, 4, 5)


def days_until_tax_year_end(today=None):
    today = today or date.today()
    return max((uk_tax_year_end(today) - today).days, 0)


def uk_tax_year_start(today=None):
    """Return the start date (April 6) of the current UK tax year."""
    today = today or date.today()
    start_year = today.year if (today.month > 4 or (today.month == 4 and today.day >= 6)) else today.year - 1
    return date(start_year, 4, 6)




def months_in_tax_year(today=None, salary_day=0):
    today = today or date.today()
    start = uk_tax_year_start(today)
    contribution_day = salary_day if salary_day >= 1 else 1
    if contribution_day >= 6:
        first_year, first_month = start.year, start.month
    else:
        first_year = start.year
        first_month = start.month + 1
        if first_month > 12:
            first_month = 1
            first_year += 1
    count = 0
    y, m = first_year, first_month
    while (y < today.year) or (y == today.year and m <= today.month):
        if y < today.year or (y == today.year and m < today.month):
            count += 1
        elif y == today.year and m == today.month:
            if today.day >= _resolve_contribution_day(y, m, contribution_day):
                count += 1
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return count


def full_year_contribution_months(salary_day=0):
    return 12


def _resolve_contribution_day(year, month, nominal_day):
    import calendar
    max_day = calendar.monthrange(year, month)[1]
    day = min(nominal_day, max_day)
    wd = date(year, month, day).weekday()
    if wd == 5:
        day -= 1
    elif wd == 6:
        day -= 2
    return max(1, day)


def review_ready_date(year, month, salary_day=0):
    """Calculate the date when investments should be settled and the monthly
    review is ready to do, for a given month.

    Logic:
    1. Start with the salary/investment day for that month.
    2. If it falls on a weekend, shift to the preceding Friday
       (banks pay early, standing orders move earlier).
    3. Add 2 business days for settlement.

    Returns a date object.
    """
    nominal_day = salary_day if salary_day >= 1 else 1
    # Clamp to last day of month and shift weekends to preceding Friday
    day = _resolve_contribution_day(year, month, nominal_day)
    d = date(year, month, day)

    # Add 2 business days for settlement
    days_added = 0
    while days_added < 2:
        d = d + timedelta(days=1)
        if d.weekday() < 5:  # Mon-Fri
            days_added += 1

    return d


def is_review_due(today, salary_day=0):
    """Check whether the monthly review is due for the current month.

    Returns True if today is on or after the review-ready date.
    """
    ready = review_ready_date(today.year, today.month, salary_day)
    return today >= ready


def is_salary_day(today, salary_day=0):
    """Return True if today is the resolved salary/investment day for this month."""
    if not salary_day:
        return False
    resolved = _resolve_contribution_day(today.year, today.month, salary_day)
    return today.day == resolved


ISA_WRAPPER_TYPES = {
    "Stocks & Shares ISA",
    "Stocks and Shares ISA",
    "Cash ISA",
    "Lifetime ISA",
}
LISA_WRAPPER_TYPES = {"Lifetime ISA"}


def _contribution_month_keys(today, salary_day):
    """Return list of YYYY-MM month keys where a regular contribution has gone through this tax year."""
    start = uk_tax_year_start(today)
    contribution_day = salary_day if salary_day >= 1 else 1
    if contribution_day >= 6:
        y, m = start.year, start.month
    else:
        y, m = start.year, start.month + 1
        if m > 12:
            y, m = y + 1, 1
    keys = []
    while (y < today.year) or (y == today.year and m <= today.month):
        if y < today.year or (y == today.year and m < today.month):
            keys.append(f"{y}-{m:02d}")
        elif y == today.year and m == today.month:
            if today.day >= _resolve_contribution_day(y, m, contribution_day):
                keys.append(f"{y}-{m:02d}")
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return keys



def _tax_year_contribution_month_keys(today, salary_day):
    """Return every scheduled contribution month in the current tax year."""
    start = uk_tax_year_start(today)
    contribution_day = salary_day if salary_day >= 1 else 1
    if contribution_day >= 6:
        y, m = start.year, start.month
    else:
        y, m = start.year, start.month + 1
        if m > 12:
            y, m = y + 1, 1
    keys = []
    for _ in range(full_year_contribution_months(salary_day)):
        keys.append(f"{y}-{m:02d}")
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return keys



def _effective_personal_amount_for_month(account_id, monthly_default, month_key, override_rows=None, review_amount_map=None):
    review_amount_map = review_amount_map or {}
    rkey = (account_id, month_key)
    if rkey in review_amount_map:
        return review_amount_map[rkey]
    override = select_best_matching_override(override_rows or [], month_key)
    if override is not None:
        return float(override["override_amount"] or 0)
    return monthly_default


def calculate_isa_usage(
    accounts,
    ad_hoc_contributions,
    today=None,
    salary_day=0,
    isa_overrides=None,
    review_contributions=None,
    allowance_events=None,
    lisa_contributions_allowed=True,
):
    """Auto-calculate ISA and LISA usage for the current tax year.

    accounts: list of account dicts (need wrapper_type, monthly_contribution)
    ad_hoc_contributions: list of isa_contributions rows (need wrapper_type, amount)
    salary_day: day of month when contributions go in (affects April handling)
    isa_overrides: list of override rows (account_id, from_month, to_month, override_amount)
                   — used to apply skips/adjustments to per-month contribution amounts
    review_contributions: list of rows from fetch_tax_year_contributions (each row
                   has account_id, month_key, expected_contribution, is_skipped).
                   When present, a finalised review item replaces the per-account
                   default for that month — the review is the user's confirmed truth.
    allowance_events: explicit cash-flow rows marked to change tracked ISA usage.
    lisa_contributions_allowed: when false, ignore regular scheduled LISA
                   contributions (used once the user is age 50+), but keep
                   recorded ad-hoc/review contributions as historical truth.

    Returns dict with keys: isa_used, lisa_used, monthly_isa, monthly_lisa,
    adhoc_isa, adhoc_lisa, projected_isa, projected_lisa, breakdown.
    """
    today = today or date.today()
    month_keys = _contribution_month_keys(today, salary_day)
    projection_month_keys = _tax_year_contribution_month_keys(today, salary_day)
    months = len(month_keys)
    total_months = len(projection_month_keys)

    # Build override lookup: account_id → matching override rows
    override_map = {}
    for ov in (isa_overrides or []):
        aid = ov["account_id"]
        override_map.setdefault(aid, []).append(ov)

    # Build review lookup: (account_id, month_key) → expected personal amount.
    # is_skipped rows force £0 regardless of the stored expected_contribution.
    review_amount_map = {}
    for rc in (review_contributions or []):
        key = (rc["account_id"], rc["month_key"])
        if rc["is_skipped"]:
            review_amount_map[key] = 0.0
        else:
            review_amount_map[key] = float(rc["expected_contribution"] or 0)

    allowance_adjustment_map = {}
    allowance_adjustment_isa = 0.0
    for event in (allowance_events or []):
        effect = str(event.get("allowance_effect") or "none").strip().lower()
        try:
            raw_amount = abs(float(event.get("amount") or 0))
        except (TypeError, ValueError):
            raw_amount = 0.0
        signed_amount = 0.0
        if effect in ("subscription", "flexible_replacement"):
            signed_amount = raw_amount
        elif effect == "flexible_withdrawal":
            signed_amount = -raw_amount
        if not signed_amount:
            continue
        account_id = event["account_id"]
        allowance_adjustment_map[account_id] = allowance_adjustment_map.get(account_id, 0.0) + signed_amount
        allowance_adjustment_isa += signed_amount

    monthly_isa = 0.0
    monthly_lisa = 0.0
    projected_monthly_isa = 0.0
    projected_monthly_lisa = 0.0
    breakdown = []

    for acc in accounts:
        try:
            wt = acc["wrapper_type"] or ""
        except (KeyError, TypeError):
            wt = ""
        if wt not in ISA_WRAPPER_TYPES:
            continue
        is_lisa_account = wt in LISA_WRAPPER_TYPES
        if is_lisa_account and not lisa_contributions_allowed:
            monthly = 0.0
        else:
            try:
                monthly = float(acc["monthly_contribution"] or 0)
            except (KeyError, TypeError):
                monthly = 0.0
        override_rows = override_map.get(acc["id"], [])
        total = sum(
            _effective_personal_amount_for_month(acc["id"], monthly, mk, override_rows, review_amount_map)
            for mk in month_keys
        )
        projected = sum(
            _effective_personal_amount_for_month(acc["id"], monthly, mk, override_rows, review_amount_map)
            for mk in projection_month_keys
        )
        entry = {
            "account_id": acc["id"],
            "account_name": acc["name"],
            "wrapper_type": wt,
            "monthly_contribution": monthly,
            "months": months,
            "monthly_total": total,
            "adhoc_total": 0.0,
            "allowance_adjustment": allowance_adjustment_map.get(acc["id"], 0.0),
            "projected_total": projected,
        }
        monthly_isa += total
        projected_monthly_isa += projected
        if wt in LISA_WRAPPER_TYPES:
            monthly_lisa += total
            projected_monthly_lisa += projected
        breakdown.append(entry)

    # Sum ad-hoc contributions
    adhoc_isa = 0.0
    adhoc_lisa = 0.0
    for c in ad_hoc_contributions:
        amt = float(c["amount"])
        try:
            wt = c["wrapper_type"] or ""
        except (KeyError, TypeError):
            wt = ""
        adhoc_isa += amt
        if wt in LISA_WRAPPER_TYPES:
            adhoc_lisa += amt
        # Add to breakdown
        for entry in breakdown:
            if entry["account_id"] == c["account_id"]:
                entry["adhoc_total"] += amt
                break

    return {
        "isa_used": monthly_isa + adhoc_isa + allowance_adjustment_isa,
        "lisa_used": monthly_lisa + adhoc_lisa,
        "monthly_isa": monthly_isa,
        "monthly_lisa": monthly_lisa,
        "adhoc_isa": adhoc_isa,
        "adhoc_lisa": adhoc_lisa,
        "allowance_adjustment_isa": allowance_adjustment_isa,
        "projected_isa": projected_monthly_isa + adhoc_isa + allowance_adjustment_isa,
        "projected_lisa": projected_monthly_lisa + adhoc_lisa,
        "months": months,
        "total_months": total_months,
        "breakdown": breakdown,
    }


def pension_allowance_limits(assumptions=None):
    assumptions = assumptions or {}
    try:
        annual_allowance = float(assumptions.get("pension_annual_allowance") or 60000)
    except (TypeError, ValueError):
        annual_allowance = 60000.0

    try:
        mpaa_enabled = int(assumptions.get("mpaa_enabled") or 0) == 1
    except (TypeError, ValueError):
        mpaa_enabled = False

    try:
        mpaa_allowance = float(assumptions.get("mpaa_allowance") or 10000)
    except (TypeError, ValueError):
        mpaa_allowance = 10000.0

    effective_allowance = min(annual_allowance, mpaa_allowance) if mpaa_enabled else annual_allowance

    try:
        income = float(assumptions.get("annual_income") or 0)
    except (TypeError, ValueError):
        income = 0.0

    if income > 0:
        personal_relief_limit = min(income, effective_allowance)
    else:
        personal_relief_limit = min(3600.0, effective_allowance)

    return {
        "annual_allowance": annual_allowance,
        "effective_allowance": effective_allowance,
        "personal_relief_limit": personal_relief_limit,
        "annual_income": income,
        "mpaa_enabled": mpaa_enabled,
        "mpaa_allowance": mpaa_allowance,
    }


def apply_pension_carry_forward(pension_limits=None, carry_forward_entries=None):
    pension_limits_with_carry = dict(pension_limits or {})

    if pension_limits_with_carry.get("mpaa_enabled"):
        pension_limits_with_carry["carry_forward_total"] = 0.0
        return pension_limits_with_carry

    carry_forward_total = 0.0

    for entry in (carry_forward_entries or [])[:3]:
        try:
            carry_forward_total += float(_safe_get(entry, "unused_allowance") or 0)
        except (TypeError, ValueError):
            continue

    pension_limits_with_carry["effective_allowance"] = float(
        pension_limits_with_carry.get("effective_allowance") or 0
    ) + carry_forward_total
    pension_limits_with_carry["carry_forward_total"] = carry_forward_total
    return pension_limits_with_carry


def is_pension_account(account):
    if not account:
        return False
    cat = (_safe_get(account, "category") or "").strip().lower()
    wt = (_safe_get(account, "wrapper_type") or "").strip().lower()
    return (cat == "pension") or ("pension" in wt) or ("sipp" in wt)


def calculate_pension_usage(
    accounts,
    ad_hoc_contributions,
    assumptions=None,
    today=None,
    salary_day=0,
    pension_overrides=None,
    review_contributions=None,
):
    today = today or date.today()
    months = months_in_tax_year(today, salary_day)
    total_months = full_year_contribution_months(salary_day)

    used_total = 0.0
    used_personal = 0.0
    used_employer = 0.0
    projected_total = 0.0
    breakdown = []

    assumptions = assumptions or {}

    override_map = {}
    for ov in (pension_overrides or []):
        aid = ov["account_id"]
        override_map.setdefault(aid, []).append(ov)

    review_amount_map = {}
    for rc in (review_contributions or []):
        key = (rc["account_id"], rc["month_key"])
        if rc["is_skipped"]:
            review_amount_map[key] = 0.0
        else:
            review_amount_map[key] = float(rc["expected_contribution"] or 0)

    for acc in accounts:
        if not is_pension_account(acc):
            continue

        try:
            acc_day = int(acc.get("pension_contribution_day") or 0)
        except (ValueError, TypeError):
            acc_day = 0
        if not acc_day:
            acc_day = salary_day
        month_keys = _contribution_month_keys(today, acc_day)
        projection_month_keys = _tax_year_contribution_month_keys(today, acc_day)
        acc_months = len(month_keys)
        acc_total_months = len(projection_month_keys)

        baseline = contribution_breakdown(acc, assumptions)
        monthly_total = float(baseline.get("total_into_pot") or 0)

        total = 0.0
        personal_total = 0.0
        employer_total = 0.0

        default_personal = float(_safe_get(acc, "monthly_contribution") or 0)
        method = (_safe_get(acc, "contribution_method") or "")
        override_rows = override_map.get(int(acc["id"]), [])

        for mk in month_keys:
            personal = float(
                _effective_personal_amount_for_month(int(acc["id"]), default_personal, mk, override_rows, review_amount_map)
                or 0
            )
            if personal <= 0:
                continue
            adjusted = dict(acc)
            adjusted["monthly_contribution"] = personal
            b = contribution_breakdown(adjusted, assumptions)
            m_total = float(b.get("total_into_pot") or 0)
            m_employer = float(b.get("employer") or 0)
            m_personal_net = float(b.get("personal") or 0)
            m_tax_relief = float(b.get("tax_relief") or 0)

            if method == "salary_sacrifice":
                m_personal_gross = 0.0
                m_employer_gross = m_total
            else:
                m_personal_gross = max(0.0, (m_personal_net + m_tax_relief))
                m_employer_gross = max(0.0, m_employer)

            total += m_total
            personal_total += m_personal_gross
            employer_total += m_employer_gross

        projected = 0.0
        for mk in projection_month_keys:
            personal = float(
                _effective_personal_amount_for_month(int(acc["id"]), default_personal, mk, override_rows, review_amount_map)
                or 0
            )
            if personal <= 0:
                continue
            adjusted = dict(acc)
            adjusted["monthly_contribution"] = personal
            projected += float(contribution_breakdown(adjusted, assumptions).get("total_into_pot") or 0)

        used_total += total
        used_personal += personal_total
        used_employer += employer_total
        projected_total += projected

        breakdown.append({
            "account_id": _safe_get(acc, "id"),
            "account_name": _safe_get(acc, "name"),
            "wrapper_type": (_safe_get(acc, "wrapper_type") or ""),
            "monthly_total": monthly_total,
            "monthly_personal": 0.0,
            "monthly_employer": 0.0,
            "months": acc_months,
            "total_months": acc_total_months,
            "monthly_sum": total,
            "adhoc_total": 0.0,
            "adhoc_personal": 0.0,
            "adhoc_employer": 0.0,
        })

    adhoc_total = 0.0
    adhoc_personal = 0.0
    adhoc_employer = 0.0

    for c in ad_hoc_contributions:
        amt = float(c["amount"])
        kind = (c.get("kind") or "personal").strip().lower()
        adhoc_total += amt
        if kind == "employer":
            adhoc_employer += amt
        else:
            adhoc_personal += amt

        for entry in breakdown:
            if entry["account_id"] == c["account_id"]:
                entry["adhoc_total"] += amt
                if kind == "employer":
                    entry["adhoc_employer"] += amt
                else:
                    entry["adhoc_personal"] += amt
                break

    used_total += adhoc_total
    used_personal += adhoc_personal
    used_employer += adhoc_employer
    projected_total += adhoc_total

    return {
        "pension_used": used_total,
        "pension_personal_used": used_personal,
        "pension_employer_used": used_employer,
        "adhoc_total": adhoc_total,
        "adhoc_personal": adhoc_personal,
        "adhoc_employer": adhoc_employer,
        "projected_total": projected_total,
        "months": months,
        "total_months": total_months,
        "breakdown": breakdown,
    }


def build_month_strip(today=None):
    """Build the 12-month tax-year strip (Apr → Mar) for the current date.

    Returns a list of dicts: key, label, month_num, is_current, is_today.
    This is a display-only strip (no budget data), so has_data is always False.
    """
    today = today or date.today()
    current_month_key = today.strftime("%Y-%m")
    current_month_num = today.month

    # Determine the tax year start (April)
    if today.month > 4 or (today.month == 4 and today.day >= 6):
        ty_start_year = today.year
    else:
        ty_start_year = today.year - 1

    strip = []
    for i in range(12):
        m = 4 + i  # Apr=4 … Mar=15→3
        y = ty_start_year if m <= 12 else ty_start_year + 1
        if m > 12:
            m -= 12
        mk = f"{y}-{m:02d}"
        label_short = datetime.strptime(mk, "%Y-%m").strftime("%b")
        strip.append({
            "key": mk,
            "label": label_short,
            "month_num": m,
            "is_current": (m == current_month_num),
            "is_today": (mk == current_month_key),
            "has_data": False,
        })
    return strip
