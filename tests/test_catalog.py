from decimal import Decimal

import pytest

from quote_builder.catalog import CatalogItem, check_catalog_item
from quote_builder.quotes import LineItem

BUSINESS = 1


def test_price_text_shows_the_price_and_unit():
    assert CatalogItem(BUSINESS, "Mow", 4500, "hour").price_text == "$45.00 / hour"


def test_price_text_leaves_out_blank_parts():
    assert CatalogItem(BUSINESS, "Mow", 4500).price_text == "$45.00"
    assert CatalogItem(BUSINESS, "Mow", unit="hour").price_text == "hour"
    assert CatalogItem(BUSINESS, "Mow").price_text == ""


def test_a_free_item_shows_its_price():
    assert CatalogItem(BUSINESS, "Estimate", 0).price_text == "$0.00"


def test_as_line_copies_the_description_price_and_taxable():
    line = CatalogItem(BUSINESS, "Mulch", 650, "each", taxable=True).as_line()
    assert line == LineItem("Mulch", Decimal(1), 650, taxed=True)


def test_a_catalog_item_needs_a_description():
    with pytest.raises(ValueError, match="A catalog item needs a description"):
        check_catalog_item(CatalogItem(BUSINESS))
    check_catalog_item(CatalogItem(BUSINESS, "Mow"))
