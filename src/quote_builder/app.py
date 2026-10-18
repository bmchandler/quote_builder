"""The app's window: start a quote, save it, and open a saved one.

A first, bare layout: enough to wire the screen to storage.
"""

import sqlite3
from collections.abc import Callable

from nicegui import ui

from quote_builder.data_folder import data_folder
from quote_builder.money import format_money, parse_money, parse_quantity
from quote_builder.quotes import LineItem, Quote
from quote_builder.storage import connect, load_quote, save_new_quote


def quote_page(conn: sqlite3.Connection) -> Callable[[], None]:
    """The function NiceGUI calls to build the page, using `conn`."""

    def root() -> None:
        ui.label("Quote Builder").classes("text-h5")
        with ui.row().classes("items-end"):
            number = ui.input("Quote number").mark("open-number")
            ui.button("Open", on_click=lambda: open_quote(number.value))
            ui.button("New Quote", on_click=lambda: show(None))
        body = ui.column().classes("w-full")

        def show(quote: Quote | None) -> None:
            body.clear()
            with body:
                if quote is None:
                    quote_editor(conn, on_saved=show)
                else:
                    quote_view(quote)

        def open_quote(text: str) -> None:
            wanted = text.strip().upper()
            quote = load_quote(conn, wanted)
            if quote is None:
                ui.notify(f"No quote {wanted}", type="warning")
                return
            show(quote)

        show(None)

    return root


def quote_editor(
    conn: sqlite3.Connection, on_saved: Callable[[Quote], None]
) -> None:
    """A form for a new quote; `on_saved` gets the quote once saved."""
    ui.label("New Quote").classes("text-h6")
    lines = ui.column()
    # One (row, description, quantity, unit price) per line, in order.
    rows: list[tuple[ui.row, ui.input, ui.input, ui.input]] = []
    added = 0  # lines ever added, so each gets its own test marker

    def add_line() -> None:
        nonlocal added
        added += 1
        with lines, ui.row().classes("items-end") as row:
            # Text inputs, not ui.number, which gives a float.
            description = ui.input("Description").mark(f"description-{added}")
            quantity = ui.input("Qty", value="1").mark(f"quantity-{added}")
            price = ui.input("Unit price").mark(f"price-{added}")
            entry = (row, description, quantity, price)
            ui.button(icon="delete", on_click=lambda: remove(entry)).props(
                "flat"
            ).mark(f"remove-{added}")
        rows.append(entry)

    def remove(entry: tuple[ui.row, ui.input, ui.input, ui.input]) -> None:
        rows.remove(entry)
        lines.remove(entry[0])

    ui.button("Add Line", on_click=add_line)
    notes = ui.textarea("Notes").classes("w-96")

    def save() -> None:
        try:
            items = [
                _line_item(n, description.value, quantity.value, price.value)
                for n, (_, description, quantity, price) in enumerate(rows, 1)
            ]
        except ValueError as problem:
            ui.notify(str(problem), type="negative")
            return
        saved = save_new_quote(
            conn, Quote(notes=notes.value.strip(), line_items=items)
        )
        ui.notify(f"Saved {saved.number}")
        on_saved(saved)

    ui.button("Save", on_click=save)
    add_line()


def quote_view(quote: Quote) -> None:
    """A saved quote, read-only (saving changes isn't built yet)."""
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
