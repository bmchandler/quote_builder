"""A business the user quotes for, and its settings."""

from dataclasses import dataclass

from quote_builder.dates import VALID_DAYS


@dataclass
class Business:
    id: int | None = None
    valid_days: int = VALID_DAYS  # a new quote's valid-through, from issue
    extend_days: int | None = None  # what Extend offers first; None: unset
