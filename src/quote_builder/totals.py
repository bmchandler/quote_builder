"""What a line and a quote add up to.

Each line is worked out to the cent on its own: amount, then discount,
then tax on what's left. The quote's totals add up the lines' cents, so
the foot of a quote always matches its lines. Rounding is half up
(half a cent rounds up), as people expect on a bill, not Python's
default half even (banker's rounding).

Once quoted, a quote's figures are frozen (stored with it) and shown
from then on, so a later change here never changes what a client was
given.
"""

from collections.abc import Iterable
from dataclasses import replace
from decimal import ROUND_HALF_UP, Decimal

from quote_builder.quotes import LineItem, LineTotals, Quote, QuoteTotals


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


def freeze(quote: Quote) -> Quote:
    """A copy with each line's figures and the foot's stored on it.

    Raises ValueError if a discount is more than its line.
    """
    lines = [replace(item, frozen=line_totals(item)) for item in quote.line_items]
    return replace(quote, line_items=lines, frozen=quote_totals(quote.line_items))


def shown_line_totals(item: LineItem) -> LineTotals:
    """The line's frozen figures once quoted, else worked out now."""
    return item.frozen or line_totals(item)


def shown_quote_totals(quote: Quote) -> QuoteTotals:
    """The quote's frozen foot once quoted, else worked out now."""
    return quote.frozen or quote_totals(quote.line_items)


def _whole_cents(cents: Decimal | int) -> int:
    return int(Decimal(cents).quantize(Decimal(1), rounding=ROUND_HALF_UP))
