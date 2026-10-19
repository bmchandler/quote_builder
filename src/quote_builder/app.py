"""The app's window: a list of quotes on the left, one quote on the right.

A first, bare layout, growing a step at a time.
"""

import sqlite3
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from nicegui import ui

from quote_builder.data_folder import data_folder
from quote_builder.money import (
    format_discount,
    format_money,
    format_percent,
    parse_discount,
    parse_money,
    parse_percent,
    parse_quantity,
)
from quote_builder.quotes import LineItem, Quote, QuoteSummary, Status
from quote_builder.storage import (
    connect,
    list_quotes,
    load_quote,
    save_draft,
    save_new_quote,
)
from quote_builder.totals import QuoteTotals, line_totals, quote_totals


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
    """One quote in the side list: number, status, first line, date, total."""
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
            ui.item_label(format_money(summary.total_cents)).mark(
                f"list-total-{summary.number}"
            )


def short_date(moment: datetime) -> str:
    """`Oct 19, 2026`, in local time."""
    local = moment.astimezone()
    return f"{local:%b} {local.day}, {local.year}"


class LineInputs:
    """One line of the form: its inputs, and its total after discount."""

    def __init__(
        self,
        marker: int,
        item: LineItem | None,
        on_change: Callable[[], None],
        on_remove: Callable[["LineInputs"], None],
    ) -> None:
        def text_input(label: str, value: str, name: str, width: str) -> ui.input:
            # Text inputs, not ui.number, which gives a float.
            return (
                ui.input(label, value=value, on_change=on_change)
                .classes(width)
                .mark(f"{name}-{marker}")
            )

        with ui.row().classes("items-end no-wrap gap-2 w-full") as self.row:
            self.description = text_input(
                "Description", item.description if item else "", "description", "grow"
            )
            self.quantity = text_input(
                "Qty", str(item.quantity) if item else "1", "quantity", "w-12"
            )
            self.price = text_input(
                "Unit price",
                format_money(item.unit_price_cents) if item else "",
                "price",
                "w-24",
            )
            self.discount = text_input(
                "Discount",
                format_discount(item.discount_cents, item.discount_percent)
                if item
                else "",
                "discount",
                "w-20",
            ).props('placeholder="$ or %"')
            self.tax = text_input(
                "Tax %", format_percent(item.tax_percent) if item else "", "tax", "w-14"
            )
            self.total = (
                ui.label().classes("w-20 text-right pb-2").mark(f"line-total-{marker}")
            )
            ui.button(icon="delete", on_click=lambda: on_remove(self)).props(
                "flat dense"
            ).mark(f"remove-{marker}")

    def item(self) -> LineItem:
        """The line as typed; ValueError if a number doesn't read.

        A blank description is allowed here, so totals show while typing.
        """
        discount_cents, discount_percent = parse_discount(self.discount.value)
        return LineItem(
            description=self.description.value.strip(),
            quantity=parse_quantity(self.quantity.value),
            unit_price_cents=parse_money(self.price.value),
            tax_percent=parse_percent(self.tax.value),
            discount_cents=discount_cents,
            discount_percent=discount_percent,
        )


def quote_editor(
    conn: sqlite3.Connection, quote: Quote, on_saved: Callable[[Quote], None]
) -> None:
    """A form for a draft, new or saved; `on_saved` gets it once saved."""
    if quote.number is None:
        ui.label("New Quote").classes("text-h6")
    else:
        ui.label(f"{quote.number} ({quote.status})").classes("text-h6")
    lines_column = ui.column().classes("w-full")
    lines: list[LineInputs] = []  # in order on the quote
    added = 0  # lines ever added, so each gets its own test marker

    def add_line(item: LineItem | None = None) -> None:
        nonlocal added
        added += 1
        with lines_column:
            lines.append(LineInputs(added, item, update_totals, remove))
        update_totals()

    def remove(line: LineInputs) -> None:
        lines.remove(line)
        lines_column.remove(line.row)
        update_totals()

    ui.button("Add Line", on_click=lambda: add_line())

    @ui.refreshable
    def foot() -> None:
        items = []
        for line in lines:
            if not line.price.value.strip():
                # No price yet: nothing to add up (Save still asks for one).
                line.total.text = ""
                items.append(None)
                continue
            try:
                item = line.item()
                line.total.text = format_money(line_totals(item).net_cents)
                items.append(item)
            except ValueError:
                line.total.text = "—"  # shown until the line reads
        if len(items) == len(lines):
            totals_foot(quote_totals(item for item in items if item is not None))
        else:
            totals_foot(None)

    def update_totals() -> None:
        foot.refresh()

    foot()
    notes = ui.textarea("Notes", value=quote.notes).classes("w-96")

    def save() -> None:
        try:
            items = [_checked_item(n, line) for n, line in enumerate(lines, 1)]
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


def totals_foot(totals: QuoteTotals | None) -> None:
    """The quote's totals, or dashes while a line doesn't read."""

    def amount(cents: int) -> str:
        return "—" if totals is None else format_money(cents)

    rows = [
        ("Items", totals.items_cents if totals else 0, "items"),
        ("Discounts", -totals.discount_cents if totals else 0, "discounts"),
        ("Tax", totals.tax_cents if totals else 0, "tax"),
        ("Total", totals.total_cents if totals else 0, "total"),
    ]
    with ui.grid(columns="auto 7rem").classes("gap-x-4 gap-y-0 self-end pr-12"):
        for label, cents, name in rows:
            bold = " text-weight-bold" if name == "total" else ""
            ui.label(label).classes("text-right" + bold)
            ui.label(amount(cents)).classes("text-right" + bold).mark(f"foot-{name}")


def quote_view(quote: Quote) -> None:
    """A quote that's no longer a draft, read-only."""
    ui.label(f"{quote.number} ({quote.status})").classes("text-h6")
    for item in quote.line_items:
        text = (
            f"{item.description}: {item.quantity} × "
            f"{format_money(item.unit_price_cents)}"
        )
        if discount := format_discount(item.discount_cents, item.discount_percent):
            text += f", less {discount}"
        if item.tax_percent:
            text += f", tax {item.tax_percent}%"
        text += f" = {format_money(line_totals(item).net_cents)}"
        ui.label(text)
    totals_foot(quote_totals(quote.line_items))
    if quote.notes:
        ui.label(quote.notes)


def _checked_item(n: int, line: LineInputs) -> LineItem:
    """Line `n` of the form, ready to save; ValueError names the line."""
    try:
        if not line.description.value.strip():
            raise ValueError("A description is needed")
        item = line.item()
        line_totals(item)  # refuses a discount over the line
        return item
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
