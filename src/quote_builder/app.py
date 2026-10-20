"""The app's window: a list of quotes on the left, one quote on the right.

A first, bare layout, growing a step at a time.
"""

import sqlite3
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime

from nicegui import ui

from quote_builder.data_folder import data_folder
from quote_builder.dates import (
    default_valid_until,
    extended_until,
    format_date,
    format_numeric_date,
    parse_date,
)
from quote_builder.money import (
    format_discount,
    format_money,
    format_percent,
    parse_discount,
    parse_money,
    parse_percent,
    parse_quantity,
)
from quote_builder.quotes import LineItem, Quote, QuoteSummary, QuoteTotals, Status
from quote_builder.storage import (
    NotExtendable,
    connect,
    expire_overdue,
    extend_quote,
    list_quotes,
    load_quote,
    mark_quoted,
    save_draft,
    save_new_quote,
)
from quote_builder.totals import (
    line_totals,
    quote_totals,
    shown_line_totals,
    shown_quote_totals,
)


def quote_page(
    conn: sqlite3.Connection, today: Callable[[], date] = date.today
) -> Callable[[], None]:
    """The function NiceGUI calls to build the page, using `conn`.

    `today` gives the date, for tests to set.
    """

    def root() -> None:
        current: Quote | None = None  # the quote on the right, if any
        # Whether the form on the right has changes not yet saved.
        has_unsaved_changes: Callable[[], bool] = lambda: False

        # Handlers first: the list below calls open_quote as it's drawn.
        def show(quote: Quote | None) -> None:
            nonlocal current, has_unsaved_changes
            current = quote
            has_unsaved_changes = lambda: False
            body.clear()
            with body:
                if quote is None:
                    landing()
                elif quote.status is Status.DRAFT:
                    has_unsaved_changes = quote_editor(
                        conn, quote, on_saved=show, today=today
                    )
                else:
                    quote_view(quote, on_extend=lambda: extend(quote))
            quote_list.refresh()

        async def may_leave() -> bool:
            """True if there's nothing unsaved, or the user lets it go."""
            if not has_unsaved_changes():
                return True
            name = current.number if current and current.number else "this new quote"
            return await confirm_discard(name)

        async def new_quote() -> None:
            if await may_leave():
                show(Quote())

        async def open_quote(number: str) -> None:
            if current is not None and current.number == number:
                return  # already open
            if not await may_leave():
                return
            expire_overdue(conn, today())
            quote = load_quote(conn, number)
            if quote is None:  # deleted since the list was drawn
                ui.notify(f"No quote {number}", type="warning")
                quote_list.refresh()
                return
            show(quote)

        async def extend(quote: Quote) -> None:
            extended = await ask_extension(conn, quote, today())
            if extended is not None:
                ui.notify(
                    f"{extended.number} valid through "
                    f"{format_numeric_date(extended.valid_until)}"
                )
                show(extended)

        # behavior=desktop: always beside the quote. Otherwise Quasar turns
        # it into a pop-over below 1024 pixels wide (the window is 1000).
        with ui.left_drawer(value=True, fixed=True).props(
            "width=300 bordered behavior=desktop"
        ).mark("side-panel"):
            ui.label("Quote Builder").classes("text-h6")
            search = ui.input(
                "Search", on_change=lambda: quote_list.refresh()
            ).props("clearable").classes("w-full").mark("search")
            ui.button("New Quote", icon="add", on_click=new_quote)

            @ui.refreshable
            def quote_list() -> None:
                # Expire overdue quotes first, so the list shows them so.
                expire_overdue(conn, today())
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


async def confirm_discard(name: str) -> bool:
    """Ask whether to drop unsaved changes to `name`; True to drop them."""
    with ui.dialog() as dialog, ui.card():
        ui.label("Discard unsaved changes?").classes("text-h6")
        ui.label(f"Changes to {name} haven't been saved.")
        with ui.row().classes("w-full justify-end"):
            ui.button("Keep Editing", on_click=lambda: dialog.submit(False)).props(
                "flat"
            )
            ui.button("Discard", on_click=lambda: dialog.submit(True)).props(
                "color=negative"
            )
    # Esc or a click outside closes it with None: keep editing.
    answer = await dialog
    dialog.delete()
    return answer is True


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
    return format_date(moment.astimezone().date())


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
    conn: sqlite3.Connection,
    quote: Quote,
    on_saved: Callable[[Quote], None],
    today: Callable[[], date],
) -> Callable[[], bool]:
    """A form for a draft, new or saved; `on_saved` gets it once saved.

    Returns a function telling whether the form has unsaved changes.
    """
    heading = "New Quote" if quote.number is None else f"{quote.number} ({quote.status})"
    ui.label(heading).classes("text-h6").mark("heading")
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

    def changed_quote() -> Quote | None:
        """The quote as the form has it, or None after showing a problem."""
        try:
            items = [_checked_item(n, line) for n, line in enumerate(lines, 1)]
        except ValueError as problem:
            ui.notify(str(problem), type="negative")
            return None
        return replace(quote, notes=notes.value.strip(), line_items=items)

    def save() -> None:
        changed = changed_quote()
        if changed is None:
            return
        if changed.number is None:
            saved = save_new_quote(conn, changed)
        else:
            save_draft(conn, changed)
            saved = changed
        ui.notify(f"Saved {saved.number}")
        on_saved(saved)

    async def quote_it() -> None:
        changed = changed_quote()
        if changed is None:
            return
        if not changed.line_items:
            ui.notify("Add a line before marking it quoted", type="negative")
            return
        name = changed.number or "this new quote"
        dates = await ask_quoted_dates(name, today())
        if dates is None:
            return
        # Saves the form's changes too, in the same transaction.
        quoted = mark_quoted(conn, changed, *dates)
        ui.notify(f"{quoted.number} marked quoted")
        on_saved(quoted)

    with ui.row():
        ui.button("Save", on_click=save)
        ui.button("Mark Quoted", on_click=quote_it).props("outline")
    for item in quote.line_items:
        add_line(item)
    if not quote.line_items:
        add_line()

    def form_state() -> tuple:
        """Everything typed in the form, to compare with what it opened with."""
        typed_lines = tuple(
            (
                line.description.value,
                line.quantity.value,
                line.price.value,
                line.discount.value,
                line.tax.value,
            )
            for line in lines
        )
        return (typed_lines, notes.value)

    # Saving shows the quote again in a new form, so this is also the
    # state as last saved. Changes undone by hand count as no change.
    opened_with = form_state()
    return lambda: form_state() != opened_with


async def ask_quoted_dates(name: str, today: date) -> tuple[date, date] | None:
    """Ask for the issued and valid-through dates to mark `name` quoted.

    None if the user cancels.
    """
    with ui.dialog() as dialog, ui.card():
        ui.label(f"Mark {name} quoted?").classes("text-h6")
        issued = date_input("Issued", today, "issued-on")
        valid = date_input(
            "Valid through", default_valid_until(today), "valid-until"
        )
        ui.label("It can't be edited after this; changes become revisions.")

        def confirm() -> None:
            try:
                issued_on = parse_date(issued.value)
                valid_until = parse_date(valid.value)
            except ValueError as problem:
                ui.notify(str(problem), type="negative")
                return
            if valid_until < issued_on:
                ui.notify(
                    "Valid through can't be before the issued date", type="negative"
                )
                return
            dialog.submit((issued_on, valid_until))

        with ui.row().classes("w-full justify-end"):
            ui.button("Cancel", on_click=lambda: dialog.submit(None)).props("flat")
            ui.button("Mark Quoted", on_click=confirm).mark("confirm-quoted")
    # Esc or a click outside closes it with None, as Cancel does.
    answer = await dialog
    dialog.delete()
    return answer


async def ask_extension(
    conn: sqlite3.Connection, quote: Quote, today: date
) -> Quote | None:
    """Ask how far to extend `quote`, and extend it.

    Returns the extended quote, or None if the user cancels.
    """
    # 30 first, as the usual choice (a setting can pick the default later).
    choices = {"30": "30 more days", "7": "7 more days", "custom": "Custom date"}
    with ui.dialog() as dialog, ui.card():
        ui.label(f"Extend {quote.number}?").classes("text-h6")
        through = format_numeric_date(quote.valid_until)
        if quote.status is Status.EXPIRED:
            ui.label(f"Expired; was valid through {through}.")
        else:
            ui.label(f"Currently valid through {through}.")
        choice = ui.radio(choices, value="30", on_change=lambda: show_new_date())
        choice.props("inline").mark("extend-choice")
        custom = date_input(
            "New valid through",
            extended_until(quote.valid_until, today, 30),
            "new-valid-until",
            on_change=lambda: show_new_date(),
        )
        custom.bind_visibility_from(choice, "value", value="custom")
        new_date_label = ui.label().mark("new-valid-through")

        def new_date() -> date:
            """The date chosen; ValueError if a custom one doesn't read."""
            if choice.value == "custom":
                return parse_date(custom.value)
            return extended_until(quote.valid_until, today, int(choice.value))

        def show_new_date() -> None:
            try:
                shown = format_numeric_date(new_date())
            except ValueError:
                shown = "—"
            new_date_label.text = f"New valid through: {shown}"

        def confirm() -> None:
            try:
                dialog.submit(extend_quote(conn, quote, new_date(), today))
            except ValueError as problem:
                ui.notify(str(problem), type="negative")
            except NotExtendable:
                ui.notify(f"{quote.number} changed meanwhile; open it again")
                dialog.submit(None)

        show_new_date()
        with ui.row().classes("w-full justify-end"):
            ui.button("Cancel", on_click=lambda: dialog.submit(None)).props("flat")
            ui.button("Extend", on_click=confirm).mark("confirm-extend")
    # Esc or a click outside closes it with None, as Cancel does.
    answer = await dialog
    dialog.delete()
    return answer


def date_input(
    label: str,
    value: date,
    marker: str,
    on_change: Callable[[], None] | None = None,
) -> ui.input:
    """A date as text (`11/18/2026`), with a calendar to pick it from."""
    field = ui.input(label, value=format_numeric_date(value), on_change=on_change)
    field.mark(marker)
    with field:
        # no-parent-event: only the icon opens the calendar, so typing in
        # the field doesn't. The calendar fills in MM/DD/YYYY, as
        # parse_date reads.
        with ui.menu().props("no-parent-event") as menu:
            ui.date(mask="MM/DD/YYYY", on_change=menu.close).bind_value(field)
    with field.add_slot("append"):
        ui.icon("edit_calendar").on("click", menu.open).classes("cursor-pointer")
    return field


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


def quote_view(quote: Quote, on_extend: Callable[[], None]) -> None:
    """A quote that's no longer a draft, read-only."""
    ui.label(f"{quote.number} ({quote.status})").classes("text-h6").mark("heading")
    if quote.issued_on and quote.valid_until:
        ui.label(
            f"Issued {format_numeric_date(quote.issued_on)} · "
            f"valid through {format_numeric_date(quote.valid_until)}"
        ).mark("dates")
    if quote.extensions:
        count = len(quote.extensions)
        times = "once" if count == 1 else f"{count} times"
        first = format_numeric_date(quote.extensions[0].old_valid_until)
        ui.label(f"Extended {times}; first valid through {first}").classes(
            "text-grey-7"
        ).mark("extensions")
    if quote.status in (Status.QUOTED, Status.EXPIRED):
        ui.button("Extend", icon="event", on_click=on_extend).props("outline")
    # A quoted quote shows its frozen figures, not ones worked out again.
    for item in quote.line_items:
        text = (
            f"{item.description}: {item.quantity} × "
            f"{format_money(item.unit_price_cents)}"
        )
        if discount := format_discount(item.discount_cents, item.discount_percent):
            text += f", less {discount}"
        if item.tax_percent:
            text += f", tax {item.tax_percent}%"
        text += f" = {format_money(shown_line_totals(item).net_cents)}"
        ui.label(text)
    totals_foot(shown_quote_totals(quote))
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
