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
    amount = _decimal(cleaned, f"{text.strip()!r} isn't an amount")
    if amount < 0:
        raise ValueError("An amount can't be negative")
    if amount.as_tuple().exponent < -2:
        raise ValueError(f"{text.strip()!r} has more than two decimal places")
    return int(amount * 100)


def format_money(cents: int) -> str:
    """`$1,234.50` for 123450 cents."""
    return f"${Decimal(cents) / 100:,.2f}"


def parse_quantity(text: str) -> Decimal:
    """A quantity above zero, such as `1` or `2.5`.

    Raises ValueError, with a message for the user, for anything else.
    """
    quantity = _decimal(text.strip(), f"{text.strip()!r} isn't a quantity")
    if quantity <= 0:
        raise ValueError("A quantity must be more than zero")
    return quantity


def _decimal(text: str, message: str) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(message) from None
    # Decimal also reads "NaN" and "Infinity".
    if not value.is_finite():
        raise ValueError(message)
    return value
