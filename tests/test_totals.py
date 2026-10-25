from decimal import Decimal

import pytest

from quote_builder.quotes import LineItem, LineTotals, Quote, QuoteTotals
from quote_builder.totals import (
    freeze,
    line_totals,
    quote_totals,
    shown_line_totals,
    shown_quote_totals,
)

UNTAXED = Decimal(0)  # the quote's rate when it has none
RATE = Decimal("7.25")


def line(quantity, price_cents, **extra):
    return LineItem("Item", Decimal(quantity), price_cents, **extra)


def test_plain_line():
    assert line_totals(line("2", 4500), UNTAXED) == LineTotals(
        amount_cents=9000, discount_cents=0, tax_cents=0
    )


def test_fractional_quantity_rounds_half_up():
    # 2.5 × $0.33 = $0.825 → $0.83 (half up), not $0.82 (half even).
    assert line_totals(line("2.5", 33), UNTAXED).amount_cents == 83


def test_discount_amount():
    totals = line_totals(line("1", 4500, discount_cents=500), UNTAXED)
    assert (totals.discount_cents, totals.net_cents) == (500, 4000)


def test_discount_percent_rounds_half_up():
    # 10% of $0.25 = $0.025 → $0.03.
    item = line("1", 25, discount_percent=Decimal("10"))
    assert line_totals(item, UNTAXED).discount_cents == 3


def test_tax_is_on_the_discounted_amount():
    item = line("1", 10000, discount_percent=Decimal("10"), taxed=True)
    totals = line_totals(item, RATE)
    # $100 - 10% = $90; 7.25% of $90 = $6.525 → $6.53.
    assert totals == LineTotals(amount_cents=10000, discount_cents=1000, tax_cents=653)
    assert totals.net_cents == 9000
    assert totals.total_cents == 9653


def test_an_untaxed_line_ignores_the_rate():
    assert line_totals(line("1", 10000), RATE).tax_cents == 0


def test_a_taxed_line_on_an_untaxed_quote_has_no_tax():
    assert line_totals(line("1", 10000, taxed=True), UNTAXED).tax_cents == 0


def test_discount_can_be_the_whole_line():
    assert line_totals(line("1", 4500, discount_cents=4500), UNTAXED).net_cents == 0


def test_discount_over_the_line_is_refused():
    with pytest.raises(ValueError, match="more than the line"):
        line_totals(line("1", 4500, discount_cents=4501), UNTAXED)


def test_quote_totals_add_up_the_lines():
    items = [
        line("1", 4500),
        line("2.5", 3000, discount_percent=Decimal("10")),
        line("1", 1899, discount_cents=200, taxed=True),
    ]
    # Lines: $45.00; $75.00 - $7.50; $18.99 - $2.00 + tax $1.23 ($1.23175).
    assert quote_totals(items, RATE) == QuoteTotals(
        items_cents=4500 + 7500 + 1899,
        discount_cents=750 + 200,
        tax_cents=123,
        total_cents=4500 + 6750 + 1699 + 123,
    )


def test_quote_with_no_lines():
    assert quote_totals([], RATE) == QuoteTotals(0, 0, 0, 0)


def test_freeze_stores_each_lines_figures_and_the_foot():
    quote = Quote(
        line_items=[
            line("1", 4500),
            line("1", 10000, discount_percent=Decimal("10"), taxed=True),
        ],
        tax_percent=RATE,
    )
    frozen = freeze(quote)
    assert [item.frozen for item in frozen.line_items] == [
        LineTotals(4500, 0, 0),
        LineTotals(10000, 1000, 653),
    ]
    assert frozen.frozen == QuoteTotals(14500, 1000, 653, 14153)
    assert quote.frozen is None  # a copy; the quote itself is left alone


def test_shown_totals_are_frozen_once_quoted():
    # Frozen figures that no longer match the lines, as after a rule change.
    item = line("1", 4500, frozen=LineTotals(4000, 0, 0))
    quote = Quote(line_items=[item], frozen=QuoteTotals(4000, 0, 0, 4000))
    assert shown_line_totals(item, RATE).amount_cents == 4000
    assert shown_quote_totals(quote).total_cents == 4000


def test_shown_totals_are_worked_out_for_a_draft():
    item = line("1", 4500, taxed=True)
    assert shown_line_totals(item, RATE).tax_cents == 326  # $3.2625
    quote = Quote(line_items=[item], tax_percent=RATE)
    assert shown_quote_totals(quote).total_cents == 4826
