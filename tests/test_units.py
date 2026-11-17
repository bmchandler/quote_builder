from decimal import Decimal

from quote_builder.units import EACH, HOUR, format_quantity, unit_label


def test_hour_takes_a_plural_for_anything_but_one():
    assert unit_label(HOUR, Decimal(1)) == "hr."
    assert unit_label(HOUR, Decimal("1.0")) == "hr."
    assert unit_label(HOUR, Decimal("2.5")) == "hrs."
    assert unit_label(HOUR, Decimal("0.5")) == "hrs."  # less than one is plural


def test_each_never_inflects():
    assert unit_label(EACH, Decimal(1)) == "ea."
    assert unit_label(EACH, Decimal(3)) == "ea."


def test_format_quantity_joins_the_count_and_unit():
    assert format_quantity(Decimal(1), HOUR) == "1 hr."
    assert format_quantity(Decimal("2.5"), HOUR) == "2.5 hrs."
    assert format_quantity(Decimal(1), EACH) == "1 ea."
