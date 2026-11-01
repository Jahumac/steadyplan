"""Pension annual allowance limits.

Carry-forward was removed as an unused ledger (v15), so the effective allowance is now
simply the annual allowance — or the MPAA when that is enabled. These tests keep the
MPAA rule pinned: removing carry-forward must never let the allowance exceed the cap.
"""
from app.calculations import pension_allowance_limits


def test_default_allowance_is_60000():
    assert pension_allowance_limits({})["effective_allowance"] == 60000


def test_annual_allowance_override_is_respected():
    assert pension_allowance_limits(
        {"pension_annual_allowance": 40000}
    )["effective_allowance"] == 40000


def test_mpaa_caps_the_effective_allowance():
    limits = pension_allowance_limits(
        {"pension_annual_allowance": 60000, "mpaa_enabled": 1, "mpaa_allowance": 10000}
    )
    assert limits["effective_allowance"] == 10000
    assert limits["mpaa_enabled"] is True


def test_mpaa_does_not_raise_a_lower_annual_allowance():
    limits = pension_allowance_limits(
        {"pension_annual_allowance": 8000, "mpaa_enabled": 1, "mpaa_allowance": 10000}
    )
    assert limits["effective_allowance"] == 8000


def test_carry_forward_is_gone_from_the_calculations_module():
    """It was deleted with the ledger that fed it — it must not come back by accident."""
    import app.calculations as calc

    assert not hasattr(calc, "apply_pension_carry_forward")
