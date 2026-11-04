"""A business's saved customers, its regulars mostly, and a quote's copy
of a customer's details."""

from dataclasses import dataclass

from quote_builder.phones import format_phone_ext, phone_matches


@dataclass
class Customer:
    business_id: int
    name: str = ""
    email: str = ""
    phone: str = ""  # ten stored digits (1234567890); shown formatted
    ext: str = ""  # a phone extension, digits only
    address: str = ""  # one field, as typed, line breaks and all
    id: int | None = None  # None until stored; always None on a quote

    @property
    def details(self) -> str:
        """`12 Oak St, Springfield · (123) 456-7890 ext. 12 · jane@example.com`:
        what tells two customers of the same name apart. The phone shows
        formatted; blank parts are left out."""
        lines = [line.strip() for line in self.address.splitlines()]
        address = ", ".join(line for line in lines if line)
        parts = [address, format_phone_ext(self.phone, self.ext), self.email]
        return " · ".join(part for part in parts if part.strip())

    @property
    def is_blank(self) -> bool:
        """True if nothing's been entered, so a quote has no customer."""
        return not (self.name or self.email or self.phone or self.ext or self.address)


def check_customer(customer: Customer) -> None:
    """Raises ValueError, with a message for the user, if `customer`
    can't be saved to the list. (A quote's copy needs nothing.)"""
    if not customer.name:
        raise ValueError("A customer needs a name")


def is_exact_duplicate(customer: Customer, customers: list[Customer]) -> bool:
    """True if one of `customers` has exactly these details, case included:
    the one duplicate that can't be two different people."""

    def details(c: Customer) -> tuple[str, str, str, str, str]:
        return (c.name, c.email, c.phone, c.ext, c.address)

    return any(details(customer) == details(other) for other in customers)


def find_customers(customers: list[Customer], text: str) -> list[Customer]:
    """The customers whose name, email, or address hold `text`, in any
    case, or whose phone holds its digits; all of them if it's blank.
    (The extension isn't searched.)"""
    wanted = text.strip().casefold()
    return [
        customer
        for customer in customers
        if any(
            wanted in part.casefold()
            for part in (customer.name, customer.email, customer.address)
        )
        or phone_matches(customer.phone, text)
    ]
