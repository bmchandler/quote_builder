from datetime import date

import pytest

from quote_builder.dates import (
    default_valid_until,
    extended_until,
    format_date,
    format_numeric_date,
    parse_date,
)


@pytest.mark.parametrize("text", ["11/18/2026", " 11/18/2026 ", "2026-11-18"])
def test_parse_date(text):
    assert parse_date(text) == date(2026, 11, 18)


def test_parse_date_without_leading_zeros():
    assert parse_date("1/8/2026") == date(2026, 1, 8)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "A date is needed"),
        ("  ", "A date is needed"),
        ("18/11/2026", "'18/11/2026' isn't a date like 11/18/2026"),
        ("02/30/2026", "'02/30/2026' isn't a date like 11/18/2026"),
        ("next week", "'next week' isn't a date like 11/18/2026"),
    ],
)
def test_parse_date_refuses(text, message):
    with pytest.raises(ValueError, match=message):
        parse_date(text)


def test_format_date():
    assert format_date(date(2026, 10, 9)) == "Oct 9, 2026"


def test_format_numeric_date():
    assert format_numeric_date(date(2026, 1, 8)) == "01/08/2026"


def test_default_valid_until_is_30_days_on():
    assert default_valid_until(date(2026, 10, 19)) == date(2026, 11, 18)


def test_extended_from_a_date_still_to_come():
    today = date(2026, 11, 10)
    assert extended_until(date(2026, 11, 18), today, 7) == date(2026, 11, 25)


def test_extended_from_today_once_expired():
    today = date(2026, 11, 25)
    assert extended_until(date(2026, 11, 18), today, 30) == date(2026, 12, 25)
