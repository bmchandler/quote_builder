"""A business the user quotes for, and its settings."""

from dataclasses import dataclass

from quote_builder.dates import VALID_DAYS


@dataclass
class Business:
    id: int | None = None
    name: str = ""  # blank until given
    pilot: bool = False  # an idea being tried out, not yet a business
    valid_days: int = VALID_DAYS  # a new quote's valid-through, from issue
    extend_days: int | None = None  # what Extend offers first; None: unset
