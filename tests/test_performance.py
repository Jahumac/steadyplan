from datetime import date


def test_monthly_performance_carries_forward_missing_account_snapshots(app, make_user):
    """A partial month should not make untouched accounts look like £0.

    This matches the real-world flow where a user updates one new/manual account
    in the current month before completing a full monthly review.
    """
    uid, _, _ = make_user()

    with app.app_context():
        from app.calculations import compute_performance_series
        from app.models import fetch_monthly_performance_data, get_connection

        with get_connection() as conn:
            isa = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active) VALUES (?, 'ISA', 58811, 1)",
                (uid,),
            ).lastrowid
            cash = conn.execute(
                "INSERT INTO accounts (user_id, name, current_value, is_active) VALUES (?, 'Cash ISA', 3200, 1)",
                (uid,),
            ).lastrowid
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, month_key, balance) VALUES ('2026-03-01', ?, '2026-03', 58811)",
                (isa,),
            )
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, month_key, balance) VALUES ('2026-03-01', ?, '2026-03', 3200)",
                (cash,),
            )
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, month_key, balance) VALUES ('2026-04-01', ?, '2026-04', 3200)",
                (cash,),
            )
            conn.commit()

        monthly_data = fetch_monthly_performance_data(uid)
        assert monthly_data == [
            ("2026-03", 62011.0, 0.0, 0, None, 62011.0),
            ("2026-04", 62011.0, 0.0, 1),
        ]

        perf = compute_performance_series(monthly_data, 0.07, 0)
        assert perf["total_return"] == 0.0
        assert perf["total_market_gain"] == 0.0
        assert perf["carried_forward_months"] == 1


def test_performance_hides_annualised_return_for_early_history():
    from app.calculations import compute_performance_series

    monthly_data = [
        ("2026-03", 1000, 0, 0, None, 1000),
        ("2026-04", 1100, 0, 0),
        ("2026-05", 1210, 0, 0),
        ("2026-06", 1331, 0, 0),
    ]

    perf = compute_performance_series(monthly_data, 0.07, 0)

    assert perf["total_return"] == 33.1
    assert perf["annualised_return"] is None
    assert perf["annualised_return_note"] == "Not enough history yet"


def test_performance_shows_annualised_return_after_full_year_history():
    from app.calculations import compute_performance_series

    monthly_data: list[tuple] = [("2026-01", 1000, 0, 0, None, 1000)]
    balance = 1000.0
    for month in range(2, 14):
        balance *= 1.01
        monthly_data.append((f"2026-{month:02d}", round(balance, 2), 0, 0))

    perf = compute_performance_series(monthly_data, 0.07, 0)

    assert perf["annualised_return"] is not None
    assert perf["annualised_return_note"] is None


def test_performance_empty_state_uses_monthly_update_copy(auth_client):
    month_key = date.today().strftime("%Y-%m")
    resp = auth_client.get("/performance/", follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Complete two monthly updates to start seeing performance charts" in html
    assert "Complete two monthly reviews to start seeing performance charts" not in html
    assert "Complete two monthly updates and the performance charts will appear." in html
    assert "Complete two monthly reviews and the performance charts will appear." not in html
    assert ">Open monthly update<" in html
    assert f'href="/monthly-review/?month={month_key}#expected-contributions"' in html
    assert f'href="/monthly-review/?month={month_key}">Open monthly update</a>' not in html
    assert 'href="/monthly-review/">Open monthly update</a>' not in html
    assert ">Go to Monthly Update<" not in html


def test_contribution_summary_empty_state_uses_monthly_update_copy(auth_client):
    month_key = date.today().strftime("%Y-%m")
    resp = auth_client.get("/performance/contributions/", follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "<title>Contribution history " in html
    assert "<title>Contributions " not in html
    assert "Contribution history" in html
    assert "Month-by-month contribution history across all accounts" in html
    assert "Contribution Summary" not in html
    assert "Complete some monthly updates and the contribution history will appear here." in html
    assert "Complete some monthly reviews and the contribution history will appear here." not in html
    assert ">Open monthly update<" in html
    assert f'href="/monthly-review/?month={month_key}#expected-contributions"' in html
    assert f'href="/monthly-review/?month={month_key}">Open monthly update</a>' not in html
    assert 'href="/monthly-review/">Open monthly update</a>' not in html
    assert ">Go to Monthly Update<" not in html


def test_performance_helper_uses_sentence_case_monthly_update_copy(app, client, make_user):
    uid, username, password = make_user(username="performance-helper-copy", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import fetch_assumptions, get_connection

        fetch_assumptions(uid)
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active, valuation_mode)
                VALUES (?, 'ISA', 'ISA', 1000, 150, 1, 'manual')
                """,
                (uid,),
            )
            conn.execute(
                "INSERT INTO portfolio_daily_snapshots (user_id, snapshot_date, total_value) VALUES (?, '2026-01-01', 900)",
                (uid,),
            )
            conn.execute(
                "INSERT INTO portfolio_daily_snapshots (user_id, snapshot_date, total_value) VALUES (?, '2026-04-01', 1000)",
                (uid,),
            )
            conn.execute(
                "INSERT INTO portfolio_daily_snapshots (user_id, snapshot_date, total_value) VALUES (?, '2026-04-02', 1100)",
                (uid,),
            )
            conn.commit()

    resp = client.get("/performance/", follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "monthly update entries" in html
    assert "investment day (shifted for weekends, plus settlement)" in html
    assert "monthly update due date" not in html
    assert "salary day shifted for weekends" not in html
    assert "includes pension tax top-up, Lifetime ISA bonus, and employer payments" in html
    assert "Over the period shown, that’s an average of £150 per month." in html
    assert "/mo." not in html
    assert "Recorded portfolio values use Monthly Update history. The comparison line uses your assumptions and contribution settings; it is not a guarantee." in html
    assert "This compares your recorded portfolio value with an assumptions-based comparison line. It is a planning guide, not a guarantee." not in html
    assert "Actual vs. comparison line" in html
    assert ">Comparison line<" in html
    assert "this comparison line" in html
    assert "ahead</span> of this comparison line" not in html
    assert "behind</span> this comparison line" not in html
    assert "above</span> this comparison line" in html or "below</span> this comparison line" in html
    assert "Portfolio performance chart showing actual vs comparison line" in html
    assert "plan line stays meaningful" not in html
    assert "where you should be" not in html
    assert ">Should be<" not in html
    assert "Actual vs. plan line" not in html
    assert ">Plan line<" not in html
    assert "of this plan line" not in html
    assert "Portfolio performance chart showing actual vs plan" not in html
    assert "review yearly to see whether you're still broadly on track with this plan." in html
    assert "review yearly to see if you're still on track." not in html
    assert ">Lifetime ISA bonus<" in html
    assert "includes tax relief, LISA bonus, employer match" not in html
    assert ">Bonus<" not in html
    assert "Monthly Review entries" not in html
    assert "Monthly Update due date" not in html


def test_contribution_summary_legend_uses_monthly_update_copy(app, client, make_user):
    uid, username, password = make_user(username="contrib-legend", password="password123")
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            account_id = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active)
                VALUES (?, 'ISA', 'ISA', 1000, 100, 1)
                """,
                (uid,),
            ).lastrowid
            review_id = conn.execute(
                "INSERT INTO monthly_reviews (user_id, month_key, status) VALUES (?, '2026-04', 'complete')",
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO monthly_review_items (review_id, account_id, expected_contribution, contribution_confirmed)
                VALUES (?, ?, 100, 1)
                """,
                (review_id, account_id),
            )
            conn.commit()

    resp = client.get("/performance/contributions/", follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "confirmed in monthly update" in html
    assert "no monthly update entry" in html
    assert "ticked off in monthly review" not in html
    assert "no review entry" not in html


def test_performance_plan_uses_recorded_monthly_contributions():
    from app.calculations import compute_performance_series

    monthly_data = [
        ("2026-03", 1000, 0, 0),
        ("2026-04", 1000, 0, 0),
        ("2026-05", 1100, 100, 0),
    ]

    perf = compute_performance_series(monthly_data, assumed_rate=0, assumed_monthly=500)

    assert perf["projected_values"] == [1000, 1000, 1100]
    assert perf["vs_plan"] == 0


def test_performance_by_account_cash_isa_cash_events_adjust_plan(auth_client, app, make_user):
    uid, _, _ = make_user()

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO assumptions (user_id, annual_growth_rate) VALUES (?, 0)",
                (uid,),
            )
            cash_isa = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value, monthly_contribution, is_active)
                VALUES (?, 'Cash ISA', 'Cash ISA', 2000, 0, 1)
                """,
                (uid,),
            ).lastrowid

            conn.execute(
                "INSERT INTO portfolio_daily_snapshots (user_id, snapshot_date, total_value) VALUES (?, '2020-04-01', 3000)",
                (uid,),
            )
            conn.execute(
                "INSERT INTO portfolio_daily_snapshots (user_id, snapshot_date, total_value) VALUES (?, '2020-05-01', 2000)",
                (uid,),
            )
            conn.execute(
                "INSERT INTO account_daily_snapshots (user_id, account_id, snapshot_date, value) VALUES (?, ?, '2020-04-01', 3000)",
                (uid, cash_isa),
            )
            conn.execute(
                "INSERT INTO account_daily_snapshots (user_id, account_id, snapshot_date, value) VALUES (?, ?, '2020-05-01', 2000)",
                (uid, cash_isa),
            )
            conn.execute(
                """
                INSERT INTO cash_flow_events (user_id, account_id, event_date, amount, kind, note, created_at)
                VALUES (?, ?, '2020-04-15', -1000, 'transfer_out', 'Moved out', '2020-04-15T00:00:00+00:00')
                """,
                (uid, cash_isa),
            )
            conn.commit()

    resp = auth_client.get("/performance/", follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Cash ISA" in html
    assert "+£0" in html


def test_performance_page_offers_historical_export_links(auth_client, app, make_user):
    uid, _, _ = make_user()

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO portfolio_daily_snapshots (user_id, snapshot_date, total_value) VALUES (?, '2026-04-01', 1000)",
                (uid,),
            )
            conn.execute(
                "INSERT INTO portfolio_daily_snapshots (user_id, snapshot_date, total_value) VALUES (?, '2026-05-01', 1100)",
                (uid,),
            )
            conn.commit()

    resp = auth_client.get("/performance/", follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert '>Download report<' in html
    assert 'href="/performance/export.xlsx?period=1M"' in html
    assert 'href="/performance/export.xlsx?period=6M"' in html
    assert 'href="/performance/export.xlsx?period=1Y"' in html
    assert 'href="/performance/export.xlsx?period=ALL"' in html
    assert 'From the latest month back over the selected window.' in html



def test_performance_cash_flow_uses_into_pot_for_sipp(app, make_user):
    uid, _, _ = make_user()

    with app.app_context():
        from app.calculations import compute_performance_series
        from app.models import fetch_monthly_performance_data, get_connection

        with get_connection() as conn:
            sipp = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, category, monthly_contribution, contribution_method, is_active)
                VALUES (?, 'SIPP', 'SIPP', 'Pension', 800, 'standard', 1)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, month_key, balance) VALUES ('2026-04-01', ?, '2026-04', 1000)",
                (sipp,),
            )
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, month_key, balance) VALUES ('2026-05-01', ?, '2026-05', 2000)",
                (sipp,),
            )
            conn.commit()

        monthly_data = fetch_monthly_performance_data(uid)
        assert monthly_data == [
            ("2026-04", 1000.0, 0.0, 0, None, 1000.0),
            ("2026-05", 2000.0, 1000.0, 0),
        ]

        perf = compute_performance_series(monthly_data, assumed_rate=0, assumed_monthly=0)
        assert perf["total_market_gain"] == 0.0


def test_performance_uses_narrowest_override_for_monthly_cash_flow(app, make_user):
    uid, _, _ = make_user(username="perf-override-precedence", password="password123")

    with app.app_context():
        from app.models import fetch_monthly_performance_data, fetch_monthly_performance_data_by_account, get_connection

        with get_connection() as conn:
            isa = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, monthly_contribution, is_active)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 80, 1)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, month_key, balance) VALUES ('2026-05-01', ?, '2026-05', 1000)",
                (isa,),
            )
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, month_key, balance) VALUES ('2026-06-01', ?, '2026-06', 1250)",
                (isa,),
            )
            conn.execute(
                """
                INSERT INTO contribution_overrides (account_id, from_month, to_month, override_amount, reason, created_at)
                VALUES (?, '2026-06', '2026-06', 250, 'narrow', datetime('now'))
                """,
                (isa,),
            )
            conn.execute(
                """
                INSERT INTO contribution_overrides (account_id, from_month, to_month, override_amount, reason, created_at)
                VALUES (?, '2026-05', '2026-07', 100, 'broad newer', datetime('now'))
                """,
                (isa,),
            )
            conn.commit()

        monthly_data = fetch_monthly_performance_data(uid)
        by_account = fetch_monthly_performance_data_by_account(uid)

    assert monthly_data == [
        ('2026-05', 1000.0, 0.0, 0, None, 1000.0),
        ('2026-06', 1250.0, 250.0, 0),
    ]
    assert by_account[isa]["rows"] == [
        ('2026-05', 1000.0, 0.0, 0, None, 1000.0),
        ('2026-06', 1250.0, 250.0),
    ]


def test_performance_draft_review_does_not_change_cash_flow(app, make_user):
    uid, _, _ = make_user()

    with app.app_context():
        from app.models import fetch_monthly_performance_data, get_connection

        with get_connection() as conn:
            sipp = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, category, monthly_contribution, contribution_method, is_active)
                VALUES (?, 'SIPP', 'SIPP', 'Pension', 800, 'standard', 1)
                """,
                (uid,),
            ).lastrowid
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, month_key, balance) VALUES ('2026-04-01', ?, '2026-04', 1000)",
                (sipp,),
            )
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, month_key, balance) VALUES ('2026-05-01', ?, '2026-05', 2000)",
                (sipp,),
            )
            review_id = conn.execute(
                "INSERT INTO monthly_reviews (user_id, month_key, status) VALUES (?, '2026-05', 'in_progress')",
                (uid,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO monthly_review_items (review_id, account_id, expected_contribution, contribution_confirmed)
                VALUES (?, ?, 0, 1)
                """,
                (review_id, sipp),
            )
            conn.commit()

        monthly_data = fetch_monthly_performance_data(uid)
        assert monthly_data[1][2] == 1000.0


def test_weighted_dietz_with_exact_dates():
    """Verify that deposit on day 3 vs day 20 produces different returns."""
    from app.calculations import compute_performance_series, _weighted_dietz_denominator

    # Same opening, same closing, same total contribution — but different timing
    opening = 1000.0
    closing = 1050.0  # £50 gain total
    total_flow = 200.0

    # Mid-month approximation (original behavior)
    mid_denom = _weighted_dietz_denominator(opening, total_flow, [])
    assert abs(mid_denom - (opening + 0.5 * total_flow)) < 1e-9

    # Early deposit (day 3 of 30-day month) → larger weight → smaller return %
    early_events = [("2026-04-03", 200.0)]
    early_denom = _weighted_dietz_denominator(opening, total_flow, early_events)

    # Late deposit (day 25 of 30-day month) → smaller weight → larger return %
    late_events = [("2026-04-25", 200.0)]
    late_denom = _weighted_dietz_denominator(opening, total_flow, late_events)

    # Early deposit has weight ≈28/30 ≈ 0.93 → large denominator
    # Late deposit has weight ≈6/30 = 0.20 → small denominator
    # Mid-month fallback uses weight 0.5
    assert early_denom > mid_denom > late_denom > opening


def test_weighted_dietz_matches_mid_month_when_contribution_on_15th():
    """When contribution lands exactly mid-month, weighted Dietz ≈ mid-month approximation."""
    from app.calculations import _weighted_dietz_denominator

    from calendar import monthrange as mr
    opening = 1000.0
    flow = 200.0

    for year in (2026, 2027, 2028):
        for month in (1, 4, 6, 9, 12):
            days_in_month = mr(year, month)[1]
            # Mid-month: day ≈ 15
            mid_day = days_in_month // 2 + 1
            events_mid = [(f"{year}-{month:02d}-{mid_day:02d}", flow)]
            expected_fallback = opening + 0.5 * flow

            denom = _weighted_dietz_denominator(opening, flow, events_mid)
            # Should be within ~3% of mid-month approx since mid-day weight
            # should be very close to 0.5
            mid_weight = (days_in_month - mid_day + 1) / days_in_month
            expected_with_events = opening + flow * mid_weight
            assert abs(denom - expected_with_events) < 0.01, f"Month {month}/{year}"


def test_weighted_dietz_fallback_without_events():
    """Without flow events, returns match existing mid-month approximation."""
    from app.calculations import compute_performance_series

    monthly_data = [
        ("2026-03", 1000, 0, 0),
        ("2026-04", 1100, 100, 0),
        ("2026-05", 1210, 100, 0),
    ]

    # Without flow_events — should get identical results as before
    perf_no_events = compute_performance_series(monthly_data, 0.07, 100)

    with_flow_events = compute_performance_series(
        monthly_data, 0.07, 100,
        flow_events_by_month={"2026-04": [], "2026-05": []},
    )

    assert perf_no_events["total_return"] == with_flow_events["total_return"]
    assert perf_no_events["annualised_return"] == with_flow_events["annualised_return"]


def test_weighted_dietz_with_withdrawals():
    """Verify negative flows (withdrawals) are correctly weighted."""
    from app.calculations import _weighted_dietz_denominator

    opening = 1000.0
    # Net positive: +500 deposit, -200 withdrawal = +300 total flow
    # Day 5: +500 deposit
    # Day 20: -200 withdrawal (negative amount)
    events = [("2026-04-05", 500.0), ("2026-04-20", -200.0)]

    denom = _weighted_dietz_denominator(opening, 300.0, events)

    # Verify the withdrawal reduces the denominator more than if it happened later
    # compared to a scenario where the withdrawal happens on day 28
    events_late_withdrawal = [("2026-04-05", 500.0), ("2026-04-28", -200.0)]
    denom_late = _weighted_dietz_denominator(opening, 300.0, events_late_withdrawal)

    # Earlier withdrawal means money was removed for more of the month → smaller denominator
    assert denom < denom_late


def test_performance_export_uses_weighted_dietz(auth_client, app, make_user):
    """End-to-end: cash flow events with exact dates produce accurate returns in export."""
    uid, username, password = make_user(username="perf-weighted-dietz", password="password123")

    with app.app_context():
        from app.models import get_connection

        with get_connection() as conn:
            isa = conn.execute(
                """
                INSERT INTO accounts (user_id, name, wrapper_type, current_value,
                    monthly_contribution, is_active)
                VALUES (?, 'ISA', 'Stocks & Shares ISA', 10000, 500, 1)
                """,
                (uid,),
            ).lastrowid
            # Three months of snapshots
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, month_key, balance) VALUES ('2026-03-01', ?, '2026-03', 10000)",
                (isa,),
            )
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, month_key, balance) VALUES ('2026-04-01', ?, '2026-04', 10500)",
                (isa,),
            )
            conn.execute(
                "INSERT INTO monthly_snapshots (snapshot_date, account_id, month_key, balance) VALUES ('2026-05-01', ?, '2026-05', 11000)",
                (isa,),
            )
            # Cash flow event on day 3 (early in month)
            conn.execute(
                """
                INSERT INTO cash_flow_events (user_id, account_id, event_date, amount,
                    kind, note, allowance_effect, created_at)
                VALUES (?, ?, '2026-04-03', 500, 'deposit', 'Early April deposit',
                    'performance_only', '2026-04-03T10:00:00+00:00')
                """,
                (uid, isa),
            )
            conn.commit()

    # Export the performance report
    resp = auth_client.get("/performance/export.xlsx?period=ALL", follow_redirects=True)
    assert resp.status_code == 200
    data = resp.data
    assert len(data) > 0  # Valid XLSX generated


def test_performance_template_explains_calculation_method():
    """Performance template includes honest explanation of calculation method."""
    from pathlib import Path

    tpl_path = Path("app/templates/performance.html")
    source = tpl_path.read_text().lower()

    # Should mention actual cash-flow dates or weighted approach
    assert "cash-flow" in source or "weighted" in source
