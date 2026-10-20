"""Reading and showing dates typed by the user, and the dates a quote
is valid through.

A quote's valid-through date is the last day it's good, inclusive: one
valid through 11/18/2026 expires on 11/19/2026.
"""

from datetime import date, datetime, timedelta

# How long a quote is good for unless the user picks another date: a
# new business's setting until changed.
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


def default_valid_until(issued_on: date, days: int) -> date:
    """`days` after the date issued."""
    return issued_on + timedelta(days=days)


def parse_days(text: str) -> int:
    """A number of days, a whole number above zero: `30`.

    Raises ValueError, with a message for the user, for anything else.
    """
    cleaned = text.strip()
    # isascii too: isdigit is also true for "²", which int() refuses.
    if not (cleaned.isascii() and cleaned.isdigit()) or int(cleaned) == 0:
        raise ValueError("Days must be a whole number above 0, like 30")
    return int(cleaned)


def extended_until(valid_until: date, today: date, days: int) -> date:
    """`days` more than the quote's valid-through date, or than today if
    that's already past, so an expired quote still gets the full time."""
    return max(valid_until, today) + timedelta(days=days)
