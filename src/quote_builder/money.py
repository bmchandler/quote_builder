"""Reading and showing amounts typed by the user.

Text goes straight to Decimal, never through float, which can't hold
most cents exactly (0.1 + 0.2 != 0.3).
"""

from decimal import Decimal, InvalidOperation


def parse_money(text: str) -> int:
    """Whole cents from a dollar amount such as `45`, `$45.50`, `1,234.5`.

    Raises ValueError, with a message for the user, for anything else.
    """
    cleaned = text.strip().removeprefix("$").replace(",", "")
    if not cleaned:
        raise ValueError("An amount is needed")
    amount = _decimal(cleaned, f"{text.strip()!r} isn't an amount")
    if amount < 0:
        raise ValueError("An amount can't be negative")
    if amount.as_tuple().exponent < -2:
        raise ValueError(f"{text.strip()!r} has more than two decimal places")
    return int(amount * 100)


def format_money(cents: int) -> str:
    """`$1,234.50` for 123450 cents; `-$7.50` for -750."""
    sign = "-" if cents < 0 else ""
    return f"{sign}${Decimal(abs(cents)) / 100:,.2f}"


def parse_quantity(text: str) -> Decimal:
    """A quantity above zero, such as `1` or `2.5`.

    Raises ValueError, with a message for the user, for anything else.
    """
    quantity = _decimal(text.strip(), f"{text.strip()!r} isn't a quantity")
    if quantity <= 0:
        raise ValueError("A quantity must be more than zero")
    return quantity


def parse_percent(text: str) -> Decimal:
    """A percent from 0 to 100, such as `7.25` or `7.25%`; blank is 0.

    Raises ValueError, with a message for the user, for anything else.
    """
    cleaned = text.strip().removesuffix("%").strip()
    if not cleaned:
        return Decimal(0)
    percent = _decimal(cleaned, f"{text.strip()!r} isn't a percent")
    if not 0 <= percent <= 100:
        raise ValueError("A percent must be between 0 and 100")
    return percent


def format_percent(percent: Decimal) -> str:
    """`7.25` for a percent field; blank for 0."""
    return "" if percent == 0 else str(percent)


def parse_discount(text: str) -> tuple[int | None, Decimal | None]:
    """A discount as (cents, None) or (None, percent); (None, None) if none.

    `10%` is a percent, anything else an amount (`5`, `$5.50`). Blank or
    zero is no discount. Raises ValueError, with a message for the user.
    """
    cleaned = text.strip()
    if cleaned.endswith("%"):
        percent = parse_percent(cleaned)
        return (None, percent) if percent else (None, None)
    if not cleaned:
        return (None, None)
    cents = parse_money(cleaned)
    return (cents, None) if cents else (None, None)


def format_discount(cents: int | None, percent: Decimal | None) -> str:
    """`$5.50` or `12.5%` for the discount field; blank if none."""
    if percent is not None:
        return f"{percent}%"
    if cents is not None:
        return format_money(cents)
    return ""


def _decimal(text: str, message: str) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(message) from None
    # Decimal also reads "NaN" and "Infinity".
    if not value.is_finite():
        raise ValueError(message)
    return value
