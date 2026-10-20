"""Reading and showing dates typed by the user, and the dates a quote
is valid through.

A quote's valid-through date is the last day it's good, inclusive: one
valid through 11/18/2026 expires on 11/19/2026.
"""

from datetime import date, datetime, timedelta

# How long a quote is good for unless the user picks another date. The
# business profile can make this a setting later.
VALID_DAYS = 30


def parse_date(text: str) -> date:
    """A date written as `11/18/2026`, as the date picker fills it in,
    or `2026-11-18`.

    Raises ValueError, with a message for the user, for anything else.
    """
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("A date is needed")
    try:
        return datetime.strptime(cleaned, "%m/%d/%Y").date()
    except ValueError:
        pass
    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        raise ValueError(f"{cleaned!r} isn't a date like 11/18/2026") from None


def format_date(day: date) -> str:
    """`Oct 19, 2026`, as the quote list shows dates."""
    return f"{day:%b} {day.day}, {day.year}"


def format_numeric_date(day: date) -> str:
    """`11/18/2026`, as a quote shows its dates."""
    return f"{day:%m/%d/%Y}"


def default_valid_until(issued_on: date) -> date:
    return issued_on + timedelta(days=VALID_DAYS)


def extended_until(valid_until: date, today: date, days: int) -> date:
    """`days` more than the quote's valid-through date, or than today if
    that's already past, so an expired quote still gets the full time."""
    return max(valid_until, today) + timedelta(days=days)
