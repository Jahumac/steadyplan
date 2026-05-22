"""Shared utility helpers used across route modules."""
import re
from datetime import date

_MONTH_KEY_RE = re.compile(r"^\d{4}-\d{2}$")
_TAX_YEAR_RE = re.compile(r"^(\d{4})-(\d{2})$")


def split_tags(tags_value):
    """Split a comma-separated tag string into a list of stripped, non-empty tags."""
    return [tag.strip() for tag in (tags_value or "").split(",") if tag.strip()]


def optional_float(value, default=None, divide_by_100=False, min_val=None):
    """Parse a string or numeric value to float, returning `default` on failure."""
    value = (str(value) if value is not None else "").strip()
    if value == "":
        return default
    try:
        result = float(value)
    except (ValueError, TypeError):
        return default
    if divide_by_100:
        result = result / 100.0
    if min_val is not None:
        result = max(min_val, result)
    return result


def optional_int(value, default=None):
    """Parse a string or numeric value to int, returning `default` on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def valid_month_key(raw):
    """Return raw if it is a real YYYY-MM calendar month, else None."""
    s = (raw or "").strip()
    if not _MONTH_KEY_RE.fullmatch(s):
        return None
    try:
        year, month = s.split("-")
        date(int(year), int(month), 1)
    except (TypeError, ValueError):
        return None
    return s


def valid_date(raw):
    """Return raw if it parses as a calendar YYYY-MM-DD date, else None."""
    s = (raw or "").strip()
    if not s:
        return None
    try:
        date.fromisoformat(s)
    except (ValueError, TypeError):
        return None
    return s


def valid_tax_year(raw):
    """Return raw if it's a UK tax year like 2023-24 (YY = (YYYY+1) mod 100), else None."""
    s = (raw or "").strip()
    m = _TAX_YEAR_RE.match(s)
    if not m:
        return None
    if (int(m.group(1)) + 1) % 100 != int(m.group(2)):
        return None
    return s
