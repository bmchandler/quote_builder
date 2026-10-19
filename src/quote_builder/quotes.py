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


@dataclass
class LineItem:
    description: str
    quantity: Decimal
    unit_price_cents: int
    tax_percent: Decimal = Decimal(0)
    # An amount or a percent, never both.
    discount_cents: int | None = None
    discount_percent: Decimal | None = None


@dataclass
class Quote:
    number: str | None = None  # None until first saved
    revision: int = 0
    status: Status = Status.DRAFT
    issued_on: date | None = None
    valid_until: date | None = None
    notes: str = ""
    line_items: list[LineItem] = field(default_factory=list)


@dataclass
class QuoteSummary:
    """What the list of quotes shows of one."""

    number: str
    revision: int
    status: Status
    first_line: str | None  # the first line's description; None if no lines
    updated_at: datetime
