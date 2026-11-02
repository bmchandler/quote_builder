import pytest

from quote_builder.customers import Customer, check_customer, same_name

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


def test_same_name_in_any_case_and_spacing():
    jane = Customer(BUSINESS, "Jane Doe", id=1)
    other_jane = Customer(BUSINESS, "JANE  DOE", id=2)
    sam = Customer(BUSINESS, "Sam Example", id=3)
    assert same_name([jane, other_jane, sam], " jane doe ") == [jane, other_jane]
    assert same_name([jane, sam], "Jane Doering") == []
