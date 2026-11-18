from decimal import Decimal

import pytest

from quote_builder.quotes import LineItem, LineTotals, Quote, QuoteTotals
from quote_builder.totals import (
    freeze,
    line_mode_taxable_cents,
    line_totals,
    quote_discount_split,
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
        quote_discount_cents=0,
        tax_cents=123,
        total_cents=4500 + 6750 + 1699 + 123,
    )


def test_quote_with_no_lines():
    assert quote_totals([], RATE) == QuoteTotals(0, 0, 0, 0, 0)


def test_freeze_stores_each_lines_figures_and_the_foot():
    quote = Quote(
        line_items=[
            line("1", 4500),
            line("1", 10000, discount_percent=Decimal("10"), taxed=True),
        ],
        tax_percent=RATE,
    )
    frozen = freeze(quote)
    # The line keeps its amount and discount; tax is pooled at the foot
    # now, so a frozen line carries no tax of its own.
    assert [item.frozen for item in frozen.line_items] == [
        LineTotals(4500, 0, 0),
        LineTotals(10000, 1000, 0),
    ]
    assert frozen.frozen == QuoteTotals(14500, 1000, 0, 653, 14153)
    assert quote.frozen is None  # a copy; the quote itself is left alone


def test_shown_totals_are_frozen_once_quoted():
    # Frozen figures that no longer match the lines, as after a rule change.
    item = line("1", 4500, frozen=LineTotals(4000, 0, 0))
    quote = Quote(line_items=[item], frozen=QuoteTotals(4000, 0, 0, 0, 4000))
    assert shown_line_totals(item, RATE).amount_cents == 4000
    assert shown_quote_totals(quote).total_cents == 4000


def test_shown_totals_are_worked_out_for_a_draft():
    item = line("1", 4500, taxed=True)
    assert shown_line_totals(item, RATE).tax_cents == 326  # $3.2625
    quote = Quote(line_items=[item], tax_percent=RATE)
    assert shown_quote_totals(quote).total_cents == 4826


def test_line_discount_mode_taxes_the_pooled_base_not_each_line():
    # Two taxed lines, each net $10.00. Pooled: $20.00 × 7.25% = $1.45.
    # Per line it would be $0.725 → $0.73 each = $1.46, a penny more; the
    # pooled figure is what makes a shown Taxable × rate land on Taxes.
    lines = [line("1", 1000, taxed=True), line("1", 1000, taxed=True)]
    totals = quote_totals(lines, RATE)
    assert totals.tax_cents == 145
    assert totals.total_cents == 2145  # $20.00 + $1.45
    assert line_mode_taxable_cents(lines, RATE) == 2000  # × 7.25% = Taxes


def test_line_mode_taxable_is_the_sum_of_taxed_nets():
    # $90 taxed less 10% → $81 net, $40 taxed less $5 → $35 net, $50
    # untaxed. Taxable is the taxed nets only: $81 + $35 = $116.
    lines = [
        line("2", 4500, taxed=True, discount_percent=Decimal("10")),
        line("1", 4000, taxed=True, discount_cents=500),
        line("1", 5000, discount_percent=Decimal("10")),
    ]
    assert line_mode_taxable_cents(lines, RATE) == 11600
    totals = quote_totals(lines, RATE)
    assert totals.tax_cents == 841  # $116.00 × 7.25% = $8.41105 → $8.41


# A whole-quote discount, applied before tax and split across the taxable
# and non-taxable lines by their share of the subtotal. The numbers here
# are the worked example in CALCULATIONS.md.

QUOTE_DISCOUNT_LINES = [
    line("2", 4500, taxed=True),  # Widget A: $90.00
    line("3", 3700, taxed=True),  # Widget B: $111.00
    line("1", 5000),  # Consultation: $50.00, non-taxable
]


def test_flat_quote_discount_splits_before_tax():
    # Subtotal $251.00; taxable $201.00. $20 discount: taxable's share is
    # $20 × 201/251 = $16.02 (rounded up), so tax is 7.25% of $184.98.
    totals = quote_totals(QUOTE_DISCOUNT_LINES, RATE, quote_discount_cents=2000)
    assert totals == QuoteTotals(
        items_cents=25100,
        discount_cents=0,
        quote_discount_cents=2000,
        tax_cents=1341,  # 7.25% × ($201.00 − $16.02 taxable share)
        total_cents=24441,  # ($251.00 − $20.00) + $13.41
    )


def test_quote_discount_split_breaks_the_subtotal_into_its_parts():
    # The foot's breakdown: discounted subtotal $231.00, split into the
    # taxable part ($184.98, what tax is figured on) and the rest ($46.02).
    totals = quote_totals(QUOTE_DISCOUNT_LINES, RATE, quote_discount_cents=2000)
    split = quote_discount_split(QUOTE_DISCOUNT_LINES, totals)
    assert split.discounted_subtotal_cents == 23100  # $251.00 − $20.00
    assert split.taxable_after_discount_cents == 18498  # $201.00 − $16.02
    assert split.untaxed_after_discount_cents == 4602  # $50.00 − $3.98
    # The two parts add back to the discounted subtotal, and the taxable
    # part × the rate is the foot's tax.
    assert (
        split.taxable_after_discount_cents + split.untaxed_after_discount_cents
        == split.discounted_subtotal_cents
    )
    assert round(split.taxable_after_discount_cents * 7.25 / 100) == totals.tax_cents


def test_quote_discount_split_with_no_taxable_lines_is_all_untaxed():
    lines = [line("1", 5000), line("1", 3000)]  # both non-taxable
    totals = quote_totals(lines, UNTAXED, quote_discount_cents=1000)
    split = quote_discount_split(lines, totals)
    assert split.taxable_after_discount_cents == 0
    assert split.untaxed_after_discount_cents == 7000  # $80.00 − $10.00


def test_percent_quote_discount_is_of_the_subtotal():
    # 10% of $251.00 = $25.10, then the same split-and-tax.
    totals = quote_totals(
        QUOTE_DISCOUNT_LINES, RATE, quote_discount_percent=Decimal("10")
    )
    assert totals.quote_discount_cents == 2510
    assert totals.tax_cents == 1312  # 7.25% × ($201.00 − $25.10)
    assert totals.total_cents == 23902


def test_the_odd_split_penny_lands_on_the_taxable_side():
    # $100 taxable + $5 untaxable, $1 quote discount at 10%. The taxable
    # share is $1 × 100/105 = $0.96 (rounded up, not $0.95), so tax is
    # 10% of $99.04 = $9.90, a penny less than it would be at $0.95
    # ($99.05 → $9.905 → $9.91). The odd penny favors the customer.
    lines = [line("1", 10000, taxed=True), line("1", 500)]
    totals = quote_totals(lines, Decimal("10"), quote_discount_cents=100)
    assert totals.tax_cents == 990
    assert totals.total_cents == 11390  # ($105 − $1) + $9.90


def test_a_quote_discount_can_be_the_whole_subtotal():
    totals = quote_totals([line("1", 4500)], UNTAXED, quote_discount_cents=4500)
    assert totals.quote_discount_cents == 4500
    assert totals.total_cents == 0


def test_a_quote_discount_over_the_subtotal_is_refused():
    with pytest.raises(ValueError, match="more than the quote"):
        quote_totals([line("1", 4500)], UNTAXED, quote_discount_cents=4501)


def test_both_discount_modes_at_once_are_refused():
    lines = [line("1", 4500, discount_cents=500)]
    with pytest.raises(ValueError, match="line discounts or a Quote Discount"):
        quote_totals(lines, UNTAXED, quote_discount_cents=1000)


def test_freeze_zeroes_each_lines_own_figures_in_quote_discount_mode():
    # The line keeps only its amount; its tax lives in the foot.
    quote = Quote(
        line_items=[line("2", 4500, taxed=True), line("1", 5000)],
        tax_percent=RATE,
        quote_discount_cents=1000,
    )
    frozen = freeze(quote)
    assert [item.frozen for item in frozen.line_items] == [
        LineTotals(9000, 0, 0),
        LineTotals(5000, 0, 0),
    ]
    assert frozen.frozen.quote_discount_cents == 1000
