from decimal import Decimal

import pytest

from quote_builder.money import (
    format_discount,
    format_discount_detail,
    format_money,
    format_percent,
    parse_discount,
    parse_money,
    parse_percent,
    parse_quantity,
)


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
        ("", "An amount is needed"),
        ("$", "An amount is needed"),
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
    [
        (0, "$0.00"),
        (5, "$0.05"),
        (4550, "$45.50"),
        (123456, "$1,234.56"),
        (-750, "-$7.50"),
    ],
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


@pytest.mark.parametrize(
    ("text", "percent"),
    [("", Decimal(0)), ("7.25", Decimal("7.25")), (" 7.25% ", Decimal("7.25")), ("100", Decimal(100))],
)
def test_parse_percent(text, percent):
    assert parse_percent(text) == percent


@pytest.mark.parametrize(
    ("text", "message"),
    [("abc", "isn't a percent"), ("-1", "between 0 and 100"), ("100.5", "between 0 and 100")],
)
def test_parse_percent_refuses(text, message):
    with pytest.raises(ValueError, match=message):
        parse_percent(text)


@pytest.mark.parametrize(
    ("text", "discount"),
    [
        ("", (None, None)),
        ("  ", (None, None)),
        ("0", (None, None)),
        ("0%", (None, None)),
        ("10%", (None, Decimal("10"))),
        ("12.5 %", (None, Decimal("12.5"))),
        ("5", (500, None)),
        ("$5.50", (550, None)),
    ],
)
def test_parse_discount(text, discount):
    assert parse_discount(text) == discount


@pytest.mark.parametrize(
    ("text", "message"),
    [("lots", "isn't an amount"), ("110%", "between 0 and 100"), ("x%", "isn't a percent")],
)
def test_parse_discount_refuses(text, message):
    with pytest.raises(ValueError, match=message):
        parse_discount(text)


@pytest.mark.parametrize(
    ("cents", "percent", "text"),
    [(None, None, ""), (550, None, "$5.50"), (None, Decimal("12.5"), "12.5%")],
)
def test_format_discount(cents, percent, text):
    assert format_discount(cents, percent) == text


@pytest.mark.parametrize(
    ("cents", "percent", "amount_cents", "text"),
    [
        (None, None, 0, ""),
        (550, None, 550, "$5.50"),  # a flat amount is already dollars
        (None, Decimal(5), 136, "5% ($1.36)"),  # percent gains the dollars
    ],
)
def test_format_discount_detail(cents, percent, amount_cents, text):
    assert format_discount_detail(cents, percent, amount_cents) == text


@pytest.mark.parametrize(
    ("percent", "text"), [(Decimal(0), ""), (Decimal("7.25"), "7.25"), (Decimal("7.250"), "7.250")]
)
def test_format_percent(percent, text):
    assert format_percent(percent) == text
