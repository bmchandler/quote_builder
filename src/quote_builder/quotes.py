"""Quotes and their line items, as the app works with them."""

from dataclasses import dataclass, field, replace
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


# Statuses a quote can be revised from (not Accepted: a change after
# acceptance is a matter for invoicing, later).
REVISABLE = (Status.QUOTED, Status.DECLINED, Status.EXPIRED)


def version_name(number: str, revision: int) -> str:
    """`Q-7KQ-M9XD` for the first version, `Q-7KQ-M9XD-R1` and on after."""
    return number if revision == 0 else f"{number}-R{revision}"


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


@dataclass(frozen=True)
class Extension:
    """One time a quote's valid-through date was moved later."""

    extended_on: date
    old_valid_until: date
    new_valid_until: date


@dataclass
class Quote:
    business_id: int | None = None  # whose quote it is; needed to save
    number: str | None = None  # None until first saved
    revision: int = 0
    status: Status = Status.DRAFT
    issued_on: date | None = None
    # The last day the quote is good, inclusive ("valid through").
    valid_until: date | None = None
    notes: str = ""
    line_items: list[LineItem] = field(default_factory=list)
    frozen: QuoteTotals | None = None  # stored once quoted, as for lines
    extensions: list[Extension] = field(default_factory=list)  # oldest first


@dataclass
class QuoteSummary:
    """What the list of quotes shows of one."""

    number: str
    revision: int
    status: Status
    first_line: str | None  # the first line's description; None if no lines
    updated_at: datetime
    total_cents: int
    issued_on: date | None = None
    valid_until: date | None = None


@dataclass(frozen=True)
class SearchText:
    """A piece of a quote's text that search looks in."""

    revision: int
    field: str  # "line" or "notes"
    position: int  # the line's place on the quote, from 0; 0 for notes
    text: str


def revision_draft(quote: Quote, revision: int) -> Quote:
    """A new draft of `quote` numbered `revision`, not yet saved.

    It keeps the lines and notes, as changeable, but none of what the
    quoted version was given: dates, frozen figures, extensions.
    """
    return Quote(
        business_id=quote.business_id,
        number=quote.number,
        revision=revision,
        notes=quote.notes,
        line_items=[replace(item, frozen=None) for item in quote.line_items],
    )
