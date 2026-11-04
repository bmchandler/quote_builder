import pytest

from quote_builder.phones import (
    digits,
    format_phone,
    format_phone_ext,
    parse_ext,
    parse_phone,
    phone_matches,
)


@pytest.mark.parametrize(
    "entered",
    ["1234567890", "123.456.7890", "(123)456-7890", "(123) 456-7890", " 123-456-7890 "],
)
def test_parse_reads_the_common_forms_as_ten_digits(entered):
    assert parse_phone(entered) == "1234567890"


def test_parse_blank_is_blank():
    assert parse_phone("") == ""
    assert parse_phone("   ") == ""


@pytest.mark.parametrize("bad", ["123456789", "12345678901", "555-0134", "phone"])
def test_parse_rejects_anything_but_ten_digits(bad):
    with pytest.raises(ValueError, match="isn't a 10-digit phone number"):
        parse_phone(bad)


def test_format_is_the_standard_form():
    assert format_phone("1234567890") == "(123) 456-7890"


def test_format_leaves_odd_or_older_data_alone():
    assert format_phone("") == ""
    assert format_phone("555-0134") == "555-0134"


def test_parse_ext_is_digits_only():
    assert parse_ext("") == ""
    assert parse_ext(" 12 ") == "12"
    with pytest.raises(ValueError, match="isn't an extension"):
        parse_ext("x12")


def test_format_phone_with_an_extension():
    assert format_phone_ext("1234567890", "12") == "(123) 456-7890 ext. 12"
    assert format_phone_ext("1234567890", "") == "(123) 456-7890"
    assert format_phone_ext("", "12") == "ext. 12"
    assert format_phone_ext("", "") == ""


def test_digits_keeps_only_digits():
    assert digits("(123) 456-7890") == "1234567890"
    assert digits("no digits here") == ""


def test_phone_matches_by_digits_either_way():
    # Stored digits, a term punctuated however.
    assert phone_matches("1234567890", "456")
    assert phone_matches("1234567890", "(123) 456")
    assert phone_matches("1234567890", "1234567890")
    assert not phone_matches("1234567890", "999")


def test_phone_matches_needs_a_digit():
    # A plain text search mustn't light up every number.
    assert not phone_matches("1234567890", "jane")
    assert not phone_matches("1234567890", "")
