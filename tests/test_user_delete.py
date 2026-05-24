"""User deletion regression tests."""


def test_delete_user_removes_linked_data_without_foreign_key_error(app, make_user):
    """Deleting a user with common linked rows should remove only that user."""
    from app.models import delete_user

    with app.app_context():
        from app.models import get_connection

        admin_id, _, _ = make_user(username="admin-delete-owner", is_admin=True)
        target_id, _, _ = make_user(username="old-janusz", is_admin=False)
        other_id, _, _ = make_user(username="kept-user", is_admin=False)

        with get_connection() as conn:
            target_account = conn.execute(
                "INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active) VALUES (?, 'Old ISA', 'isa', 1000, 1)",
                (target_id,),
            ).lastrowid
            other_account = conn.execute(
                "INSERT INTO accounts (user_id, name, wrapper_type, current_value, is_active) VALUES (?, 'Keep ISA', 'isa', 2000, 1)",
                (other_id,),
            ).lastrowid
            target_catalogue = conn.execute(
                "INSERT INTO holding_catalogue (user_id, holding_name, ticker, is_active) VALUES (?, 'Old Fund', 'OLD', 1)",
                (target_id,),
            ).lastrowid
            other_catalogue = conn.execute(
                "INSERT INTO holding_catalogue (user_id, holding_name, ticker, is_active) VALUES (?, 'Keep Fund', 'KEEP', 1)",
                (other_id,),
            ).lastrowid
            conn.execute(
                "INSERT INTO holdings (account_id, holding_catalogue_id, holding_name, value) VALUES (?, ?, 'Old Fund', 1000)",
                (target_account, target_catalogue),
            )
            conn.execute(
                "INSERT INTO holdings (account_id, holding_catalogue_id, holding_name, value) VALUES (?, ?, 'Keep Fund', 2000)",
                (other_account, other_catalogue),
            )
            target_review = conn.execute(
                "INSERT INTO monthly_reviews (user_id, month_key, status) VALUES (?, '2026-05', 'draft')",
                (target_id,),
            ).lastrowid
            conn.execute(
                "INSERT INTO monthly_review_items (review_id, account_id, expected_contribution) VALUES (?, ?, 100)",
                (target_review, target_account),
            )
            target_budget_item = conn.execute(
                "INSERT INTO budget_items (user_id, name, section, default_amount) VALUES (?, 'Old Budget', 'bills', 50)",
                (target_id,),
            ).lastrowid
            conn.execute(
                "INSERT INTO budget_entries (month_key, budget_item_id, amount) VALUES ('2026-05', ?, 50)",
                (target_budget_item,),
            )
            conn.execute(
                "INSERT INTO cash_flow_events (user_id, account_id, event_date, amount, kind) VALUES (?, ?, '2026-05-01', 25, 'transfer')",
                (target_id, target_account),
            )
            conn.execute(
                "INSERT INTO premium_bonds_prizes (user_id, account_id, month_key, prize_amount) VALUES (?, ?, '2026-05', 25)",
                (target_id, target_account),
            )
            conn.execute(
                "INSERT INTO hidden_tags (user_id, tag) VALUES (?, 'hide-me')",
                (target_id,),
            )
            conn.commit()

        ok, err = delete_user(target_id)
        assert ok is True
        assert err is None

        with get_connection() as conn:
            assert conn.execute("SELECT COUNT(*) AS c FROM users WHERE id = ?", (target_id,)).fetchone()["c"] == 0
            assert conn.execute("SELECT COUNT(*) AS c FROM accounts WHERE user_id = ?", (target_id,)).fetchone()["c"] == 0
            assert conn.execute("SELECT COUNT(*) AS c FROM holding_catalogue WHERE user_id = ?", (target_id,)).fetchone()["c"] == 0
            assert conn.execute("SELECT COUNT(*) AS c FROM monthly_reviews WHERE user_id = ?", (target_id,)).fetchone()["c"] == 0
            assert conn.execute("SELECT COUNT(*) AS c FROM budget_items WHERE user_id = ?", (target_id,)).fetchone()["c"] == 0
            assert conn.execute("SELECT COUNT(*) AS c FROM cash_flow_events WHERE user_id = ?", (target_id,)).fetchone()["c"] == 0
            assert conn.execute("SELECT COUNT(*) AS c FROM premium_bonds_prizes WHERE user_id = ?", (target_id,)).fetchone()["c"] == 0
            assert conn.execute("SELECT COUNT(*) AS c FROM hidden_tags WHERE user_id = ?", (target_id,)).fetchone()["c"] == 0

            assert conn.execute("SELECT COUNT(*) AS c FROM users WHERE id = ?", (admin_id,)).fetchone()["c"] == 1
            assert conn.execute("SELECT COUNT(*) AS c FROM users WHERE id = ?", (other_id,)).fetchone()["c"] == 1
            assert conn.execute("SELECT COUNT(*) AS c FROM accounts WHERE user_id = ?", (other_id,)).fetchone()["c"] == 1
            assert conn.execute("SELECT COUNT(*) AS c FROM holdings WHERE account_id = ?", (other_account,)).fetchone()["c"] == 1
