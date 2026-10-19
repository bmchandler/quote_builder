"""The app's window: a list of quotes on the left, one quote on the right.

A first, bare layout: enough to wire the screen to storage.
"""

import sqlite3
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from nicegui import ui

from quote_builder.data_folder import data_folder
from quote_builder.money import format_money, parse_money, parse_quantity
from quote_builder.quotes import LineItem, Quote, QuoteSummary, Status
from quote_builder.storage import (
    connect,
    list_quotes,
    load_quote,
    save_draft,
    save_new_quote,
)

# One line's row and its description, quantity, and unit price inputs.
LineRow = tuple[ui.row, ui.input, ui.input, ui.input]


def quote_page(conn: sqlite3.Connection) -> Callable[[], None]:
    """The function NiceGUI calls to build the page, using `conn`."""

    def root() -> None:
        current: Quote | None = None  # the quote on the right, if any

        # Handlers first: the list below calls open_quote as it's drawn.
        def show(quote: Quote | None) -> None:
            nonlocal current
            current = quote
            body.clear()
            with body:
                if quote is None:
                    landing()
                elif quote.status is Status.DRAFT:
                    quote_editor(conn, quote, on_saved=show)
                else:
                    quote_view(quote)
            quote_list.refresh()

        def open_quote(number: str) -> None:
            quote = load_quote(conn, number)
            if quote is None:  # deleted since the list was drawn
                ui.notify(f"No quote {number}", type="warning")
                quote_list.refresh()
                return
            show(quote)

        # behavior=desktop: always beside the quote. Otherwise Quasar turns
        # it into a pop-over below 1024 pixels wide (the window is 1000).
        with ui.left_drawer(value=True, fixed=True).props(
            "width=300 bordered behavior=desktop"
        ).mark("side-panel"):
            ui.label("Quote Builder").classes("text-h6")
            search = ui.input(
                "Search", on_change=lambda: quote_list.refresh()
            ).props("clearable").classes("w-full").mark("search")
            ui.button("New Quote", icon="add", on_click=lambda: show(Quote()))

            @ui.refreshable
            def quote_list() -> None:
                summaries = list_quotes(conn, search.value or "")
                if not summaries:
                    ui.label("No quotes found" if search.value else "No quotes yet")
                    return
                with ui.list().props("separator").classes("w-full"):
                    for summary in summaries:
                        quote_list_item(
                            summary,
                            selected=current is not None
                            and summary.number == current.number,
                            on_click=open_quote,
                        )

            quote_list()

        body = ui.column().classes("w-full")

        show(None)

    return root


def landing() -> None:
    """The right side before a quote is opened."""
    ui.label("Pick a quote on the left, or start a new one.").classes(
        "text-grey-7"
    )


def quote_list_item(
    summary: QuoteSummary, selected: bool, on_click: Callable[[str], None]
) -> None:
    """One quote in the side list: number, status, first line, date."""
    item = ui.item(on_click=lambda: on_click(summary.number))
    item.props("clickable").mark(f"quote-{summary.number}")
    if selected:
        item.props("active")
    with item:
        with ui.item_section():
            ui.item_label(f"{summary.number} · {summary.status}")
            ui.item_label(summary.first_line or "No lines").props("caption lines=1")
        with ui.item_section().props("side top"):
            ui.item_label(short_date(summary.updated_at)).props("caption")


def short_date(moment: datetime) -> str:
    """`Oct 19, 2026`, in local time."""
    local = moment.astimezone()
    return f"{local:%b} {local.day}, {local.year}"


def quote_editor(
    conn: sqlite3.Connection, quote: Quote, on_saved: Callable[[Quote], None]
) -> None:
    """A form for a draft, new or saved; `on_saved` gets it once saved."""
    if quote.number is None:
        ui.label("New Quote").classes("text-h6")
    else:
        ui.label(f"{quote.number} ({quote.status})").classes("text-h6")
    lines = ui.column()
    rows: list[LineRow] = []  # in order on the quote
    added = 0  # lines ever added, so each gets its own test marker

    def add_line(item: LineItem | None = None) -> None:
        nonlocal added
        added += 1
        with lines, ui.row().classes("items-end") as row:
            # Text inputs, not ui.number, which gives a float.
            description = ui.input(
                "Description", value=item.description if item else ""
            ).mark(f"description-{added}")
            quantity = ui.input(
                "Qty", value=str(item.quantity) if item else "1"
            ).mark(f"quantity-{added}")
            price = ui.input(
                "Unit price",
                value=format_money(item.unit_price_cents) if item else "",
            ).mark(f"price-{added}")
            entry = (row, description, quantity, price)
            ui.button(icon="delete", on_click=lambda: remove(entry)).props(
                "flat"
            ).mark(f"remove-{added}")
        rows.append(entry)

    def remove(entry: LineRow) -> None:
        rows.remove(entry)
        lines.remove(entry[0])

    ui.button("Add Line", on_click=lambda: add_line())
    notes = ui.textarea("Notes", value=quote.notes).classes("w-96")

    def save() -> None:
        try:
            items = [
                _line_item(n, description.value, quantity.value, price.value)
                for n, (_, description, quantity, price) in enumerate(rows, 1)
            ]
        except ValueError as problem:
            ui.notify(str(problem), type="negative")
            return
        changed = replace(quote, notes=notes.value.strip(), line_items=items)
        if changed.number is None:
            saved = save_new_quote(conn, changed)
        else:
            save_draft(conn, changed)
            saved = changed
        ui.notify(f"Saved {saved.number}")
        on_saved(saved)

    ui.button("Save", on_click=save)
    for item in quote.line_items:
        add_line(item)
    if not quote.line_items:
        add_line()


def quote_view(quote: Quote) -> None:
    """A quote that's no longer a draft, read-only."""
    ui.label(f"{quote.number} ({quote.status})").classes("text-h6")
    for item in quote.line_items:
        ui.label(
            f"{item.description}: {item.quantity} × "
            f"{format_money(item.unit_price_cents)}"
        )
    if quote.notes:
        ui.label(quote.notes)


def _line_item(n: int, description: str, quantity: str, price: str) -> LineItem:
    """Line `n` of the form as a LineItem; ValueError names the line."""
    try:
        if not description.strip():
            raise ValueError("A description is needed")
        return LineItem(
            description.strip(), parse_quantity(quantity), parse_money(price)
        )
    except ValueError as problem:
        raise ValueError(f"Line {n}: {problem}") from None


def main() -> None:
    folder = data_folder()
    folder.mkdir(parents=True, exist_ok=True)
    conn = connect(folder / "quotes.db")
    ui.run(
        quote_page(conn),
        title="Quote Builder",
        native=True,
        window_size=(1000, 750),
        reload=False,
    )
