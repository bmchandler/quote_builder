from dataclasses import replace

import pytest

from quote_builder.customers import (
    Customer,
    check_customer,
    find_customers,
    is_exact_duplicate,
)

BUSINESS = 1


def test_details_tell_customers_apart():
    jane = Customer(
        BUSINESS, "Jane Doe", "jane@example.com", "555-0134", "12 Oak St\nSpringfield"
    )
    assert jane.details == "12 Oak St, Springfield · 555-0134 · jane@example.com"


def test_details_leave_out_blank_parts():
    assert Customer(BUSINESS, "Jane Doe", phone="555-0134").details == "555-0134"
    assert Customer(BUSINESS, "Jane Doe", address=" 12 Oak St \n\n").details == (
        "12 Oak St"
    )
    assert Customer(BUSINESS, "Jane Doe").details == ""


def test_a_customer_needs_a_name():
    with pytest.raises(ValueError, match="A customer needs a name"):
        check_customer(Customer(BUSINESS))
    check_customer(Customer(BUSINESS, "Jane Doe"))


def test_blank_means_nothing_entered():
    assert Customer(BUSINESS).is_blank
    assert not Customer(BUSINESS, name="Jane Doe").is_blank
    assert not Customer(BUSINESS, email="jane@example.com").is_blank
    assert not Customer(BUSINESS, phone="555-0134").is_blank
    assert not Customer(BUSINESS, address="12 Oak St").is_blank


JANE = Customer(BUSINESS, "Jane Doe", "jane@example.com", "555-0134", "12 Oak St", 1)
SAM = Customer(BUSINESS, "Sam Example", "sam@test.example", "555-0177", "48 Elm Rd", 2)


@pytest.mark.parametrize("text", ["JANE", "@example.com", "0134", "oak st", " doe "])
def test_find_matches_any_detail_in_any_case(text):
    assert find_customers([JANE, SAM], text) == [JANE]


def test_find_with_nothing_typed_gives_them_all():
    assert find_customers([JANE, SAM], "  ") == [JANE, SAM]


def test_find_can_find_nobody():
    assert find_customers([JANE, SAM], "nobody") == []


def test_all_details_matching_is_an_exact_duplicate():
    assert is_exact_duplicate(replace(JANE, id=None), [SAM, JANE])


@pytest.mark.parametrize(
    "change",
    [
        {"name": "jane doe"},
        {"email": "doe@example.com"},
        {"phone": "555-0199"},
        {"address": "48 Elm Rd"},
    ],
)
def test_any_detail_differing_isnt_an_exact_duplicate(change):
    assert not is_exact_duplicate(replace(JANE, id=None, **change), [SAM, JANE])
