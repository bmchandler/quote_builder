"""What a line and a quote add up to.

Each line is worked out to the cent on its own: amount, then discount,
then tax on what's left. The quote's totals add up the lines' cents, so
the foot of a quote always matches its lines. Rounding is half up
(half a cent rounds up), as people expect on a bill, not Python's
default half even (banker's rounding).

Once quoted, a quote's figures are frozen (stored with it) and shown
from then on, so a later change here never changes what a customer was
given.
"""

from collections.abc import Iterable
from dataclasses import replace
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from quote_builder.quotes import (
    LineItem,
    LineTotals,
    Quote,
    QuoteDiscountSplit,
    QuoteTotals,
)

# A quote with both a line discount and a whole-quote discount set; the
# app blocks saving one, and totals refuse to work one out.
BOTH_MODES = "A quote can use line discounts or a Quote Discount, not both"


def line_amount_cents(item: LineItem) -> int:
    """A line's amount before any discount: quantity × unit price."""
    return _whole_cents(item.quantity * item.unit_price_cents)


def line_totals(item: LineItem, tax_percent: Decimal) -> LineTotals:
    """The line's figures, taxed at `tax_percent` (the quote's rate) if
    it's taxed. Raises ValueError if the discount is more than the line."""
    amount = line_amount_cents(item)
    if item.discount_percent is not None:
        discount = _whole_cents(amount * item.discount_percent / 100)
    else:
        discount = item.discount_cents or 0
    if discount > amount:
        raise ValueError("A discount can't be more than the line")
    percent = tax_percent if item.taxed else Decimal(0)
    tax = _whole_cents((amount - discount) * percent / 100)
    return LineTotals(amount, discount, tax)


def quote_totals(
    items: Iterable[LineItem],
    tax_percent: Decimal,
    quote_discount_cents: int | None = None,
    quote_discount_percent: Decimal | None = None,
) -> QuoteTotals:
    """The quote's foot. Without a quote discount, each line is taxed on
    its own (today's way). With one, the lines carry no discount of their
    own, the quote discount comes off the subtotal before tax, split
    across the taxable and non-taxable lines by their share of it, and tax
    falls on what's left of the taxable part. See CALCULATIONS.md.

    Raises ValueError if a line discount is more than its line, if both
    discount modes are used at once, or if a quote discount is more than
    the whole subtotal.
    """
    items = list(items)
    lines = [line_totals(item, tax_percent) for item in items]
    items_cents = sum(line.amount_cents for line in lines)
    line_discount_cents = sum(line.discount_cents for line in lines)
    if quote_discount_cents is None and quote_discount_percent is None:
        return QuoteTotals(
            items_cents=items_cents,
            discount_cents=line_discount_cents,
            quote_discount_cents=0,
            tax_cents=sum(line.tax_cents for line in lines),
            total_cents=sum(line.total_cents for line in lines),
        )
    # Quote-discount mode: one mode per quote, so no line discounts.
    if line_discount_cents:
        raise ValueError(BOTH_MODES)
    discount = _quote_discount_cents(
        items_cents, quote_discount_cents, quote_discount_percent
    )
    if discount > items_cents:
        raise ValueError("A Quote Discount can't be more than the quote")
    taxable = sum(
        line.amount_cents for line, item in zip(lines, items) if item.taxed
    )
    taxable_share = _taxable_share(discount, taxable, items_cents)
    tax = _whole_cents((taxable - taxable_share) * tax_percent / 100)
    return QuoteTotals(
        items_cents=items_cents,
        discount_cents=0,
        quote_discount_cents=discount,
        tax_cents=tax,
        total_cents=(items_cents - discount) + tax,
    )


def freeze(quote: Quote) -> Quote:
    """A copy with each line's figures and the foot's stored on it.

    Raises ValueError as quote_totals does.
    """
    percent = quote.tax_percent
    foot = quote_totals(
        quote.line_items,
        percent,
        quote.quote_discount_cents,
        quote.quote_discount_percent,
    )
    if quote.has_quote_discount:
        # A line keeps no discount or tax of its own; its tax lives in the
        # foot, worked out for the quote as a whole.
        lines = [
            replace(item, frozen=LineTotals(line_amount_cents(item), 0, 0))
            for item in quote.line_items
        ]
    else:
        lines = [
            replace(item, frozen=line_totals(item, percent))
            for item in quote.line_items
        ]
    return replace(quote, line_items=lines, frozen=foot)


def shown_line_totals(item: LineItem, tax_percent: Decimal) -> LineTotals:
    """The line's frozen figures once quoted, else worked out now at the
    quote's rate."""
    return item.frozen or line_totals(item, tax_percent)


def shown_quote_totals(quote: Quote) -> QuoteTotals:
    """The quote's frozen foot once quoted, else worked out now."""
    return quote.frozen or quote_totals(
        quote.line_items,
        quote.tax_percent,
        quote.quote_discount_cents,
        quote.quote_discount_percent,
    )


def quote_discount_split(
    items: Iterable[LineItem], totals: QuoteTotals
) -> QuoteDiscountSplit:
    """The quote-discount breakdown shown in the foot: the subtotal after
    the quote discount, split into its non-taxable and taxable parts (tax
    falls on the taxable part). Figured the same way as quote_totals, from
    the lines' plain amounts and the discount in `totals`, so it always
    agrees with the foot's Taxes. See CALCULATIONS.md.
    """
    taxable = sum(line_amount_cents(item) for item in items if item.taxed)
    taxable_share = _taxable_share(
        totals.quote_discount_cents, taxable, totals.items_cents
    )
    taxable_after = taxable - taxable_share
    discounted_subtotal = totals.items_cents - totals.quote_discount_cents
    return QuoteDiscountSplit(
        discounted_subtotal_cents=discounted_subtotal,
        untaxed_after_discount_cents=discounted_subtotal - taxable_after,
        taxable_after_discount_cents=taxable_after,
    )


def _taxable_share(discount: int, taxable: int, items_cents: int) -> int:
    """The discount's share of the taxable part, rounded up so the odd
    penny lands on the taxable side (a touch less tax, the customer's
    favor). Never more than the taxable part itself."""
    if not items_cents:
        return 0
    share = _ceil_cents(Decimal(discount) * taxable / items_cents)
    return min(share, taxable)


def _quote_discount_cents(
    subtotal: int, cents: int | None, percent: Decimal | None
) -> int:
    """A quote discount worked out to cents: a flat amount as given, or a
    percent of the subtotal."""
    if cents is not None:
        return cents
    if percent is not None:
        return _whole_cents(subtotal * percent / 100)
    return 0


def _whole_cents(cents: Decimal | int) -> int:
    return int(Decimal(cents).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _ceil_cents(cents: Decimal) -> int:
    return int(cents.quantize(Decimal(1), rounding=ROUND_CEILING))
