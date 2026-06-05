from app.calculations import apply_pension_carry_forward


def test_apply_pension_carry_forward_adds_first_three_entries_when_mpaa_disabled():
    result = apply_pension_carry_forward(
        {
            "effective_allowance": 60000,
            "personal_relief_limit": 3600,
            "mpaa_enabled": False,
        },
        [
            {"unused_allowance": 1000},
            {"unused_allowance": "2000"},
            {"unused_allowance": 500},
            {"unused_allowance": 9999},
        ],
    )

    assert result["effective_allowance"] == 63500
    assert result["carry_forward_total"] == 3500
    assert result["personal_relief_limit"] == 3600


def test_apply_pension_carry_forward_does_not_inflate_mpaa_limit():
    result = apply_pension_carry_forward(
        {
            "effective_allowance": 10000,
            "personal_relief_limit": 3600,
            "mpaa_enabled": True,
        },
        [
            {"unused_allowance": 1000},
            {"unused_allowance": 2000},
            {"unused_allowance": 3000},
        ],
    )

    assert result["effective_allowance"] == 10000
    assert result["carry_forward_total"] == 0
    assert result["personal_relief_limit"] == 3600
