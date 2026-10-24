from decimal import Decimal

import pytest

from quote_builder.business import TaxPart, TaxRate, check_tax_rate

HOME = TaxRate(
    1,
    "Home county",
    [
        TaxPart("State", Decimal("4.75")),
        TaxPart("County", Decimal("1.5")),
        TaxPart("City", Decimal("1")),
    ],
)


def test_a_rate_is_its_parts_added_up():
    assert HOME.percent == Decimal("7.25")


def test_a_rate_without_parts_is_zero():
    assert TaxRate(1, "None").percent == 0


def test_a_whole_rate_checks_out():
    check_tax_rate(HOME)  # no error


def test_a_rate_needs_a_name():
    with pytest.raises(ValueError, match="A tax rate needs a name"):
        check_tax_rate(TaxRate(1, "", HOME.parts))


def test_a_rate_needs_a_part():
    with pytest.raises(ValueError, match="A tax rate needs at least one part"):
        check_tax_rate(TaxRate(1, "Home county"))
