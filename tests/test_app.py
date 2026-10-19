"""The page, driven by NiceGUI's simulated user: no browser or window."""

import asyncio
import time
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from quote_builder.app import quote_page, short_date
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


async def reload(user):
    """Open the page again, as after quotes were saved behind its back."""
    await user.open("/")


def list_order(user):
    """The quote numbers in the side list, top to bottom."""
    items = user.find(kind=ui.item).elements
    markers = [m for item in sorted(items, key=lambda e: e.id) for m in item._markers]
    return [m.removeprefix("quote-") for m in markers if m.startswith("quote-")]


async def eventually(check, tries=50):
    """Wait for `check()` to come true, as NiceGUI redraws a refreshed list
    in the background (refresh() runs as a task unless awaited)."""
    for _ in range(tries):
        if check():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("still not true after waiting")


def active(user, number):
    """Whether the list highlights this quote."""
    [item] = user.find(marker=f"quote-{number}").elements
    return item.props.get("active") is True


def saved_numbers(conn):
    # ORDER BY: without it, SQLite may read the (number, revision) index
    # and return the numbers sorted instead of in the order saved.
    return [row[0] for row in conn.execute("SELECT number FROM quotes ORDER BY id")]


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

    await reload(user)
    user.find(marker=f"quote-{saved.number}").click()

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

    await reload(user)
    user.find(marker=f"quote-{saved.number}").click()
    user.find("Save").click()

    assert load_quote(conn, saved.number) == saved


async def test_open_a_quoted_quote_read_only(user, conn):
    quote = Quote(
        status=Status.QUOTED,
        line_items=[LineItem("Mow lawn", Decimal("1"), 4500)],
    )
    saved = save_new_quote(conn, quote)

    await reload(user)
    user.find(marker=f"quote-{saved.number}").click()

    await user.should_see(f"{saved.number} (Quoted)")
    await user.should_see("Mow lawn: 1 × $45.00")
    await user.should_not_see("Save")


async def test_list_shows_saved_quotes_newest_first(user, conn):
    fill_line(user, 1, "Mow lawn", "1", "45")
    user.find("Save").click()
    user.find("New Quote").click()
    fill_line(user, 1, "Clean gutters", "1", "85")
    user.find("Save").click()

    gutters, lawn = saved_numbers(conn)[::-1]
    await user.should_see(f"{gutters} · Draft")
    await user.should_see(f"{lawn} · Draft")
    assert list_order(user) == [gutters, lawn]


async def test_open_quote_is_highlighted_in_the_list(user, conn):
    first = save_new_quote(conn, Quote())
    second = save_new_quote(conn, Quote())
    await reload(user)

    user.find(marker=f"quote-{first.number}").click()
    await eventually(lambda: active(user, first.number))
    assert not active(user, second.number)


async def test_list_starts_empty(user):
    await user.should_see("No quotes yet")


async def test_search_filters_the_list(user, conn):
    lawn = save_new_quote(conn, Quote(line_items=[LineItem("Mow lawn", Decimal(1), 4500)]))
    gutters = save_new_quote(conn, Quote(notes="Clean gutters"))
    await reload(user)

    user.find(marker="search").type("GUTTER")
    await user.should_see(f"{gutters.number} · Draft")
    await user.should_not_see(f"{lawn.number} · Draft")

    user.find(marker="search").clear().type("snow")
    await user.should_see("No quotes found")


async def test_open_a_quote_deleted_since_listed(user, conn):
    saved = save_new_quote(conn, Quote())
    await reload(user)
    conn.execute("DELETE FROM quotes")
    conn.commit()

    user.find(marker=f"quote-{saved.number}").click()
    await user.should_see(f"No quote {saved.number}")
    await user.should_see("No quotes yet")


async def test_new_quote_after_saving(user, conn):
    fill_line(user, 1, "Mow lawn", "1", "45")
    user.find("Save").click()
    user.find("New Quote").click()

    await user.should_see("Add Line")
    await user.should_not_see("(Draft)")


def test_short_date_is_local(monkeypatch):
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    try:
        # 02:00 UTC on Oct 20 is still Oct 19 in New York.
        assert short_date(datetime(2026, 10, 20, 2, 0, tzinfo=UTC)) == "Oct 19, 2026"
    finally:
        monkeypatch.undo()
        time.tzset()
