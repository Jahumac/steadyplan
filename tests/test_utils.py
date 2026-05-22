from app.utils import valid_month_key


def test_valid_month_key_accepts_real_month():
    assert valid_month_key("2026-04") == "2026-04"


def test_valid_month_key_rejects_impossible_month():
    assert valid_month_key("2026-13") is None
    assert valid_month_key("2026-00") is None


def test_valid_month_key_rejects_extra_trailing_text():
    assert valid_month_key("2026-04-extra") is None
