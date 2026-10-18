from decimal import Decimal

import pytest

from quote_builder.money import format_money, parse_money, parse_quantity


@pytest.mark.parametrize(
    ("text", "cents"),
    [
        ("45", 4500),
        ("45.5", 4550),
        (" $45.50 ", 4550),
        ("1,234.56", 123456),
        ("0.10", 10),
        ("0", 0),
    ],
)
def test_parse_money(text, cents):
    assert parse_money(text) == cents


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "isn't an amount"),
        ("abc", "isn't an amount"),
        ("NaN", "isn't an amount"),
        ("-5", "can't be negative"),
        ("4.505", "more than two decimal places"),
    ],
)
def test_parse_money_refuses(text, message):
    with pytest.raises(ValueError, match=message):
        parse_money(text)


@pytest.mark.parametrize(
    ("cents", "text"),
    [(0, "$0.00"), (5, "$0.05"), (4550, "$45.50"), (123456, "$1,234.56")],
)
def test_format_money(cents, text):
    assert format_money(cents) == text


def test_parse_quantity():
    assert parse_quantity(" 2.5 ") == Decimal("2.5")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "isn't a quantity"),
        ("two", "isn't a quantity"),
        ("Infinity", "isn't a quantity"),
        ("0", "more than zero"),
        ("-1", "more than zero"),
    ],
)
def test_parse_quantity_refuses(text, message):
    with pytest.raises(ValueError, match=message):
        parse_quantity(text)
