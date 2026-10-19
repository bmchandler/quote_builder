from decimal import Decimal

import pytest

from quote_builder.quotes import LineItem
from quote_builder.totals import LineTotals, QuoteTotals, line_totals, quote_totals


def line(quantity, price_cents, **extra):
    return LineItem("Item", Decimal(quantity), price_cents, **extra)


def test_plain_line():
    assert line_totals(line("2", 4500)) == LineTotals(
        amount_cents=9000, discount_cents=0, tax_cents=0
    )


def test_fractional_quantity_rounds_half_up():
    # 2.5 × $0.33 = $0.825 → $0.83 (half up), not $0.82 (half even).
    assert line_totals(line("2.5", 33)).amount_cents == 83


def test_discount_amount():
    totals = line_totals(line("1", 4500, discount_cents=500))
    assert (totals.discount_cents, totals.net_cents) == (500, 4000)


def test_discount_percent_rounds_half_up():
    # 10% of $0.25 = $0.025 → $0.03.
    assert line_totals(line("1", 25, discount_percent=Decimal("10"))).discount_cents == 3


def test_tax_is_on_the_discounted_amount():
    totals = line_totals(
        line(
            "1",
            10000,
            discount_percent=Decimal("10"),
            tax_percent=Decimal("7.25"),
        )
    )
    # $100 - 10% = $90; 7.25% of $90 = $6.525 → $6.53.
    assert totals == LineTotals(amount_cents=10000, discount_cents=1000, tax_cents=653)
    assert totals.net_cents == 9000
    assert totals.total_cents == 9653


def test_discount_can_be_the_whole_line():
    assert line_totals(line("1", 4500, discount_cents=4500)).net_cents == 0


def test_discount_over_the_line_is_refused():
    with pytest.raises(ValueError, match="more than the line"):
        line_totals(line("1", 4500, discount_cents=4501))


def test_quote_totals_add_up_the_lines():
    items = [
        line("1", 4500),
        line("2.5", 3000, discount_percent=Decimal("10")),
        line("1", 1899, discount_cents=200, tax_percent=Decimal("7.25")),
    ]
    # Lines: $45.00; $75.00 - $7.50; $18.99 - $2.00 + tax $1.23 ($1.23175).
    assert quote_totals(items) == QuoteTotals(
        items_cents=4500 + 7500 + 1899,
        discount_cents=750 + 200,
        tax_cents=123,
        total_cents=4500 + 6750 + 1699 + 123,
    )


def test_quote_with_no_lines():
    assert quote_totals([]) == QuoteTotals(0, 0, 0, 0)
