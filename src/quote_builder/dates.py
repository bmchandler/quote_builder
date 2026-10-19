"""Reading and showing dates typed by the user, and the default
valid-until date."""

from datetime import date, timedelta

# How long a quote is good for unless the user picks another date. The
# business profile can make this a setting later.
VALID_DAYS = 30


def parse_date(text: str) -> date:
    """A date written as `2026-11-18`, as the date picker fills it in.

    Raises ValueError, with a message for the user, for anything else.
    """
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("A date is needed")
    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        raise ValueError(f"{cleaned!r} isn't a date like 2026-11-18") from None


def format_date(day: date) -> str:
    """`Oct 19, 2026`."""
    return f"{day:%b} {day.day}, {day.year}"


def default_valid_until(issued_on: date) -> date:
    return issued_on + timedelta(days=VALID_DAYS)
