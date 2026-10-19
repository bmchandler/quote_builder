"""What a line and a quote add up to.

Each line is worked out to the cent on its own: amount, then discount,
then tax on what's left. The quote's totals add up the lines' cents, so
the foot of a quote always matches its lines. Rounding is half up
(half a cent rounds up), as people expect on a bill, not Python's
default half even (banker's rounding).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from quote_builder.quotes import LineItem


@dataclass(frozen=True)
class LineTotals:
    amount_cents: int  # quantity × unit price
    discount_cents: int
    tax_cents: int

    @property
    def net_cents(self) -> int:
        """The amount after the discount, before tax."""
        return self.amount_cents - self.discount_cents

    @property
    def total_cents(self) -> int:
        return self.net_cents + self.tax_cents


@dataclass(frozen=True)
class QuoteTotals:
    items_cents: int  # the lines' amounts, before discounts
    discount_cents: int
    tax_cents: int
    total_cents: int


def line_totals(item: LineItem) -> LineTotals:
    """Raises ValueError if the discount is more than the line."""
    amount = _whole_cents(item.quantity * item.unit_price_cents)
    if item.discount_percent is not None:
        discount = _whole_cents(amount * item.discount_percent / 100)
    else:
        discount = item.discount_cents or 0
    if discount > amount:
        raise ValueError("A discount can't be more than the line")
    tax = _whole_cents((amount - discount) * item.tax_percent / 100)
    return LineTotals(amount, discount, tax)


def quote_totals(items: Iterable[LineItem]) -> QuoteTotals:
    lines = [line_totals(item) for item in items]
    return QuoteTotals(
        items_cents=sum(line.amount_cents for line in lines),
        discount_cents=sum(line.discount_cents for line in lines),
        tax_cents=sum(line.tax_cents for line in lines),
        total_cents=sum(line.total_cents for line in lines),
    )


def _whole_cents(cents: Decimal | int) -> int:
    return int(Decimal(cents).quantize(Decimal(1), rounding=ROUND_HALF_UP))
