"""A business the user quotes for, and its settings."""

from dataclasses import dataclass, field
from decimal import Decimal

from quote_builder.dates import VALID_DAYS


@dataclass
class Business:
    id: int | None = None
    name: str = ""  # blank until given
    pilot: bool = False  # an idea being tried out, not yet a business
    valid_days: int = VALID_DAYS  # a new quote's valid-through, from issue
    extend_days: int | None = None  # what Extend offers first; None: unset


@dataclass(frozen=True)
class TaxPart:
    """One part of a tax rate: `State 4.75%`."""

    name: str  # may be blank, for a rate of one part
    percent: Decimal


@dataclass
class TaxRate:
    """A business's sales tax rate where it works (`Home county`), from
    its parts, so a part that changes is changed once."""

    business_id: int
    name: str = ""
    parts: list[TaxPart] = field(default_factory=list)  # in order
    is_default: bool = False  # what a new quote starts with
    id: int | None = None  # None until stored

    @property
    def percent(self) -> Decimal:
        """The combined rate: its parts added up."""
        return sum((part.percent for part in self.parts), Decimal(0))


def check_tax_rate(rate: TaxRate) -> None:
    """Raises ValueError, with a message for the user, if `rate` can't
    be saved."""
    if not rate.name:
        raise ValueError("A tax rate needs a name")
    if not rate.parts:
        raise ValueError("A tax rate needs at least one part")
