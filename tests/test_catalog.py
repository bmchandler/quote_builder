from decimal import Decimal

import pytest

from quote_builder.catalog import CatalogItem, check_catalog_item
from quote_builder.quotes import LineItem

BUSINESS = 1


def test_price_text_shows_the_price_per_unit():
    assert CatalogItem(BUSINESS, "Mow", 4500, "hour").price_text == "$45.00 / hr."
    assert CatalogItem(BUSINESS, "Mulch", 650, "each").price_text == "$6.50 / ea."


def test_price_text_is_blank_without_a_price():
    # A job-by-job item has no per-unit price to show.
    assert CatalogItem(BUSINESS, "Mow", unit="hour").price_text == ""
    assert CatalogItem(BUSINESS, "Mow").price_text == ""


def test_a_free_item_shows_its_price():
    assert CatalogItem(BUSINESS, "Estimate", 0).price_text == "$0.00 / ea."


def test_as_line_copies_the_description_price_unit_and_taxable():
    line = CatalogItem(BUSINESS, "Labor", 4500, "hour", taxable=True).as_line()
    assert line == LineItem("Labor", Decimal(1), 4500, unit="hour", taxed=True)


def test_a_catalog_item_needs_a_description():
    with pytest.raises(ValueError, match="A catalog item needs a description"):
        check_catalog_item(CatalogItem(BUSINESS))
    check_catalog_item(CatalogItem(BUSINESS, "Mow"))
