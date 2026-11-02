"""The page, driven by NiceGUI's simulated user: no browser or window."""

import asyncio
import time
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from nicegui import events, ui
from nicegui.testing.user_simulation import user_simulation

from quote_builder.app import quote_page, short_date
from quote_builder.business import Business, TaxPart, TaxRate
from quote_builder.catalog import CatalogItem
from quote_builder.customers import Customer
from quote_builder.quotes import LineItem, Quote, Status, revision_draft
from quote_builder.storage import (
    add_business,
    add_customer,
    connect,
    current_business,
    list_businesses,
    list_catalog_items,
    list_customers,
    list_quotes,
    list_tax_rates,
    load_quote,
    mark_quoted,
    pick_business,
    save_business,
    save_catalog_item,
    save_new_quote,
    save_revision,
    save_tax_rate,
)


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "quotes.db")
    current_business(conn)  # made first, so its id is BUSINESS
    yield conn
    conn.close()


BUSINESS = 1  # the business made on first start, which the page shows


def make_quote(**fields):
    """A Quote of BUSINESS, as each needs a business to be saved."""
    return Quote(business_id=BUSINESS, **fields)


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
    quote = make_quote(
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
    quote = make_quote(line_items=[LineItem("Trim hedges", Decimal("2.5"), 123456)])
    saved = save_new_quote(conn, quote)

    await reload(user)
    user.find(marker=f"quote-{saved.number}").click()
    await user.should_see(f"{saved.number} (Draft)")
    user.find("Save").click()

    assert load_quote(conn, saved.number) == saved


ISSUED = date(2026, 10, 19)
VALID_UNTIL = date(2026, 11, 18)


async def test_open_a_quoted_quote_read_only(user, conn):
    quote = make_quote(line_items=[LineItem("Mow lawn", Decimal("1"), 4500)])
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
    first = save_new_quote(conn, make_quote())
    second = save_new_quote(conn, make_quote())
    await reload(user)

    user.find(marker=f"quote-{first.number}").click()
    await eventually(lambda: active(user, first.number))
    assert not active(user, second.number)


async def test_list_starts_empty(user):
    await user.should_see("No quotes yet")


async def test_search_filters_the_list(user, conn):
    lawn = save_new_quote(conn, make_quote(line_items=[LineItem("Mow lawn", Decimal(1), 4500)]))
    gutters = save_new_quote(conn, make_quote(notes="Clean gutters"))
    await reload(user)

    user.find(marker="search").type("GUTTER")
    await user.should_see(f"{gutters.number} · Draft")
    await user.should_not_see(f"{lawn.number} · Draft")

    user.find(marker="search").clear().type("snow")
    await user.should_see("No quotes found")


async def test_open_a_quote_deleted_since_listed(user, conn):
    saved = save_new_quote(conn, make_quote())
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


def rate_725(conn, **changes):
    """A 7.25% rate, the business's default unless changed."""
    parts = [TaxPart("", Decimal("7.25"))]
    return home_county(conn, parts=parts, is_default=True, **changes)


async def test_totals_update_as_you_type(user, conn):
    rate_725(conn)
    await new_quote(user)
    fill_line(user, 1, "Trim hedges", "2.5", "30")
    user.find(marker="discount-1").type("10%")
    user.find(marker="taxed-1").click()

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
    rate = rate_725(conn)
    quote = make_quote(
        tax_rate_id=rate.id,
        line_items=[
            LineItem("Hedge trimmer blade", Decimal(1), 1899, taxed=True, discount_cents=200),
            LineItem("Trim hedges", Decimal("2.5"), 3000, discount_percent=Decimal("10")),
        ],
    )
    saved = load_quote(conn, save_new_quote(conn, quote).number)
    await reload(user)
    user.find(marker=f"quote-{saved.number}").click()

    await user.should_see(f"{saved.number} (Draft)")
    assert value(user.find(marker="tax-rate")) == rate.id
    assert value(user.find(marker="discount-1")) == "$2.00"
    assert value(user.find(marker="taxed-1")) is True
    assert value(user.find(marker="discount-2")) == "10%"
    assert value(user.find(marker="taxed-2")) is False
    user.find("Save").click()
    assert load_quote(conn, saved.number) == saved


async def test_list_shows_each_quotes_total(user, conn):
    saved = save_new_quote(
        conn, make_quote(line_items=[LineItem("Mow lawn", Decimal(2), 4500, discount_cents=500)])
    )
    await reload(user)
    assert text(user.find(marker=f"list-total-{saved.number}")) == "$85.00"


async def test_read_only_quote_shows_discounts_tax_and_totals(user, conn):
    quote = make_quote(
        tax_rate_id=rate_725(conn).id,
        line_items=[
            LineItem("Trim hedges", Decimal("2.5"), 3000, discount_percent=Decimal("10"), taxed=True),
        ],
    )
    saved = mark_quoted(conn, quote, ISSUED, VALID_UNTIL)
    await reload(user)
    user.find(marker=f"quote-{saved.number}").click()

    await user.should_see("Trim hedges: 2.5 × $30.00, less 10%, taxed = $67.50")
    assert text(user.find(marker="view-tax-rate")) == "Tax: Home county 7.25%"
    assert text(user.find(marker="foot-total")) == "$72.39"


async def test_an_untaxed_quote_says_so(user, conn):
    saved = mark_quoted(conn, make_quote(), ISSUED, VALID_UNTIL)
    await reload(user)
    user.find(marker=f"quote-{saved.number}").click()
    await user.should_see(marker="view-tax-rate")
    assert text(user.find(marker="view-tax-rate")) == "Tax: Untaxed"


async def test_a_new_quote_starts_on_the_default_rate(user, conn):
    home_county(conn)  # not the default
    lake = rate_725(conn, name="Lake county")
    await new_quote(user)
    assert value(user.find(marker="tax-rate")) == lake.id


async def test_a_new_quote_without_a_default_is_untaxed(user, conn):
    home_county(conn)
    await new_quote(user)
    assert value(user.find(marker="tax-rate")) == "untaxed"


async def test_a_new_line_is_untaxed_to_start(user):
    await new_quote(user)
    assert value(user.find(marker="taxed-1")) is False


async def test_changing_the_rate_refigures_the_tax(user, conn):
    rate_725(conn)
    lake = home_county(conn, name="Lake county")  # 6.25%
    await new_quote(user)
    fill_line(user, 1, "Gutter guard", "1", "100")
    user.find(marker="taxed-1").click()
    await eventually(lambda: text(user.find(marker="foot-tax")) == "$7.25")

    [rate] = user.find(marker="tax-rate").elements
    rate.value = lake.id
    await eventually(lambda: text(user.find(marker="foot-tax")) == "$6.25")
    rate.value = "untaxed"
    await eventually(lambda: text(user.find(marker="foot-tax")) == "$0.00")
    assert value(user.find(marker="taxed-1")) is True  # kept for switching back


async def test_a_saved_draft_keeps_its_rate(user, conn):
    rate_725(conn)
    lake = home_county(conn, name="Lake county")
    await new_quote(user)
    fill_line(user, 1, "Gutter guard", "1", "100")
    [rate] = user.find(marker="tax-rate").elements
    rate.value = lake.id
    user.find(kind=ui.button, content="Save").click()

    await user.should_see("Saved")
    [summary] = list_quotes(conn, BUSINESS)
    assert load_quote(conn, summary.number).tax_rate_id == lake.id


async def test_changing_the_rate_counts_as_a_change(user, conn):
    lake = home_county(conn, name="Lake county")
    saved = save_new_quote(conn, make_quote())
    await reload(user)
    user.find(marker=f"quote-{saved.number}").click()
    await user.should_see(f"{saved.number} (Draft)")
    [rate] = user.find(marker="tax-rate").elements
    rate.value = lake.id
    user.find("New Quote").click()

    await user.should_see(DISCARD_QUESTION)


async def test_mark_quoted_shows_the_rate_it_kept(user, conn):
    rate_725(conn)
    await new_quote(user)
    fill_line(user, 1, "Gutter guard", "1", "100")
    user.find(marker="taxed-1").click()
    user.find(kind=ui.button, content="Mark Quoted").click()
    await user.should_see("Mark this new quote quoted?")
    user.find(marker="confirm-quoted").click()

    await user.should_see(marker="view-tax-rate")
    assert text(user.find(marker="view-tax-rate")) == "Tax: Home county 7.25%"
    assert text(user.find(marker="foot-total")) == "$107.25"


async def test_a_rate_a_draft_uses_isnt_deleted(user, conn):
    rate = rate_725(conn)
    save_new_quote(conn, make_quote(tax_rate_id=rate.id))
    await open_settings(user)
    user.find(marker=f"tax-rate-{rate.id}").click()
    await user.should_see("Edit tax rate")
    user.find(marker="delete-tax-rate").click()

    await user.should_see("Home county is used by 1 draft")
    assert list_tax_rates(conn, BUSINESS) == [rate]


DISCARD_QUESTION = "Discard unsaved changes?"


async def test_unchanged_form_leaves_without_asking(user, conn):
    saved = save_new_quote(conn, make_quote(line_items=[LineItem("Mow lawn", Decimal(1), 4500)]))
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
    first = save_new_quote(conn, make_quote(line_items=[LineItem("Mow lawn", Decimal(1), 4500)]))
    second = save_new_quote(conn, make_quote(line_items=[LineItem("Clean gutters", Decimal(1), 8500)]))
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
    saved = save_new_quote(conn, make_quote(line_items=[LineItem("Mow lawn", Decimal(1), 4500)]))
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
    saved = save_new_quote(conn, make_quote(line_items=[LineItem("Mow lawn", Decimal(1), 4500)]))
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


async def test_valid_through_starts_the_business_days_on(user, conn):
    save_business(conn, replace(current_business(conn), valid_days=14))
    await reload(user)
    await new_quote(user)
    fill_line(user, 1, "Mow lawn", "1", "45")
    user.find("Mark Quoted").click()
    await user.should_see(QUOTE_QUESTION)

    assert value(user.find(marker="valid-until")) == "11/02/2026"


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
    quote = make_quote(line_items=[LineItem("Mow lawn", Decimal(1), 4500)])
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


def extend_choice(user):
    [radio] = user.find(marker="extend-choice").elements
    return radio.value


async def test_extend_setting_of_7_picks_7_days(user, conn):
    save_business(conn, replace(current_business(conn), extend_days=7))
    saved = quoted(conn)  # valid through 11/18/2026
    await open_saved(user, saved)
    await start_extending(user)

    assert extend_choice(user) == "7"
    await user.should_see("New valid through: 11/25/2026")


async def test_extend_setting_of_other_days_picks_a_custom_date(user, conn):
    save_business(conn, replace(current_business(conn), extend_days=14))
    saved = quoted(conn)  # valid through 11/18/2026
    await open_saved(user, saved)
    await start_extending(user)

    assert extend_choice(user) == "custom"
    assert value(user.find(marker="new-valid-until")) == "12/02/2026"
    await user.should_see("New valid through: 12/02/2026")


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
        conn, make_quote(line_items=[LineItem("Trim hedges", Decimal(1), 3000)])
    )
    await reload(user)
    await search_for(user, "HEDGES")

    assert any(">hedges</mark>" in part for part in row_html(user, saved.number))
    await user.should_not_see(marker=f"match-{saved.number}")


async def test_search_shows_a_match_the_row_hides(user, conn):
    saved = save_new_quote(
        conn,
        make_quote(
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
        conn, make_quote(line_items=[LineItem("Mow lawn", Decimal(1), 4500)])
    )
    await reload(user)
    await search_for(user, saved.number[2:5].lower())

    [title, _first_line] = row_html(user, saved.number)
    assert title.startswith("Q-<mark")


async def test_typed_html_shows_as_typed(user, conn):
    saved = save_new_quote(
        conn, make_quote(line_items=[LineItem("<b>Deck</b> wash", Decimal(1), 4500)])
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
        make_quote(
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
        make_quote(
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
    save_new_quote(conn, make_quote(notes="Back hedges too."))
    await reload(user)
    await user.should_see("No lines")
    await user.should_not_see(kind=ui.html)


async def open_settings(user):
    """Open Settings, on the business whose quotes were shown."""
    user.find(marker="settings").click()
    await user.should_see(marker="business-name")


async def back_to_quotes(user):
    user.find(marker="back-to-quotes").click()
    await user.should_see("New Quote")


async def test_settings_start_at_30_days_and_extend_unset(user):
    await open_settings(user)
    assert value(user.find(marker="business-valid-days")) == "30"
    assert value(user.find(marker="business-extend-days")) == ""


async def test_save_and_clear_the_extend_setting(user, conn):
    await open_settings(user)
    user.find(marker="business-extend-days").type("14")
    user.find(kind=ui.button, content="Save").click()
    await user.should_see("Settings saved")
    assert current_business(conn).extend_days == 14

    await eventually(lambda: value(user.find(marker="business-extend-days")) == "14")
    user.find(marker="business-extend-days").clear()
    user.find(kind=ui.button, content="Save").click()
    await eventually(lambda: current_business(conn).extend_days is None)


async def test_settings_say_which_days_dont_read(user, conn):
    await open_settings(user)
    user.find(marker="business-extend-days").type("a week")
    user.find(kind=ui.button, content="Save").click()

    await user.should_see("Extend by: Days must be a whole number above 0")
    assert current_business(conn).extend_days is None


async def test_save_settings(user, conn):
    await open_settings(user)
    user.find(marker="business-valid-days").clear().type("14")
    user.find(kind=ui.button, content="Save").click()

    await user.should_see("Settings saved")
    assert current_business(conn).valid_days == 14
    await back_to_quotes(user)  # saved: leaves without asking
    await user.should_not_see(DISCARD_QUESTION)


async def test_settings_refuse_days_that_dont_read(user, conn):
    await open_settings(user)
    user.find(marker="business-valid-days").clear().type("two weeks")
    user.find(kind=ui.button, content="Save").click()

    await user.should_see("Quotes valid for: Days must be a whole number above 0")
    assert current_business(conn).valid_days == 30


async def test_settings_refuse_blank_valid_days(user, conn):
    await open_settings(user)
    user.find(marker="business-valid-days").clear()
    user.find(kind=ui.button, content="Save").click()

    await user.should_see("Quotes valid for: Days must be a whole number above 0")
    assert current_business(conn).valid_days == 30


def title(user):
    return text(user.find(marker="title"))


def is_italic(user):
    [label] = user.find(marker="title").elements
    return "italic" in label.classes


async def test_the_top_left_shows_the_name_once_given(user, conn):
    assert title(user) == "Quote Builder"
    await open_settings(user)
    user.find(marker="business-name").type("  John Doe's Lawn Service ")
    user.find(kind=ui.button, content="Save").click()

    await user.should_see("Settings saved")
    assert current_business(conn).name == "John Doe's Lawn Service"
    await back_to_quotes(user)
    await eventually(lambda: title(user) == "John Doe's Lawn Service")
    assert not is_italic(user)


async def test_a_pilots_name_is_in_italics(user, conn):
    await open_settings(user)
    [kind] = user.find(marker="business-kind").elements
    kind.value = "pilot"
    user.find(marker="business-name").type("Pressure washing")
    user.find(kind=ui.button, content="Save").click()

    await user.should_see("Settings saved")
    assert current_business(conn).pilot is True
    await back_to_quotes(user)
    await eventually(lambda: title(user) == "Pressure washing")
    assert is_italic(user)


async def test_a_pilot_without_a_name_shows_quote_builder(user, conn):
    save_business(conn, replace(current_business(conn), pilot=True))
    await reload(user)
    assert title(user) == "Quote Builder"
    assert not is_italic(user)


async def test_the_name_example_follows_the_kind(user):
    await open_settings(user)
    [kind] = user.find(marker="business-kind").elements
    [name] = user.find(marker="business-name").elements
    assert name.props["placeholder"] == "John Doe's Lawn Service"
    assert "hint" not in name.props

    kind.value = "pilot"
    await eventually(lambda: name.props["placeholder"] == "Pressure washing")
    assert name.props["hint"] == (
        "An activity name works well. Pilots show in italics in the list."
    )
    kind.value = "business"
    await eventually(lambda: "hint" not in name.props)


async def test_changing_the_kind_counts_as_a_change(user):
    await open_settings(user)
    [kind] = user.find(marker="business-kind").elements
    kind.value = "pilot"
    user.find(marker="back-to-quotes").click()

    await user.should_see(DISCARD_QUESTION)


async def test_leaving_changed_settings_asks(user):
    await open_settings(user)
    user.find(marker="business-valid-days").clear().type("14")
    user.find(marker="back-to-quotes").click()

    await user.should_see(DISCARD_QUESTION)
    await user.should_see("Changes to the settings haven't been saved.")


async def test_settings_take_over_the_side_panel(user):
    user.find(marker="search").type("hedges")
    await open_settings(user)
    await user.should_not_see("New Quote")
    await user.should_not_see(marker="search")
    await user.should_not_see(marker="title")  # no name or dropdown
    await user.should_see("Add business or pilot…")

    await back_to_quotes(user)
    await user.should_not_see("Back to Quotes")
    assert value(user.find(marker="search")) == "hedges"  # kept while away


async def test_settings_name_an_unnamed_business_for_now(user):
    await open_settings(user)
    assert heading(user) == "Unnamed business"
    await user.should_see(marker=f"business-{BUSINESS}")


def businesses(conn, *named):
    """Add businesses: a name, or ("Pressure washing", "pilot"). Returns
    them in the order given, with their ids."""
    added = []
    for entry in named:
        name, pilot = (entry, False) if isinstance(entry, str) else (entry[0], True)
        added.append(add_business(conn, Business(name=name, pilot=pilot)))
    return added


def settings_list(user):
    """The ids of the businesses Settings lists, top to bottom."""
    items = user.find(kind=ui.item).elements
    markers = [m for item in sorted(items, key=lambda e: e.id) for m in item._markers]
    return [int(m.removeprefix("business-")) for m in markers if m.startswith("business-")]


async def test_settings_list_businesses_then_pilots_by_name(user, conn):
    save_business(conn, replace(current_business(conn), name="lawn care"))
    gifts, deck, acme = businesses(conn, ("Gift baskets", "pilot"), ("decks", "pilot"), "Acme")
    await open_settings(user)
    assert settings_list(user) == [acme.id, BUSINESS, deck.id, gifts.id]


async def test_add_a_business(user, conn):
    save_business(conn, replace(current_business(conn), name="Joe's Lawn Service"))
    await open_settings(user)
    user.find(marker="add-business").click()
    await eventually(lambda: heading(user) == "New business or pilot")
    [kind] = user.find(marker="business-kind").elements
    kind.value = "pilot"
    user.find(marker="business-name").type("Pressure washing")
    user.find(kind=ui.button, content="Save").click()

    await user.should_see("Settings saved")
    [_, added] = list_businesses(conn)
    assert (added.name, added.pilot) == ("Pressure washing", True)
    await eventually(lambda: heading(user) == "Pressure washing")
    await user.should_see(marker=f"business-{added.id}")
    assert current_business(conn).id == BUSINESS  # still Joe's quotes


async def test_a_new_business_needs_a_name(user, conn):
    await open_settings(user)
    user.find(marker="add-business").click()
    await eventually(lambda: heading(user) == "New business or pilot")
    user.find(kind=ui.button, content="Save").click()

    await user.should_see(NAME_NEEDED)
    assert len(list_businesses(conn)) == 1


NAME_NEEDED = "Name: a name is needed once there's more than one business or pilot"


async def test_a_name_cant_be_cleared_once_there_are_two(user, conn):
    save_business(conn, replace(current_business(conn), name="Joe's Lawn Service"))
    businesses(conn, "Acme")
    await open_settings(user)
    user.find(marker="business-name").clear()
    user.find(kind=ui.button, content="Save").click()

    await user.should_see(NAME_NEEDED)
    assert current_business(conn).name == "Joe's Lawn Service"


async def test_settings_open_another_business(user, conn):
    save_business(conn, replace(current_business(conn), name="Joe's Lawn Service"))
    [acme] = businesses(conn, "Acme")
    await open_settings(user)
    user.find(marker=f"business-{acme.id}").click()

    await eventually(lambda: heading(user) == "Acme")
    assert current_business(conn).id == BUSINESS  # only its settings opened


async def test_opening_another_business_with_changes_asks(user, conn):
    save_business(conn, replace(current_business(conn), name="Joe's Lawn Service"))
    [acme] = businesses(conn, "Acme")
    await open_settings(user)
    user.find(marker="business-valid-days").clear().type("14")
    user.find(marker=f"business-{acme.id}").click()

    await user.should_see(DISCARD_QUESTION)


async def test_one_business_has_no_dropdown(user, conn):
    save_business(conn, replace(current_business(conn), name="Joe's Lawn Service"))
    await reload(user)
    await user.should_not_see(kind=ui.dropdown_button)


async def test_the_dropdown_switches_business(user, conn):
    save_business(conn, replace(current_business(conn), name="Joe's Lawn Service"))
    [washing] = businesses(conn, ("Pressure washing", "pilot"))
    lawn = save_new_quote(conn, make_quote(notes="Mow"))
    deck = save_new_quote(conn, replace(make_quote(notes="Deck"), business_id=washing.id))
    await reload(user)
    assert title(user) == "Joe's Lawn Service"
    assert list_order(user) == [lawn.number]

    user.find(marker=f"pick-{washing.id}").click()
    await eventually(lambda: title(user) == "Pressure washing")
    assert is_italic(user)
    await eventually(lambda: list_order(user) == [deck.number])
    assert current_business(conn).id == washing.id  # opened on next time


async def test_switching_business_with_changes_asks(user, conn):
    save_business(conn, replace(current_business(conn), name="Joe's Lawn Service"))
    [acme] = businesses(conn, "Acme")
    await reload(user)
    await new_quote(user)
    user.find(marker="description-1").type("Mow lawn")
    user.find(marker=f"pick-{acme.id}").click()

    await user.should_see(DISCARD_QUESTION)
    assert current_business(conn).id == BUSINESS


async def test_a_new_quote_belongs_to_the_business_shown(user, conn):
    save_business(conn, replace(current_business(conn), name="Joe's Lawn Service"))
    [acme] = businesses(conn, "Acme")
    pick_business(conn, acme.id)
    await reload(user)
    await new_quote(user)
    fill_line(user, 1, "Paint fence", "1", "300")
    user.find(kind=ui.button, content="Save").click()

    await user.should_see("Saved")
    [summary] = list_quotes(conn, acme.id)
    assert load_quote(conn, summary.number).business_id == acme.id
    assert list_quotes(conn, BUSINESS) == []


async def test_search_covers_only_the_business_shown(user, conn):
    [acme] = businesses(conn, "Acme")
    save_new_quote(conn, replace(make_quote(notes="Hedges"), business_id=acme.id))
    await reload(user)
    user.find(marker="search").type("hedges")
    await user.should_see("No quotes found")


async def add_tax_rate(user):
    user.find(marker="add-tax-rate").click()
    # Not should_see("Add tax rate"): the button's label holds it too.
    await user.should_see(marker="tax-rate-name")


def home_county(conn, **changes):
    rate = TaxRate(
        BUSINESS,
        "Home county",
        [TaxPart("State", Decimal("4.75")), TaxPart("County", Decimal("1.5"))],
    )
    return save_tax_rate(conn, replace(rate, **changes))


async def test_add_a_tax_rate(user, conn):
    await open_settings(user)
    await add_tax_rate(user)
    user.find(marker="tax-rate-name").type("Home county")
    user.find(marker="part-name-1").type("State")
    user.find(marker="part-percent-1").type("4.75")
    user.find(marker="add-part").click()
    user.find(marker="part-name-2").type("County")
    user.find(marker="part-percent-2").type("1.5%")
    await eventually(lambda: text(user.find(marker="combined")) == "Combined: 6.25%")
    user.find(marker="save-tax-rate").click()

    await user.should_see("Saved Home county")
    [rate] = list_tax_rates(conn, BUSINESS)
    assert rate.parts == [
        TaxPart("State", Decimal("4.75")),
        TaxPart("County", Decimal("1.5")),
    ]
    assert rate.is_default  # the first one is, to start
    await user.should_see("Home county · 6.25% · Default")


async def test_a_parts_example_names_the_kinds(user):
    await open_settings(user)
    await add_tax_rate(user)
    [part] = user.find(marker="part-name-1").elements
    assert part.props["placeholder"] == "State, County, or City, etc."


async def test_combined_waits_for_every_part_to_read(user):
    await open_settings(user)
    await add_tax_rate(user)
    user.find(marker="part-percent-1").type("lots")
    await eventually(lambda: text(user.find(marker="combined")) == "Combined: —")


async def test_a_tax_rate_says_what_doesnt_read(user, conn):
    await open_settings(user)
    await add_tax_rate(user)
    user.find(marker="tax-rate-name").type("Home county")
    user.find(marker="part-percent-1").type("lots")
    user.find(marker="save-tax-rate").click()

    await user.should_see("Part 1: 'lots' isn't a percent")
    assert list_tax_rates(conn, BUSINESS) == []


async def test_a_tax_rate_needs_a_name(user, conn):
    await open_settings(user)
    await add_tax_rate(user)
    user.find(marker="part-percent-1").type("7")
    user.find(marker="save-tax-rate").click()

    await user.should_see("A tax rate needs a name")
    assert list_tax_rates(conn, BUSINESS) == []


async def test_a_tax_rate_needs_a_part(user, conn):
    await open_settings(user)
    await add_tax_rate(user)
    user.find(marker="tax-rate-name").type("Home county")
    user.find(marker="remove-part-1").click()
    user.find(marker="save-tax-rate").click()

    await user.should_see("A tax rate needs at least one part")


async def test_edit_a_tax_rate(user, conn):
    rate = home_county(conn)
    await open_settings(user)
    user.find(marker=f"tax-rate-{rate.id}").click()
    await user.should_see("Edit tax rate")
    assert value(user.find(marker="part-percent-2")) == "1.5"
    user.find(marker="part-percent-2").clear().type("2")
    user.find(marker="save-tax-rate").click()

    await user.should_see("Home county · 6.75%")
    [changed] = list_tax_rates(conn, BUSINESS)
    assert changed.parts[1] == TaxPart("County", Decimal("2"))


async def test_a_second_rate_isnt_the_default_to_start(user, conn):
    home_county(conn, is_default=True)
    await open_settings(user)
    await add_tax_rate(user)
    [default] = user.find(marker="tax-rate-default").elements
    assert default.value is False


async def test_make_another_rate_the_default(user, conn):
    home = home_county(conn, is_default=True)
    lake = home_county(conn, name="Lake county")
    await open_settings(user)
    user.find(marker=f"tax-rate-{lake.id}").click()
    await user.should_see("Edit tax rate")
    [default] = user.find(marker="tax-rate-default").elements
    default.value = True
    user.find(marker="save-tax-rate").click()

    await user.should_see("Lake county · 6.25% · Default")
    await user.should_see("Home county · 6.25%")
    assert [r.id for r in list_tax_rates(conn, BUSINESS) if r.is_default] == [lake.id]
    assert home.id != lake.id


async def test_delete_a_tax_rate(user, conn):
    rate = home_county(conn)
    await open_settings(user)
    user.find(marker=f"tax-rate-{rate.id}").click()
    await user.should_see("Edit tax rate")
    user.find(marker="delete-tax-rate").click()

    await user.should_see("Deleted Home county")
    await user.should_not_see(marker=f"tax-rate-{rate.id}")
    assert list_tax_rates(conn, BUSINESS) == []


async def test_a_new_rate_cant_be_deleted(user):
    await open_settings(user)
    await add_tax_rate(user)
    await user.should_not_see(marker="delete-tax-rate")


async def test_cancel_leaves_tax_rates_alone(user, conn):
    await open_settings(user)
    await add_tax_rate(user)
    user.find(marker="tax-rate-name").type("Home county")
    user.find(kind=ui.button, content="Cancel").click()

    await user.should_not_see(marker="tax-rate-name")
    assert list_tax_rates(conn, BUSINESS) == []


async def test_tax_rates_follow_the_business_shown(user, conn):
    home_county(conn)
    [acme] = businesses(conn, "Acme")
    await open_settings(user)
    await user.should_see("Home county · 6.25%")
    user.find(marker=f"business-{acme.id}").click()

    await eventually(lambda: heading(user) == "Acme")
    await user.should_not_see("Home county · 6.25%")


async def test_a_new_business_gets_tax_rates_once_saved(user):
    await open_settings(user)
    user.find(marker="add-business").click()
    await eventually(lambda: heading(user) == "New business or pilot")
    await user.should_not_see(marker="add-tax-rate")


def mow(conn, **changes):
    item = CatalogItem(BUSINESS, "Mow lawn", 4500, "hour")
    return save_catalog_item(conn, replace(item, **changes))


async def open_catalog(user):
    await open_settings(user)
    user.find(marker="catalog").click()
    await user.should_see(marker="add-catalog-item")


async def add_catalog_item(user):
    user.find(marker="add-catalog-item").click()
    await user.should_see(marker="catalog-description")


def pick_from_catalog(user, item):
    [select] = user.find(marker="add-from-catalog").elements
    with user.client:
        select.value = item.id


async def test_add_a_catalog_item(user, conn):
    await open_catalog(user)
    assert heading(user) == "Catalog: Unnamed business"
    await add_catalog_item(user)
    user.find(marker="catalog-description").type("Mulch")
    user.find(marker="catalog-price").type("$6.50")
    user.find(marker="catalog-unit").type("each")
    user.find(marker="catalog-taxable").click()
    user.find(marker="save-catalog-item").click()

    await user.should_see("Saved Mulch")
    await user.should_see("Mulch · $6.50 / each")
    [item] = list_catalog_items(conn, BUSINESS)
    assert (item.description, item.price_cents, item.unit, item.taxable) == (
        "Mulch",
        650,
        "each",
        True,
    )


async def test_a_catalog_item_needs_only_a_description(user, conn):
    await open_catalog(user)
    await add_catalog_item(user)
    user.find(marker="save-catalog-item").click()
    await user.should_see("A catalog item needs a description")
    assert list_catalog_items(conn, BUSINESS) == []

    user.find(marker="catalog-description").type("Yard cleanup")
    user.find(marker="save-catalog-item").click()
    await user.should_see("Saved Yard cleanup")
    [item] = list_catalog_items(conn, BUSINESS)
    assert item.price_cents is None


async def test_a_catalog_price_says_what_doesnt_read(user, conn):
    await open_catalog(user)
    await add_catalog_item(user)
    user.find(marker="catalog-description").type("Mulch")
    user.find(marker="catalog-price").type("lots")
    user.find(marker="save-catalog-item").click()
    await user.should_see("Default price: 'lots' isn't an amount")
    assert list_catalog_items(conn, BUSINESS) == []


async def test_edit_a_catalog_item(user, conn):
    item = mow(conn)
    await open_catalog(user)
    user.find(marker=f"catalog-item-{item.id}").click()
    await user.should_see("Edit catalog item")
    assert value(user.find(marker="catalog-price")) == "$45.00"
    user.find(marker="catalog-unit").clear().type("flat")
    user.find(marker="save-catalog-item").click()

    await user.should_see("Mow lawn · $45.00 / flat")
    assert list_catalog_items(conn, BUSINESS) == [replace(item, unit="flat")]


async def test_delete_a_catalog_item(user, conn):
    item = mow(conn)
    await open_catalog(user)
    user.find(marker=f"catalog-item-{item.id}").click()
    await user.should_see("Edit catalog item")
    user.find(marker="delete-catalog-item").click()

    await user.should_see("Deleted Mow lawn")
    await user.should_not_see(marker=f"catalog-item-{item.id}")
    assert list_catalog_items(conn, BUSINESS) == []


async def test_a_new_catalog_item_cant_be_deleted(user):
    await open_catalog(user)
    await add_catalog_item(user)
    await user.should_not_see(marker="delete-catalog-item")


async def test_cancel_leaves_the_catalog_alone(user, conn):
    await open_catalog(user)
    await add_catalog_item(user)
    user.find(marker="catalog-description").type("Mulch")
    user.find(kind=ui.button, content="Cancel").click()

    await user.should_not_see(marker="catalog-description")
    assert list_catalog_items(conn, BUSINESS) == []


async def test_catalog_follows_the_business_picked_in_settings(user, conn):
    mow(conn)
    [acme] = businesses(conn, "Acme")
    await open_settings(user)
    user.find(marker=f"business-{acme.id}").click()
    await eventually(lambda: heading(user) == "Acme")
    user.find(marker="catalog").click()

    await eventually(lambda: heading(user) == "Catalog: Acme")
    await user.should_not_see("Mow lawn")


async def test_the_business_open_goes_back_from_its_catalog(user, conn):
    business = current_business(conn)
    await open_catalog(user)
    user.find(marker=f"business-{business.id}").click()
    await user.should_see(marker="business-name")


async def test_a_new_business_gets_a_catalog_once_saved(user):
    await open_settings(user)
    [catalog] = user.find(marker="catalog").elements
    assert catalog.enabled
    user.find(marker="add-business").click()
    await eventually(lambda: heading(user) == "New business or pilot")
    assert not catalog.enabled

    user.find(marker="business-name").type("Acme")
    user.find(kind=ui.button, content="Save").click()
    await eventually(lambda: heading(user) == "Acme")
    assert catalog.enabled


async def test_unsaved_settings_ask_before_opening_the_catalog(user):
    await open_settings(user)
    user.find(marker="business-name").type("Acme")
    user.find(marker="catalog").click()
    await user.should_see("Discard unsaved changes?")


async def test_no_catalog_field_until_theres_an_item(user):
    await new_quote(user)
    await user.should_not_see(marker="add-from-catalog")


async def test_catalog_field_shows_this_businesss_items(user, conn):
    item = mow(conn)
    acme = add_business(conn, Business(name="Acme"))
    other = save_catalog_item(conn, CatalogItem(acme.id, "Acme's item"))
    await new_quote(user)
    [select] = user.find(marker="add-from-catalog").elements
    assert select.options == {item.id: "Mow lawn\n$45.00 / hour"}
    assert other.id not in select.options


async def test_picking_fills_the_blank_line_and_saves(user, conn):
    item = mow(conn, taxable=True)
    await new_quote(user)
    pick_from_catalog(user, item)

    await user.should_see(marker="description-2")
    await user.should_not_see(marker="description-1")
    assert value(user.find(marker="description-2")) == "Mow lawn"
    assert value(user.find(marker="quantity-2")) == "1"
    assert value(user.find(marker="price-2")) == "$45.00"
    [taxed] = user.find(marker="taxed-2").elements
    assert taxed.value
    [select] = user.find(marker="add-from-catalog").elements
    assert select.value is None  # ready for the next pick

    user.find(kind=ui.button, content="Save").click()
    await user.should_see("Saved Q-")
    [summary] = list_quotes(conn, BUSINESS)
    [line] = load_quote(conn, summary.number).line_items
    assert line == LineItem("Mow lawn", Decimal(1), 4500, taxed=True)


async def test_picking_keeps_a_line_already_started(user, conn):
    item = mow(conn)
    await new_quote(user)
    user.find(marker="description-1").type("Trip fee")
    pick_from_catalog(user, item)

    await user.should_see(marker="description-2")
    assert value(user.find(marker="description-1")) == "Trip fee"
    assert value(user.find(marker="description-2")) == "Mow lawn"


async def test_picking_twice_adds_two_lines(user, conn):
    item = mow(conn)
    await new_quote(user)
    pick_from_catalog(user, item)
    await user.should_see(marker="description-2")
    pick_from_catalog(user, item)
    await user.should_see(marker="description-3")
    assert value(user.find(marker="description-2")) == "Mow lawn"
    assert value(user.find(marker="description-3")) == "Mow lawn"


async def test_an_item_without_a_price_leaves_it_to_type(user, conn):
    item = mow(conn, price_cents=None)
    await new_quote(user)
    pick_from_catalog(user, item)
    await user.should_see(marker="description-2")
    assert value(user.find(marker="price-2")) == ""


async def test_a_picked_line_changes_for_this_quote_only(user, conn):
    item = mow(conn)
    await new_quote(user)
    pick_from_catalog(user, item)
    await user.should_see(marker="description-2")
    user.find(marker="price-2").clear().type("50")
    user.find(kind=ui.button, content="Save").click()
    await user.should_see("Saved Q-")

    assert list_catalog_items(conn, BUSINESS) == [item]
    [summary] = list_quotes(conn, BUSINESS)
    [line] = load_quote(conn, summary.number).line_items
    assert line.unit_price_cents == 5000


async def test_changing_the_catalog_leaves_a_line_alone(user, conn):
    item = mow(conn)
    await new_quote(user)
    pick_from_catalog(user, item)
    await user.should_see(marker="description-2")
    user.find(kind=ui.button, content="Save").click()
    await user.should_see("Saved Q-")
    [summary] = list_quotes(conn, BUSINESS)

    save_catalog_item(conn, replace(item, price_cents=9900))
    [line] = load_quote(conn, summary.number).line_items
    assert line.unit_price_cents == 4500


async def test_a_picked_line_counts_as_a_change(user, conn):
    item = mow(conn)
    await new_quote(user)
    pick_from_catalog(user, item)
    await user.should_see(marker="description-2")
    user.find(marker="settings").click()
    await user.should_see("Discard unsaved changes?")


def description_field(user, n):
    [field] = user.find(marker=f"description-{n}").elements
    return field


def add_to_catalog_slot(user, n, kind):
    """A slot's child, as user.find doesn't look in slots."""
    [child] = [
        element
        for element in description_field(user, n).slots["append"].children
        if isinstance(element, kind)
    ]
    return child


def add_to_catalog_button(user, n):
    return add_to_catalog_slot(user, n, ui.button)


def description_hover(user, n):
    [hover] = description_field(user, n).default_slot.children
    return hover


async def click_add_to_catalog(user, n):
    send(user, add_to_catalog_button(user, n), "click")
    await user.should_see(marker="catalog-description")


async def test_a_lines_box_is_labeled_tax(user):
    await new_quote(user)
    [box] = user.find(marker="taxed-1").elements
    assert box.text == "Tax"


async def test_add_to_catalog_waits_for_a_description(user):
    await new_quote(user)
    assert not add_to_catalog_button(user, 1).visible
    user.find(marker="description-1").type("Mulch")
    await eventually(lambda: add_to_catalog_button(user, 1).visible)
    user.find(marker="description-1").clear()
    await eventually(lambda: not add_to_catalog_button(user, 1).visible)


async def test_add_to_catalog_has_its_hint(user):
    await new_quote(user)
    hint = add_to_catalog_slot(user, 1, ui.tooltip)
    assert hint.text == "Add to Catalog"
    assert hint.props["target"] == f"#{add_to_catalog_button(user, 1).html_id}"


async def test_tab_skips_add_to_catalog(user):
    await new_quote(user)
    assert add_to_catalog_button(user, 1).props["tabindex"] == "-1"


async def test_hovering_shows_the_full_description(user):
    await new_quote(user)
    assert not description_hover(user, 1).visible
    user.find(marker="description-1").type("Mow lawn, front and back")
    await eventually(
        lambda: description_hover(user, 1).text == "Mow lawn, front and back"
    )
    assert description_hover(user, 1).visible


async def test_a_long_description_is_cut_off_with_dots(user):
    await new_quote(user)
    assert description_field(user, 1).props["input-class"] == "truncate"


async def test_add_a_line_to_the_catalog(user, conn):
    await new_quote(user)
    fill_line(user, 1, " Mulch ", "3", "$6.50")
    user.find(marker="taxed-1").click()
    await eventually(lambda: add_to_catalog_button(user, 1).visible)
    await click_add_to_catalog(user, 1)
    assert value(user.find(marker="catalog-description")) == "Mulch"
    assert value(user.find(marker="catalog-price")) == "$6.50"
    assert value(user.find(marker="catalog-unit")) == ""
    [taxable] = user.find(marker="catalog-taxable").elements
    assert taxable.value
    user.find(marker="catalog-unit").type("each")
    user.find(marker="save-catalog-item").click()

    await user.should_see("Added Mulch to the catalog")
    [item] = list_catalog_items(conn, BUSINESS)
    assert (item.description, item.price_cents, item.unit, item.taxable) == (
        "Mulch",
        650,
        "each",
        True,
    )
    # The line stays as it was, and can be picked again at once.
    assert value(user.find(marker="quantity-1")) == "3"
    [select] = user.find(marker="add-from-catalog").elements
    assert select.visible
    assert select.options == {item.id: "Mulch\n$6.50 / each"}
    pick_from_catalog(user, item)
    await user.should_see(marker="description-2")


async def test_a_price_that_doesnt_read_starts_blank(user):
    await new_quote(user)
    fill_line(user, 1, "Mulch", "1", "lots")
    await eventually(lambda: add_to_catalog_button(user, 1).visible)
    await click_add_to_catalog(user, 1)
    assert value(user.find(marker="catalog-price")) == ""


async def test_cancel_adds_nothing_to_the_catalog(user, conn):
    await new_quote(user)
    user.find(marker="description-1").type("Mulch")
    await eventually(lambda: add_to_catalog_button(user, 1).visible)
    await click_add_to_catalog(user, 1)
    user.find(kind=ui.button, content="Cancel").click()

    await user.should_not_see(marker="catalog-description")
    assert list_catalog_items(conn, BUSINESS) == []
    await user.should_not_see(marker="add-from-catalog")


async def test_adding_to_the_catalog_isnt_a_change_to_the_quote(user, conn):
    quote = save_new_quote(
        conn,
        make_quote(line_items=[LineItem("Mulch", Decimal(1), 650)]),
    )
    await reload(user)
    user.find(marker=f"quote-{quote.number}").click()
    await user.should_see(marker="description-1")
    await click_add_to_catalog(user, 1)
    user.find(marker="save-catalog-item").click()
    await user.should_see("Added Mulch to the catalog")

    user.find(marker="settings").click()
    await user.should_see(marker="add-business")
    await user.should_not_see("Discard unsaved changes?")


def jane(conn, **changes):
    customer = Customer(
        BUSINESS, "Jane Doe", "jane@example.com", "555-0134", "12 Oak St"
    )
    return add_customer(conn, replace(customer, **changes))


def customer_field(user):
    [select] = user.find(marker="customer").elements
    return select


def send(user, element, event, args=None):
    """Send `element` a browser event, for what the simulated user can't
    do: type in a select, or click in its list of choices (a Quasar
    slot, which user.find doesn't look in)."""
    with user.client:
        for listener in element._event_listeners.values():
            if listener.type == event:
                events.handle_event(
                    listener.handler,
                    events.GenericEventArguments(
                        sender=element, client=user.client, args=args
                    ),
                )


async def add_customer_from(user, typed):
    """Type in the Customer field, then click Add customer, below the
    choices. (The browser narrows the choices itself.)"""
    select = customer_field(user)
    send(user, select, "inputValue", typed)  # NiceGUI's name for input-value
    [add] = select.slots["after-options"].children
    [label] = [e for e in add.descendants() if isinstance(e, ui.item_label)]
    expected = f'Add customer "{typed}"…' if typed else "Add customer…"
    await eventually(lambda: label.text == expected)
    send(user, add, "click")
    await user.should_see(marker="customer-name")


def row_texts(user, number):
    """The texts of a quote's row in the list, top to bottom."""
    [row] = user.find(marker=f"quote-{number}").elements
    labels = [e for e in row.descendants() if isinstance(e, ui.item_label)]
    return [label.text for label in sorted(labels, key=lambda e: e.id)]


async def test_pick_a_customer_and_save(user, conn):
    doe = jane(conn)
    await new_quote(user)
    customer_field(user).value = doe.id
    await eventually(
        lambda: text(user.find(marker="customer-details"))
        == "12 Oak St · 555-0134 · jane@example.com"
    )
    fill_line(user, 1, "Mow lawn", "1", "45")
    user.find(kind=ui.button, content="Save").click()

    await user.should_see("Saved Q-")
    [number] = saved_numbers(conn)
    assert load_quote(conn, number).customer == doe


async def test_add_a_customer_from_what_was_typed(user, conn):
    await new_quote(user)
    await add_customer_from(user, "Pat Newby")
    assert value(user.find(marker="customer-name")) == "Pat Newby"
    user.find(marker="customer-phone").type("555-0111")
    user.find(marker="save-customer").click()

    await user.should_see("Added Pat Newby")
    [pat] = list_customers(conn, BUSINESS)
    assert (pat.name, pat.phone) == ("Pat Newby", "555-0111")
    assert customer_field(user).value == pat.id
    assert text(user.find(marker="customer-details")) == "555-0111"


async def test_a_customer_needs_a_name(user, conn):
    await new_quote(user)
    await add_customer_from(user, "")
    user.find(marker="save-customer").click()

    await user.should_see("A customer needs a name")
    assert list_customers(conn, BUSINESS) == []


async def test_a_same_named_customer_asks_first(user, conn):
    doe = jane(conn)
    await new_quote(user)
    await add_customer_from(user, "jane  doe")
    user.find(marker="save-customer").click()

    await user.should_see(marker="same-name")
    assert text(user.find(marker="same-name")) == (
        "There's already a Jane Doe (12 Oak St · 555-0134 · jane@example.com)."
        " Add another anyway?"
    )
    assert list_customers(conn, BUSINESS) == [doe]
    user.find(marker="add-another").click()

    await user.should_see("Added jane doe")  # as typed, spaces tidied
    [new] = [c for c in list_customers(conn, BUSINESS) if c.id != doe.id]
    assert customer_field(user).value == new.id


async def test_use_the_same_named_customer_instead(user, conn):
    doe = jane(conn)
    await new_quote(user)
    await add_customer_from(user, "Jane Doe")
    user.find(marker="save-customer").click()
    await user.should_see(marker="same-name")
    user.find(marker="use-that-one").click()

    await user.should_not_see(marker="customer-name")
    assert list_customers(conn, BUSINESS) == [doe]
    assert customer_field(user).value == doe.id


async def test_several_same_named_customers(user, conn):
    jane(conn)
    jane(conn, address="48 Elm Rd")
    await new_quote(user)
    await add_customer_from(user, "Jane Doe")
    user.find(marker="save-customer").click()

    await user.should_see(marker="same-name")
    assert text(user.find(marker="same-name")) == (
        "There are already 2 customers named Jane Doe. Add another anyway?"
    )
    await user.should_not_see(marker="use-that-one")


async def test_a_changed_name_no_longer_warns(user, conn):
    jane(conn)
    await new_quote(user)
    await add_customer_from(user, "Jane Doe")
    user.find(marker="save-customer").click()
    await user.should_see(marker="same-name")
    user.find(marker="customer-name").type("ring")

    await user.should_not_see(marker="same-name")
    user.find(marker="save-customer").click()
    await user.should_see("Added Jane Doering")


async def test_changing_the_customer_counts_as_a_change(user, conn):
    doe = jane(conn)
    saved = save_new_quote(conn, make_quote())
    await reload(user)
    user.find(marker=f"quote-{saved.number}").click()
    await user.should_see(f"{saved.number} (Draft)")
    customer_field(user).value = doe.id
    user.find("New Quote").click()

    await user.should_see(DISCARD_QUESTION)


async def test_mark_quoted_shows_the_customer_it_kept(user, conn):
    doe = jane(conn)
    await new_quote(user)
    customer_field(user).value = doe.id
    fill_line(user, 1, "Gutter guard", "1", "100")
    user.find(kind=ui.button, content="Mark Quoted").click()
    await user.should_see("Mark this new quote quoted?")
    user.find(marker="confirm-quoted").click()

    await user.should_see(marker="view-customer")
    assert text(user.find(marker="view-customer")) == "Customer: Jane Doe"
    assert text(user.find(marker="view-customer-details")) == (
        "12 Oak St · 555-0134 · jane@example.com"
    )


async def test_the_list_shows_the_customer_in_place_of_the_first_line(user, conn):
    doe = jane(conn)
    with_customer = save_new_quote(
        conn,
        make_quote(customer=doe, line_items=[LineItem("Mow lawn", Decimal(1), 4500)]),
    )
    without = save_new_quote(
        conn, make_quote(line_items=[LineItem("Clean gutters", Decimal(1), 9000)])
    )
    await reload(user)

    assert row_texts(user, with_customer.number)[1] == "Jane Doe"
    assert row_texts(user, without.number)[1] == "Clean gutters"


async def test_search_shows_the_first_line_when_the_row_shows_the_customer(
    user, conn
):
    saved = save_new_quote(
        conn,
        make_quote(
            customer=jane(conn), line_items=[LineItem("Mow lawn", Decimal(1), 4500)]
        ),
    )
    await reload(user)
    await search_for(user, "mow")

    await user.should_see(marker=f"match-{saved.number}")
    [match] = [p for p in row_html(user, saved.number) if p.startswith("Line Item")]
    assert match.startswith("Line Item 1: <mark")


async def test_search_finds_a_quote_by_its_customers_details(user, conn):
    saved = save_new_quote(
        conn,
        make_quote(
            customer=jane(conn), line_items=[LineItem("Mow lawn", Decimal(1), 4500)]
        ),
    )
    save_new_quote(
        conn, make_quote(line_items=[LineItem("Clean gutters", Decimal(1), 9000)])
    )
    await reload(user)
    await search_for(user, "0134")

    assert list_order(user) == [saved.number]
    await user.should_see(marker=f"match-{saved.number}")
    [match] = [p for p in row_html(user, saved.number) if p.startswith("Customer")]
    assert match.startswith("Customer: 555-<mark")


async def test_search_highlights_the_customers_name_in_the_row(user, conn):
    saved = save_new_quote(conn, make_quote(customer=jane(conn)))
    await reload(user)
    await search_for(user, "jane")

    assert any(">Jane</mark> Doe" in part for part in row_html(user, saved.number))
    await user.should_not_see(marker=f"match-{saved.number}")


async def test_a_quoted_quote_highlights_its_customers_matches(user, conn):
    quoted = mark_quoted(
        conn,
        make_quote(
            customer=jane(conn), line_items=[LineItem("Mow lawn", Decimal(1), 4500)]
        ),
        date(2026, 10, 19),
        date(2026, 11, 18),
    )
    await reload(user)
    await search_for(user, "oak")
    user.find(marker=f"quote-{quoted.number}").click()

    await user.should_see(marker="view-customer-details")
    [details] = user.find(marker="view-customer-details").elements
    assert ">Oak</mark> St" in details.content
    [name] = user.find(marker="view-customer").elements
    assert name.content == "Customer: Jane Doe"


async def test_a_draft_tints_its_customer_when_it_matches(user, conn):
    doe = jane(conn)
    saved = save_new_quote(conn, make_quote(customer=doe))
    await reload(user)
    user.find(marker=f"quote-{saved.number}").click()
    await user.should_see(f"{saved.number} (Draft)")
    assert not tinted(user, "customer")

    user.find(marker="search").type("jane@")
    await eventually(lambda: tinted(user, "customer"))
    customer_field(user).value = None  # no customer: nothing to match
    await eventually(lambda: not tinted(user, "customer"))
