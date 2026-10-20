"""The page, driven by NiceGUI's simulated user: no browser or window."""

import asyncio
import time
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from quote_builder.app import quote_page, short_date
from quote_builder.quotes import LineItem, Quote, Status, revision_draft
from quote_builder.storage import (
    connect,
    load_quote,
    mark_quoted,
    save_new_quote,
    save_revision,
)


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "quotes.db")
    yield conn
    conn.close()


TODAY = date(2026, 10, 19)


@pytest.fixture
async def user(conn):
    # A fixed today, so quotes made in tests don't expire as time passes.
    async with user_simulation(root=quote_page(conn, today=lambda: TODAY)) as user:
        await user.open("/")
        yield user


def fill_line(user, n, description, quantity, price):
    user.find(marker=f"description-{n}").type(description)
    user.find(marker=f"quantity-{n}").clear().type(quantity)
    user.find(marker=f"price-{n}").type(price)


def text(found):
    """The text of the one label found."""
    [element] = found.elements
    return element.text


def value(found):
    """The value of the one element found."""
    [element] = found.elements
    return element.value


async def new_quote(user):
    """Click New Quote and wait for the form (the click may ask first)."""
    user.find("New Quote").click()
    await eventually(lambda: heading(user) == "New Quote")


def heading(user):
    """The open quote's heading, or None if no quote is open."""
    try:
        return text(user.find(marker="heading"))
    except AssertionError:
        return None


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
    await new_quote(user)
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
    await new_quote(user)
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
    await new_quote(user)
    fill_line(user, 1, "Mow lawn", "1", "45")
    user.find("Add Line").click()
    fill_line(user, 2, "Trim hedges", "2", "lots")
    user.find("Save").click()

    await user.should_see("Line 2: 'lots' isn't an amount")
    assert saved_numbers(conn) == []


async def test_line_needs_a_description(user, conn):
    await new_quote(user)
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
    await new_quote(user)
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
    await user.should_see(f"{saved.number} (Draft)")
    user.find("Save").click()

    assert load_quote(conn, saved.number) == saved


ISSUED = date(2026, 10, 19)
VALID_UNTIL = date(2026, 11, 18)


async def test_open_a_quoted_quote_read_only(user, conn):
    quote = Quote(line_items=[LineItem("Mow lawn", Decimal("1"), 4500)])
    saved = mark_quoted(conn, quote, ISSUED, VALID_UNTIL)

    await reload(user)
    user.find(marker=f"quote-{saved.number}").click()

    await user.should_see(f"{saved.number} (Quoted)")
    await user.should_see("Mow lawn: 1 × $45.00")
    await user.should_not_see("Save")


async def test_list_shows_saved_quotes_newest_first(user, conn):
    await new_quote(user)
    fill_line(user, 1, "Mow lawn", "1", "45")
    user.find("Save").click()
    await new_quote(user)
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


async def test_starts_on_the_landing_view(user):
    await user.should_see("Pick a quote on the left, or start a new one.")
    await user.should_not_see("Save")


async def test_new_quote_opens_the_form(user):
    await new_quote(user)
    await user.should_see("Add Line")
    await user.should_not_see("Pick a quote on the left, or start a new one.")


async def test_side_panel_stays_beside_the_quote_at_any_width(user):
    # Quasar's default turns the panel into a pop-over below 1024 pixels.
    [panel] = user.find(marker="side-panel").elements
    assert panel.props["behavior"] == "desktop"


async def test_side_panel_is_wide_enough_for_a_revision(user):
    # At 300, "Q-...-R1 · Quoted" wrapped onto two lines.
    [panel] = user.find(marker="side-panel").elements
    assert panel.props["width"] == "350"  # props from text stay text


async def test_new_quote_after_saving(user, conn):
    await new_quote(user)
    fill_line(user, 1, "Mow lawn", "1", "45")
    user.find("Save").click()
    await new_quote(user)

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


async def test_totals_update_as_you_type(user):
    await new_quote(user)
    fill_line(user, 1, "Trim hedges", "2.5", "30")
    user.find(marker="discount-1").type("10%")
    user.find(marker="tax-1").type("7.25")

    # $75.00 - 10% = $67.50; 7.25% tax on that = $4.89 ($4.894).
    await eventually(lambda: text(user.find(marker="line-total-1")) == "$67.50")
    assert text(user.find(marker="foot-items")) == "$75.00"
    assert text(user.find(marker="foot-discounts")) == "-$7.50"
    assert text(user.find(marker="foot-tax")) == "$4.89"
    assert text(user.find(marker="foot-total")) == "$72.39"


async def test_new_quote_starts_at_zero(user):
    await new_quote(user)
    await eventually(lambda: text(user.find(marker="foot-total")) == "$0.00")
    assert text(user.find(marker="line-total-1")) == ""


async def test_blank_price_still_needed_to_save(user, conn):
    await new_quote(user)
    user.find(marker="description-1").type("Mow lawn")
    user.find("Save").click()

    await user.should_see("Line 1: An amount is needed")
    assert saved_numbers(conn) == []


async def test_totals_wait_for_a_line_that_doesnt_read(user):
    await new_quote(user)
    fill_line(user, 1, "Trim hedges", "2", "lots")

    await eventually(lambda: text(user.find(marker="line-total-1")) == "—")
    assert text(user.find(marker="foot-total")) == "—"


async def test_discount_over_the_line_is_refused(user, conn):
    await new_quote(user)
    fill_line(user, 1, "Mow lawn", "1", "45")
    user.find(marker="discount-1").type("50")
    user.find("Save").click()

    await user.should_see("Line 1: A discount can't be more than the line")
    assert saved_numbers(conn) == []


async def test_discount_and_tax_are_saved_and_shown_again(user, conn):
    quote = Quote(
        line_items=[
            LineItem("Hedge trimmer blade", Decimal(1), 1899, tax_percent=Decimal("7.25"), discount_cents=200),
            LineItem("Trim hedges", Decimal("2.5"), 3000, discount_percent=Decimal("10")),
        ]
    )
    saved = save_new_quote(conn, quote)
    await reload(user)
    user.find(marker=f"quote-{saved.number}").click()

    await user.should_see(f"{saved.number} (Draft)")
    assert value(user.find(marker="discount-1")) == "$2.00"
    assert value(user.find(marker="tax-1")) == "7.25"
    assert value(user.find(marker="discount-2")) == "10%"
    assert value(user.find(marker="tax-2")) == ""
    user.find("Save").click()
    assert load_quote(conn, saved.number) == saved


async def test_list_shows_each_quotes_total(user, conn):
    saved = save_new_quote(
        conn, Quote(line_items=[LineItem("Mow lawn", Decimal(2), 4500, discount_cents=500)])
    )
    await reload(user)
    assert text(user.find(marker=f"list-total-{saved.number}")) == "$85.00"


async def test_read_only_quote_shows_discounts_tax_and_totals(user, conn):
    quote = Quote(
        line_items=[
            LineItem("Trim hedges", Decimal("2.5"), 3000, discount_percent=Decimal("10"), tax_percent=Decimal("7.25")),
        ],
    )
    saved = mark_quoted(conn, quote, ISSUED, VALID_UNTIL)
    await reload(user)
    user.find(marker=f"quote-{saved.number}").click()

    await user.should_see("Trim hedges: 2.5 × $30.00, less 10%, tax 7.25% = $67.50")
    assert text(user.find(marker="foot-total")) == "$72.39"


DISCARD_QUESTION = "Discard unsaved changes?"


async def test_unchanged_form_leaves_without_asking(user, conn):
    saved = save_new_quote(conn, Quote(line_items=[LineItem("Mow lawn", Decimal(1), 4500)]))
    await reload(user)
    user.find(marker=f"quote-{saved.number}").click()
    await user.should_see(f"{saved.number} (Draft)")

    await new_quote(user)
    await user.should_not_see(DISCARD_QUESTION)


async def test_saved_form_leaves_without_asking(user):
    await new_quote(user)
    fill_line(user, 1, "Mow lawn", "1", "45")
    user.find("Save").click()
    await eventually(lambda: heading(user) != "New Quote")

    await new_quote(user)
    await user.should_not_see(DISCARD_QUESTION)


async def test_change_undone_by_hand_leaves_without_asking(user):
    await new_quote(user)
    user.find(marker="description-1").type("Mow lawn")
    user.find(marker="description-1").clear()

    user.find("New Quote").click()
    await user.should_not_see(DISCARD_QUESTION)


async def test_keep_editing_keeps_the_changes(user):
    await new_quote(user)
    user.find(marker="description-1").type("Mow lawn")

    user.find("New Quote").click()
    await user.should_see(DISCARD_QUESTION)
    await user.should_see("Changes to this new quote haven't been saved.")
    user.find("Keep Editing").click()

    await user.should_not_see(DISCARD_QUESTION)
    assert value(user.find(marker="description-1")) == "Mow lawn"


async def test_discard_opens_the_other_quote(user, conn):
    first = save_new_quote(conn, Quote(line_items=[LineItem("Mow lawn", Decimal(1), 4500)]))
    second = save_new_quote(conn, Quote(line_items=[LineItem("Clean gutters", Decimal(1), 8500)]))
    await reload(user)
    user.find(marker=f"quote-{first.number}").click()
    await user.should_see(f"{first.number} (Draft)")
    user.find(marker="price-1").clear().type("50")

    user.find(marker=f"quote-{second.number}").click()
    await user.should_see(f"Changes to {first.number} haven't been saved.")
    user.find(kind=ui.button, content="Discard").click()

    await user.should_see(f"{second.number} (Draft)")
    assert load_quote(conn, first.number) == first


async def test_clicking_the_open_quote_keeps_the_changes(user, conn):
    saved = save_new_quote(conn, Quote(line_items=[LineItem("Mow lawn", Decimal(1), 4500)]))
    await reload(user)
    user.find(marker=f"quote-{saved.number}").click()
    await user.should_see(f"{saved.number} (Draft)")
    user.find(marker="price-1").clear().type("50")

    user.find(marker=f"quote-{saved.number}").click()
    await user.should_not_see(DISCARD_QUESTION)
    assert value(user.find(marker="price-1")) == "50"


QUOTE_QUESTION = "It can't be edited after this; changes become revisions."


async def test_mark_a_new_quote_quoted(user, conn):
    await new_quote(user)
    fill_line(user, 1, "Mow lawn", "1", "45")
    user.find("Mark Quoted").click()
    await user.should_see("Mark this new quote quoted?")
    user.find(marker="issued-on").clear().type("10/19/2026")
    user.find(marker="valid-until").clear().type("11/18/2026")
    user.find(marker="confirm-quoted").click()

    # The click's handler finishes in the background.
    await eventually(lambda: saved_numbers(conn) != [])
    [number] = saved_numbers(conn)
    await user.should_see(f"{number} (Quoted)")
    await user.should_see("Issued 10/19/2026 · valid through 11/18/2026")
    await user.should_see(f"{number} · Quoted")
    await user.should_not_see("Save")
    quoted = load_quote(conn, number)
    assert quoted.status is Status.QUOTED
    assert quoted.frozen.total_cents == 4500


async def test_marking_quoted_saves_the_forms_changes(user, conn):
    saved = save_new_quote(conn, Quote(line_items=[LineItem("Mow lawn", Decimal(1), 4500)]))
    await reload(user)
    user.find(marker=f"quote-{saved.number}").click()
    await user.should_see(f"{saved.number} (Draft)")
    user.find(marker="price-1").clear().type("50")

    user.find("Mark Quoted").click()
    await user.should_see(f"Mark {saved.number} quoted?")
    user.find(marker="confirm-quoted").click()

    await user.should_see(f"{saved.number} (Quoted)")
    assert load_quote(conn, saved.number).line_items[0].unit_price_cents == 5000


async def test_dates_default_to_today_and_30_days_on(user):
    await new_quote(user)
    fill_line(user, 1, "Mow lawn", "1", "45")
    user.find("Mark Quoted").click()
    await user.should_see(QUOTE_QUESTION)

    assert value(user.find(marker="issued-on")) == "10/19/2026"
    assert value(user.find(marker="valid-until")) == "11/18/2026"


async def test_cancel_leaves_the_draft(user, conn):
    await new_quote(user)
    fill_line(user, 1, "Mow lawn", "1", "45")
    user.find("Mark Quoted").click()
    await user.should_see(QUOTE_QUESTION)
    user.find(kind=ui.button, content="Cancel").click()

    await user.should_not_see(QUOTE_QUESTION)
    assert heading(user) == "New Quote"
    assert value(user.find(marker="description-1")) == "Mow lawn"
    assert saved_numbers(conn) == []


async def test_valid_until_cant_be_before_issued(user, conn):
    await new_quote(user)
    fill_line(user, 1, "Mow lawn", "1", "45")
    user.find("Mark Quoted").click()
    await user.should_see(QUOTE_QUESTION)
    user.find(marker="issued-on").clear().type("2026-10-19")
    user.find(marker="valid-until").clear().type("2026-10-18")
    user.find(marker="confirm-quoted").click()

    await user.should_see("Valid through can't be before the issued date")
    await user.should_see(QUOTE_QUESTION)  # still asking
    assert saved_numbers(conn) == []


async def test_date_that_doesnt_read_is_named(user, conn):
    await new_quote(user)
    fill_line(user, 1, "Mow lawn", "1", "45")
    user.find("Mark Quoted").click()
    await user.should_see(QUOTE_QUESTION)
    user.find(marker="valid-until").clear().type("next month")
    user.find(marker="confirm-quoted").click()

    await user.should_see("'next month' isn't a date like 11/18/2026")
    assert saved_numbers(conn) == []


async def test_line_problem_is_shown_before_asking_for_dates(user, conn):
    await new_quote(user)
    fill_line(user, 1, "Mow lawn", "1", "lots")
    user.find("Mark Quoted").click()

    await user.should_see("Line 1: 'lots' isn't an amount")
    await user.should_not_see(QUOTE_QUESTION)


async def test_quote_with_no_lines_cant_be_quoted(user, conn):
    await new_quote(user)
    user.find(marker="remove-1").click()
    user.find("Mark Quoted").click()

    await user.should_see("Add a line before marking it quoted")
    await user.should_not_see(QUOTE_QUESTION)


def quoted(conn, valid_until=VALID_UNTIL):
    """A quoted quote, issued 9/1/2026, valid through `valid_until`."""
    quote = Quote(line_items=[LineItem("Mow lawn", Decimal(1), 4500)])
    return mark_quoted(conn, quote, date(2026, 9, 1), valid_until)


async def open_saved(user, quote):
    await reload(user)
    user.find(marker=f"quote-{quote.number}").click()
    await eventually(lambda: (heading(user) or "").startswith(quote.number))


def choose(user, choice):
    """Pick an option in the Extend dialog: "7", "30", or "custom"."""
    [radio] = user.find(marker="extend-choice").elements
    radio.value = choice


async def shows_valid_through(user, shown):
    """Wait for the open quote's dates line (not the notification, which
    says the same) to show this valid-through date."""
    await eventually(
        lambda: f"valid through {shown}" in text(user.find(marker="dates"))
    )


async def start_extending(user):
    user.find(kind=ui.button, content="Extend").click()
    await user.should_see(marker="confirm-extend")


async def test_quote_is_good_through_its_last_day(user, conn):
    saved = quoted(conn, valid_until=TODAY)
    await reload(user)
    await user.should_see(f"{saved.number} · Quoted")


async def test_quote_expires_the_day_after(user, conn):
    saved = quoted(conn, valid_until=TODAY - timedelta(days=1))
    await open_saved(user, saved)
    await user.should_see(f"{saved.number} (Expired)")
    await user.should_see(f"{saved.number} · Expired")


async def test_extend_30_days(user, conn):
    saved = quoted(conn)  # valid through 11/18/2026
    await open_saved(user, saved)
    await start_extending(user)
    await user.should_see("Currently valid through 11/18/2026.")
    [radio] = user.find(marker="extend-choice").elements
    assert list(radio.options) == ["30", "7", "custom"]  # 30 first, picked
    assert radio.value == "30"
    await user.should_see("New valid through: 12/18/2026")
    user.find(marker="confirm-extend").click()

    await shows_valid_through(user, "12/18/2026")
    await user.should_see("Extended once; first valid through 11/18/2026")
    assert load_quote(conn, saved.number).valid_until == date(2026, 12, 18)


async def test_extend_7_days(user, conn):
    saved = quoted(conn)
    await open_saved(user, saved)
    await start_extending(user)
    choose(user, "7")
    await user.should_see("New valid through: 11/25/2026")
    user.find(marker="confirm-extend").click()

    await shows_valid_through(user, "11/25/2026")


async def test_extend_an_expired_quote_counts_from_today(user, conn):
    saved = quoted(conn, valid_until=date(2026, 10, 10))
    await open_saved(user, saved)
    await user.should_see(f"{saved.number} (Expired)")
    await start_extending(user)
    await user.should_see("Expired; was valid through 10/10/2026.")
    choose(user, "7")
    await user.should_see("New valid through: 10/26/2026")
    user.find(marker="confirm-extend").click()

    await user.should_see(f"{saved.number} (Quoted)")
    await user.should_see(f"{saved.number} · Quoted")


async def test_extend_to_a_custom_date(user, conn):
    saved = quoted(conn)
    await open_saved(user, saved)
    await start_extending(user)
    choose(user, "custom")
    user.find(marker="new-valid-until").clear().type("11/20/2026")
    await user.should_see("New valid through: 11/20/2026")
    user.find(marker="confirm-extend").click()

    await shows_valid_through(user, "11/20/2026")


async def test_custom_date_must_be_later(user, conn):
    saved = quoted(conn)
    await open_saved(user, saved)
    await start_extending(user)
    choose(user, "custom")
    user.find(marker="new-valid-until").clear().type("11/18/2026")
    user.find(marker="confirm-extend").click()

    await user.should_see("The new date must be later than the current one")
    await user.should_see(marker="confirm-extend")  # still asking
    assert load_quote(conn, saved.number).extensions == []


async def test_cancel_extending_changes_nothing(user, conn):
    saved = quoted(conn)
    await open_saved(user, saved)
    await start_extending(user)
    user.find(kind=ui.button, content="Cancel").click()

    await user.should_not_see(marker="confirm-extend")
    assert load_quote(conn, saved.number) == saved


async def test_draft_has_no_extend_button(user):
    await new_quote(user)
    await user.should_not_see(kind=ui.button, content="Extend")


async def start_revising(user, quote):
    """Open `quote` and click Revise; waits for the revision's form."""
    await open_saved(user, quote)
    user.find(marker="revise").click()
    await eventually(lambda: heading(user) == f"{quote.number}-R1 (New revision)")


async def test_revise_opens_a_copy_not_yet_saved(user, conn):
    saved = quoted(conn)
    await start_revising(user, saved)

    assert value(user.find(marker="description-1")) == "Mow lawn"
    assert value(user.find(marker="price-1")) == "$45.00"
    assert saved_numbers(conn) == [saved.number]  # nothing stored yet
    assert load_quote(conn, saved.number).status is Status.QUOTED


async def test_revise_is_beside_extend(user, conn):
    saved = quoted(conn)
    await open_saved(user, saved)
    [extend] = user.find(kind=ui.button, content="Extend").elements
    [revise] = user.find(marker="revise").elements
    assert extend.parent_slot.parent is revise.parent_slot.parent
    assert extend.id < revise.id  # Extend first, then Revise


async def test_save_a_revision(user, conn):
    saved = quoted(conn)
    await start_revising(user, saved)
    user.find(marker="price-1").clear().type("50")
    user.find("Save").click()

    await user.should_see(f"Saved {saved.number}-R1")
    await eventually(lambda: heading(user) == f"{saved.number}-R1 (Draft)")
    revision = load_quote(conn, saved.number, 1)
    assert revision.line_items[0].unit_price_cents == 5000
    # The list shows one row for the quote: its newest version.
    await user.should_see(f"{saved.number}-R1 · Draft")
    await user.should_not_see(f"{saved.number} · Quoted")


async def test_leaving_an_unchanged_revision_saves_nothing(user, conn):
    saved = quoted(conn)
    await start_revising(user, saved)
    await new_quote(user)

    await user.should_not_see(DISCARD_QUESTION)
    assert load_quote(conn, saved.number, 1) is None


async def test_mark_a_revision_quoted_supersedes_the_one_before(user, conn):
    saved = quoted(conn)
    await start_revising(user, saved)
    user.find("Mark Quoted").click()
    await user.should_see(f"Mark {saved.number}-R1 quoted?")
    user.find(marker="confirm-quoted").click()

    await eventually(lambda: heading(user) == f"{saved.number}-R1 (Quoted)")
    assert load_quote(conn, saved.number, 0).status is Status.SUPERSEDED


async def test_older_version_leads_to_the_draft(user, conn):
    saved = quoted(conn)
    save_revision(conn, revision_draft(saved, 1))
    await reload(user)
    await open_version(user, saved.number, 0)

    await user.should_see(kind=ui.button, content="Extend")  # drawn
    await user.should_not_see(marker="revise")  # the banner leads there
    [button] = user.find(marker="go-to-newest").elements
    assert button.text == "Go to Draft R1"
    user.find(marker="go-to-newest").click()
    await eventually(lambda: heading(user) == f"{saved.number}-R1 (Draft)")


async def test_superseded_version_has_no_revise_or_extend(user, conn):
    saved = quoted(conn)
    mark_quoted(conn, revision_draft(saved, 1), TODAY, VALID_UNTIL, new_revision=True)
    await reload(user)
    await open_version(user, saved.number, 0)

    await user.should_see(f"{saved.number} (Superseded)")
    await user.should_not_see(marker="revise")
    await user.should_not_see(kind=ui.button, content="Extend")


async def test_version_history_lists_versions_newest_first(user, conn):
    saved = quoted(conn)
    save_revision(conn, revision_draft(saved, 1))
    await open_saved(user, saved)  # opens the newest: R1
    user.find(marker="version-history").click()

    await user.should_see(f"Versions of {saved.number}")
    await user.should_see("R1 · Draft")
    await user.should_see("Original · Quoted")
    await user.should_see("Issued 09/01/2026 · valid through 11/18/2026")
    # Elements are numbered in the order drawn: R1's row comes first.
    [original] = user.find(marker="version-0").elements
    [r1] = user.find(marker="version-1").elements
    assert r1.id < original.id


async def test_no_version_history_with_one_version(user, conn):
    saved = quoted(conn)
    await open_saved(user, saved)
    await user.should_not_see(marker="version-history")


async def test_search_finds_a_quote_by_an_older_version(user, conn):
    saved = quoted(conn)  # "Mow lawn"
    save_revision(
        conn,
        replace(
            revision_draft(saved, 1),
            line_items=[LineItem("Edge walks", Decimal(1), 1500)],
        ),
    )
    await reload(user)
    user.find(marker="search").type("mow")
    await user.should_see(f"{saved.number}-R1 · Draft")


def with_edging_draft(conn):
    """A quoted "Mow lawn" quote, and an R1 draft of "Edge walks"."""
    saved = quoted(conn)
    save_revision(
        conn,
        replace(
            revision_draft(saved, 1),
            line_items=[LineItem("Edge walks", Decimal(1), 1500)],
        ),
    )
    return saved


async def test_search_opens_the_older_version_that_matched(user, conn):
    saved = with_edging_draft(conn)
    await reload(user)
    await search_for(user, "mow")
    user.find(marker=f"quote-{saved.number}").click()

    await eventually(lambda: heading(user) == f"{saved.number} (Quoted)")
    await user.should_see(
        "This is an older version. R1 (Draft) is the newest.", marker="older-version"
    )


async def test_search_opens_the_newest_when_it_matched(user, conn):
    saved = with_edging_draft(conn)
    await reload(user)
    await search_for(user, "edge")
    user.find(marker=f"quote-{saved.number}").click()

    await eventually(lambda: heading(user) == f"{saved.number}-R1 (Draft)")
    await user.should_not_see(marker="older-version")


async def test_older_version_banner_goes_to_the_newest(user, conn):
    saved = quoted(conn)
    mark_quoted(conn, revision_draft(saved, 1), TODAY, VALID_UNTIL, new_revision=True)
    await reload(user)
    await open_version(user, saved.number, 0)  # from Version history

    await user.should_see("R1 (Quoted) is the newest", marker="older-version")
    [button] = user.find(marker="go-to-newest").elements
    assert button.text == "Go to R1"
    user.find(marker="go-to-newest").click()
    await eventually(lambda: heading(user) == f"{saved.number}-R1 (Quoted)")
    await user.should_not_see(marker="older-version")


async def open_version(user, number, revision):
    """Open a version through the open quote's Version history."""
    user.find(marker=f"quote-{number}").click()
    await user.should_see(marker="version-history")
    user.find(marker="version-history").click()
    await user.should_see(f"Versions of {number}")
    user.find(marker=f"version-{revision}").click()
    name = number if revision == 0 else f"{number}-R{revision}"
    await eventually(lambda: (heading(user) or "").startswith(f"{name} ("))


def row_html(user, number):
    """The HTML of each highlighted part of a quote's list row."""
    [row] = user.find(marker=f"quote-{number}").elements
    return [
        element.content
        for element in row.descendants()
        if isinstance(element, ui.html)
    ]


async def search_for(user, term):
    user.find(marker="search").type(term)
    await user.should_see(kind=ui.html)  # the list redrawn, highlighted


async def test_search_highlights_the_first_line(user, conn):
    saved = save_new_quote(
        conn, Quote(line_items=[LineItem("Trim hedges", Decimal(1), 3000)])
    )
    await reload(user)
    await search_for(user, "HEDGES")

    assert any(">hedges</mark>" in part for part in row_html(user, saved.number))
    await user.should_not_see(marker=f"match-{saved.number}")


async def test_search_shows_a_match_the_row_hides(user, conn):
    saved = save_new_quote(
        conn,
        Quote(
            notes="Back hedges too.",
            line_items=[LineItem("Mow lawn", Decimal(1), 4500)],
        ),
    )
    await reload(user)
    await search_for(user, "hedges")

    await user.should_see(marker=f"match-{saved.number}")
    parts = row_html(user, saved.number)
    [match] = [part for part in parts if part.startswith("Notes")]
    assert match.startswith("Notes: Back <mark")
    assert ">hedges</mark> too." in match


async def test_search_highlights_the_number(user, conn):
    saved = save_new_quote(
        conn, Quote(line_items=[LineItem("Mow lawn", Decimal(1), 4500)])
    )
    await reload(user)
    await search_for(user, saved.number[2:5].lower())

    [title, _first_line] = row_html(user, saved.number)
    assert title.startswith("Q-<mark")


async def test_typed_html_shows_as_typed(user, conn):
    saved = save_new_quote(
        conn, Quote(line_items=[LineItem("<b>Deck</b> wash", Decimal(1), 4500)])
    )
    await reload(user)
    await search_for(user, "deck")

    [_title, first_line] = row_html(user, saved.number)
    assert first_line.startswith("&lt;b&gt;<mark")


def view_html(user, marker):
    """The highlighted HTML of a part of the open quote, or None if it
    isn't highlighted (no search)."""
    [element] = user.find(marker=marker).elements
    return element.content if isinstance(element, ui.html) else None


async def test_open_quote_highlights_the_search(user, conn):
    saved = mark_quoted(
        conn,
        Quote(
            notes="Back hedges too.",
            line_items=[LineItem("Trim hedges", Decimal(1), 3000)],
        ),
        date(2026, 9, 1),
        VALID_UNTIL,
    )
    await reload(user)
    await search_for(user, "hedges")
    user.find(marker=f"quote-{saved.number}").click()
    await user.should_see(marker="view-notes")

    assert ">hedges</mark>: 1 × $30.00" in view_html(user, "view-line-1")
    assert ">hedges</mark> too." in view_html(user, "view-notes")


async def test_highlights_stay_after_switching_versions(user, conn):
    saved = quoted(conn)  # "Mow lawn"
    mark_quoted(conn, revision_draft(saved, 1), TODAY, VALID_UNTIL, new_revision=True)
    await reload(user)
    await search_for(user, "mow")
    await open_version(user, saved.number, 0)

    await user.should_see(marker="older-version")
    assert view_html(user, "view-line-1").startswith("<mark")


async def test_highlights_follow_the_search(user, conn):
    saved = quoted(conn)  # "Mow lawn"
    await open_saved(user, saved)
    assert view_html(user, "view-line-1") is None

    user.find(marker="search").type("lawn")
    await eventually(lambda: view_html(user, "view-line-1") is not None)
    assert ">lawn</mark>" in view_html(user, "view-line-1")
    user.find(marker="search").clear()
    await eventually(lambda: view_html(user, "view-line-1") is None)


def tinted(user, marker):
    """Whether a field of the form is tinted as holding the search."""
    [field] = user.find(marker=marker).elements
    return "bg-amber-100" in field.classes


async def test_draft_tints_fields_holding_the_search(user, conn):
    saved = save_new_quote(
        conn,
        Quote(
            notes="Back hedges too.",
            line_items=[
                LineItem("Mow lawn", Decimal(1), 4500),
                LineItem("Trim hedges", Decimal(1), 3000),
            ],
        ),
    )
    await reload(user)
    await search_for(user, "hedges")
    user.find(marker=f"quote-{saved.number}").click()
    await eventually(lambda: heading(user) == f"{saved.number} (Draft)")

    assert not tinted(user, "description-1")
    assert tinted(user, "description-2")
    assert tinted(user, "notes")


async def test_draft_tints_follow_the_search_and_typing(user, conn):
    await new_quote(user)
    user.find(marker="description-1").type("Trim hedges")
    assert not tinted(user, "description-1")  # no search yet

    user.find(marker="search").type("hedges")
    await eventually(lambda: tinted(user, "description-1"))
    user.find(marker="description-1").clear().type("Mow lawn")
    await eventually(lambda: not tinted(user, "description-1"))
    user.find(marker="notes").type("Hedges next time")
    await eventually(lambda: tinted(user, "notes"))
    user.find(marker="search").clear()
    await eventually(lambda: not tinted(user, "notes"))
    # The form wasn't drawn again: what was typed is still there.
    assert value(user.find(marker="notes")) == "Hedges next time"


async def test_no_highlighting_without_a_search(user, conn):
    save_new_quote(conn, Quote(notes="Back hedges too."))
    await reload(user)
    await user.should_see("No lines")
    await user.should_not_see(kind=ui.html)
