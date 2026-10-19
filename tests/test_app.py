"""The page, driven by NiceGUI's simulated user: no browser or window."""

from decimal import Decimal

import pytest
from nicegui.testing.user_simulation import user_simulation

from quote_builder.app import quote_page
from quote_builder.quotes import LineItem, Quote, Status
from quote_builder.storage import connect, load_quote, save_new_quote


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "quotes.db")
    yield conn
    conn.close()


@pytest.fixture
async def user(conn):
    async with user_simulation(root=quote_page(conn)) as user:
        await user.open("/")
        yield user


def fill_line(user, n, description, quantity, price):
    user.find(marker=f"description-{n}").type(description)
    user.find(marker=f"quantity-{n}").clear().type(quantity)
    user.find(marker=f"price-{n}").type(price)


def value(found):
    """The value of the one element found."""
    [element] = found.elements
    return element.value


def saved_numbers(conn):
    return [row[0] for row in conn.execute("SELECT number FROM quotes")]


async def test_save_a_new_quote(user, conn):
    fill_line(user, 1, "Mow lawn", "1", "45")
    user.find("Add Line").click()
    fill_line(user, 2, "Trim hedges", "2.5", "$30.00")
    user.find("Notes").type("Front and back yard.")
    user.find("Save").click()

    [number] = saved_numbers(conn)
    await user.should_see(f"Saved {number}")
    await user.should_see(f"{number} (Draft)")
    assert load_quote(conn, number).line_items == [
        LineItem("Mow lawn", Decimal("1"), 4500),
        LineItem("Trim hedges", Decimal("2.5"), 3000),
    ]
    assert load_quote(conn, number).notes == "Front and back yard."


async def test_removed_line_is_not_saved(user, conn):
    fill_line(user, 1, "Mow lawn", "1", "45")
    user.find("Add Line").click()
    fill_line(user, 2, "Trim hedges", "2", "30")
    user.find(marker="remove-1").click()
    user.find("Save").click()

    [number] = saved_numbers(conn)
    assert [item.description for item in load_quote(conn, number).line_items] == [
        "Trim hedges"
    ]


async def test_problem_names_the_line_and_saves_nothing(user, conn):
    fill_line(user, 1, "Mow lawn", "1", "45")
    user.find("Add Line").click()
    fill_line(user, 2, "Trim hedges", "2", "lots")
    user.find("Save").click()

    await user.should_see("Line 2: 'lots' isn't an amount")
    assert saved_numbers(conn) == []


async def test_line_needs_a_description(user, conn):
    fill_line(user, 1, "  ", "1", "45")
    user.find("Save").click()

    await user.should_see("Line 1: A description is needed")
    assert saved_numbers(conn) == []


async def test_open_a_draft_to_edit(user, conn):
    quote = Quote(
        notes="Front yard.",
        line_items=[LineItem("Trim hedges", Decimal("2.5"), 123456)],
    )
    saved = save_new_quote(conn, quote)

    # Typed in lowercase, with spaces around it.
    user.find(marker="open-number").type(f" {saved.number.lower()} ")
    user.find("Open").click()

    await user.should_see(f"{saved.number} (Draft)")
    assert value(user.find(marker="description-1")) == "Trim hedges"
    assert value(user.find(marker="quantity-1")) == "2.5"
    assert value(user.find(marker="price-1")) == "$1,234.56"
    assert value(user.find("Notes")) == "Front yard."


async def test_save_changes_to_a_draft(user, conn):
    fill_line(user, 1, "Mow lawn", "1", "45")
    user.find("Save").click()
    [number] = saved_numbers(conn)

    user.find(marker="price-1").clear().type("50")
    user.find("Add Line").click()
    fill_line(user, 2, "Edge walks", "1", "15")
    user.find("Save").click()

    assert saved_numbers(conn) == [number]
    assert load_quote(conn, number).line_items == [
        LineItem("Mow lawn", Decimal("1"), 5000),
        LineItem("Edge walks", Decimal("1"), 1500),
    ]


async def test_reopened_draft_saves_unchanged(user, conn):
    quote = Quote(line_items=[LineItem("Trim hedges", Decimal("2.5"), 123456)])
    saved = save_new_quote(conn, quote)

    user.find(marker="open-number").type(saved.number)
    user.find("Open").click()
    user.find("Save").click()

    assert load_quote(conn, saved.number) == saved


async def test_open_a_quoted_quote_read_only(user, conn):
    quote = Quote(
        status=Status.QUOTED,
        line_items=[LineItem("Mow lawn", Decimal("1"), 4500)],
    )
    saved = save_new_quote(conn, quote)

    user.find(marker="open-number").type(saved.number)
    user.find("Open").click()

    await user.should_see(f"{saved.number} (Quoted)")
    await user.should_see("Mow lawn: 1 × $45.00")
    await user.should_not_see("Save")


async def test_open_a_missing_quote(user):
    user.find(marker="open-number").type("Q-000-0000")
    user.find("Open").click()

    await user.should_see("No quote Q-000-0000")
    await user.should_see("New Quote")


async def test_new_quote_after_saving(user, conn):
    fill_line(user, 1, "Mow lawn", "1", "45")
    user.find("Save").click()
    user.find("New Quote").click()

    await user.should_see("Add Line")
    await user.should_not_see("(Draft)")
