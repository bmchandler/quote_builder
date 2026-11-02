"""A business's customers, kept for the next job."""

from dataclasses import dataclass


@dataclass
class Customer:
    business_id: int
    name: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""  # one field, as typed, line breaks and all
    id: int | None = None  # None until stored

    @property
    def details(self) -> str:
        """`12 Oak St, Springfield · 555-0134 · jane@example.com`: what
        tells two customers of the same name apart. Blank parts are left
        out."""
        lines = [line.strip() for line in self.address.splitlines()]
        address = ", ".join(line for line in lines if line)
        parts = [address, self.phone, self.email]
        return " · ".join(part for part in parts if part.strip())


def check_customer(customer: Customer) -> None:
    """Raises ValueError, with a message for the user, if `customer`
    can't be saved."""
    if not customer.name:
        raise ValueError("A customer needs a name")


def same_name(customers: list[Customer], name: str) -> list[Customer]:
    """The customers named `name`, in any case and spacing: a likely
    duplicate of a new one."""

    def key(text: str) -> str:
        # casefold: lower() for comparing, which also folds ß to ss.
        return " ".join(text.split()).casefold()

    return [customer for customer in customers if key(customer.name) == key(name)]
