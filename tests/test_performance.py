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
            ("2026-03", 62011.0, 0.0, 0),
            ("2026-04", 62011.0, 0.0, 1),
        ]

        perf = compute_performance_series(monthly_data, 0.07, 0)
        assert perf["total_return"] == 0.0
        assert perf["total_market_gain"] == 0.0
        assert perf["carried_forward_months"] == 1


def test_performance_empty_state_uses_monthly_update_copy(auth_client):
    resp = auth_client.get("/performance/", follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Complete two monthly updates to start seeing performance charts" in html
    assert "Complete two monthly reviews to start seeing performance charts" not in html
    assert "Complete two monthly updates and the performance charts will appear." in html
    assert "Complete two monthly reviews and the performance charts will appear." not in html
    assert ">Open monthly update<" in html
    assert ">Go to Monthly Update<" not in html


def test_contribution_summary_empty_state_uses_monthly_update_copy(auth_client):
    resp = auth_client.get("/performance/contributions/", follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Complete some monthly updates and the contribution history will appear here." in html
    assert "Complete some monthly reviews and the contribution history will appear here." not in html
    assert ">Open monthly update<" in html
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
    assert "monthly update due date" in html
    assert "includes tax relief, Lifetime ISA bonus, employer match" in html
    assert "This compares your recorded portfolio value with an assumptions-based plan line. It is a planning guide, not a guarantee." in html
    assert "Actual vs. plan line" in html
    assert ">Plan line<" in html
    assert "of this plan line" in html
    assert "where you should be" not in html
    assert ">Should be<" not in html
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
            ("2026-04", 1000.0, 1000.0, 0),
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
        ('2026-05', 1000.0, 100.0, 0),
        ('2026-06', 1250.0, 250.0, 0),
    ]
    assert by_account[isa]["rows"] == [
        ('2026-05', 1000.0, 100.0),
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
