"""A business's catalog: services and parts to pick for a quote's lines."""

from dataclasses import dataclass
from decimal import Decimal

from quote_builder import units
from quote_builder.money import format_money
from quote_builder.quotes import LineItem
from quote_builder.units import unit_label


@dataclass
class CatalogItem:
    business_id: int
    description: str = ""
    price_cents: int | None = None  # None: priced job by job
    unit: str = units.DEFAULT  # Hour or Each; stays in the catalog
    taxable: bool = False
    id: int | None = None  # None until stored

    @property
    def price_text(self) -> str:
        """`$45.00 / hr.`, leaving out a blank price."""
        price = "" if self.price_cents is None else format_money(self.price_cents)
        per_unit = f"{price} / {unit_label(self.unit, Decimal(1))}" if price else ""
        return per_unit

    def as_line(self) -> LineItem:
        """A new line of one, a copy: changing it leaves the catalog alone,
        and changing the catalog leaves the line alone. A price of 0 if
        the item has none."""
        return LineItem(
            self.description,
            Decimal(1),
            self.price_cents or 0,
            unit=self.unit,
            taxed=self.taxable,
        )


def check_catalog_item(item: CatalogItem) -> None:
    """Raises ValueError, with a message for the user, if `item` can't be
    saved."""
    if not item.description:
        raise ValueError("A catalog item needs a description")
