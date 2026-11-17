"""A line's unit: how its quantity reads to the customer (`2.5 hrs.`).

A fixed pair for now, Hour and Each, stored as a short code. A flat-rate
line is just one Each (`1 ea.`). Showing the unit is text out, kept here
as amounts and dates keep theirs.
"""

from decimal import Decimal

HOUR = "hour"
EACH = "each"
DEFAULT = EACH  # a hand-typed line starts here
UNITS = (EACH, HOUR)  # the allowed codes

# code -> (singular, plural); `ea.` doesn't inflect.
_LABELS = {
    EACH: ("ea.", "ea."),
    HOUR: ("hr.", "hrs."),
}

# What the Unit picker shows for a code, in the editor and the catalog.
CHOICES = {EACH: "Each", HOUR: "Hour"}


def unit_label(unit: str, quantity: Decimal) -> str:
    """`hr.` for exactly one, `hrs.` for any other count; `ea.` either way."""
    singular, plural = _LABELS[unit]
    return singular if quantity == 1 else plural


def format_quantity(quantity: Decimal, unit: str) -> str:
    """A quantity with its unit: `2.5 hrs.`, `1 ea.`."""
    return f"{quantity} {unit_label(unit, quantity)}"
