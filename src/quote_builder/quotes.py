"""Quotes and their line items, as the app works with them."""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class Status(StrEnum):
    DRAFT = "Draft"
    QUOTED = "Quoted"
    ACCEPTED = "Accepted"
    DECLINED = "Declined"
    EXPIRED = "Expired"
    SUPERSEDED = "Superseded"


@dataclass(frozen=True)
class LineTotals:
    """What a line adds up to (worked out in totals.py)."""

    amount_cents: int  # quantity × unit price
    discount_cents: int
    tax_cents: int

    @property
    def net_cents(self) -> int:
        """The amount after the discount, before tax."""
        return self.amount_cents - self.discount_cents

    @property
    def total_cents(self) -> int:
        return self.net_cents + self.tax_cents


@dataclass(frozen=True)
class QuoteTotals:
    """A quote's foot: what its lines add up to."""

    items_cents: int  # the lines' amounts, before discounts
    discount_cents: int
    tax_cents: int
    total_cents: int


@dataclass
class LineItem:
    description: str
    quantity: Decimal
    unit_price_cents: int
    tax_percent: Decimal = Decimal(0)
    # An amount or a percent, never both.
    discount_cents: int | None = None
    discount_percent: Decimal | None = None
    # Stored once quoted, so what the client was given never changes.
    frozen: LineTotals | None = None


@dataclass
class Quote:
    number: str | None = None  # None until first saved
    revision: int = 0
    status: Status = Status.DRAFT
    issued_on: date | None = None
    valid_until: date | None = None
    notes: str = ""
    line_items: list[LineItem] = field(default_factory=list)
    frozen: QuoteTotals | None = None  # stored once quoted, as for lines


@dataclass
class QuoteSummary:
    """What the list of quotes shows of one."""

    number: str
    revision: int
    status: Status
    first_line: str | None  # the first line's description; None if no lines
    updated_at: datetime
    total_cents: int
