from datetime import date

import pytest

from quote_builder.dates import default_valid_until, format_date, parse_date


@pytest.mark.parametrize("text", ["2026-11-18", " 2026-11-18 "])
def test_parse_date(text):
    assert parse_date(text) == date(2026, 11, 18)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "A date is needed"),
        ("  ", "A date is needed"),
        ("11/18/2026", "'11/18/2026' isn't a date like 2026-11-18"),
        ("2026-02-30", "'2026-02-30' isn't a date like 2026-11-18"),
    ],
)
def test_parse_date_refuses(text, message):
    with pytest.raises(ValueError, match=message):
        parse_date(text)


def test_format_date():
    assert format_date(date(2026, 10, 9)) == "Oct 9, 2026"


def test_default_valid_until_is_30_days_on():
    assert default_valid_until(date(2026, 10, 19)) == date(2026, 11, 18)
