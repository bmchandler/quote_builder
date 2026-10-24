"""The app's window: a list of quotes on the left, one quote on the right.

A first, bare layout, growing a step at a time.
"""

import html
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import date, datetime
from typing import NamedTuple

from nicegui import ui

from quote_builder.business import Business
from quote_builder.data_folder import data_folder
from quote_builder.dates import (
    default_valid_until,
    extended_until,
    format_date,
    format_numeric_date,
    parse_date,
    parse_days,
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
from quote_builder.quotes import (
    REVISABLE,
    LineItem,
    Quote,
    QuoteSummary,
    QuoteTotals,
    Status,
    revision_draft,
    version_name,
)
from quote_builder.storage import (
    NameNeeded,
    NotExtendable,
    add_business,
    connect,
    current_business,
    expire_overdue,
    extend_quote,
    list_businesses,
    list_quotes,
    list_versions,
    load_quote,
    mark_quoted,
    pick_business,
    save_business,
    save_draft,
    save_new_quote,
    save_revision,
    search_texts,
)
from quote_builder.search import HiddenMatch, hidden_match, highlight, matches
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
        editor: Editor | None = None  # the form on the right, if any
        # The business whose settings are on the right, while in Settings.
        settings_for: Business | None = None

        def search_term() -> str:
            return (search.value or "").strip()

        # Handlers first: the list below calls open_quote as it's drawn.
        def show(quote: Quote | None, new_revision: bool = False) -> None:
            """Show `quote` on the right; `new_revision` if it's a
            revision draft not saved yet."""
            nonlocal current, editor
            current = quote
            editor = None
            versions = []
            if quote is not None and quote.number is not None:
                versions = list_versions(conn, quote.number)
            # The link shows once there's more than one version, counting
            # a new revision that isn't saved yet.
            on_history = None
            if len(versions) + new_revision > 1:
                on_history = lambda: version_history(quote)
            body.clear()
            with body:
                if quote is None:
                    landing()
                elif quote.status is Status.DRAFT:
                    editor = quote_editor(
                        conn,
                        quote,
                        on_saved=show,
                        today=today,
                        new_revision=new_revision,
                        on_history=on_history,
                        term=search_term(),
                    )
                else:
                    # A draft is always the newest, so only a view can
                    # be an older version.
                    newest = versions[0]
                    quote_view(
                        quote,
                        on_extend=lambda: extend(quote),
                        on_revise=revise_action(quote, versions),
                        on_history=on_history,
                        newer=newest if newest.revision != quote.revision else None,
                        on_newest=lambda: open_quote(quote.number),
                        term=search_term(),
                    )
            quote_list.refresh()

        def show_business(business: Business) -> None:
            """Show a business's settings on the right, in Settings; a new
            one's if its id is None."""
            nonlocal current, editor, settings_for
            current = None
            settings_for = business
            body.clear()
            with body:
                editor = business_settings(conn, business, on_saved=show_business)
            business_list.refresh()  # its name or kind may have changed

        async def open_settings() -> None:
            """Settings takes over the side panel, opening on the business
            whose quotes were shown."""
            if await may_leave():
                quotes_panel.set_visibility(False)
                settings_panel.set_visibility(True)
                show_business(current_business(conn))

        async def open_business(business: Business) -> None:
            if settings_for is not None and business.id == settings_for.id:
                return  # already open
            if await may_leave():
                show_business(business)

        async def new_business() -> None:
            if await may_leave():
                show_business(Business())

        async def back_to_quotes() -> None:
            nonlocal settings_for
            if await may_leave():
                settings_for = None
                settings_panel.set_visibility(False)
                quotes_panel.set_visibility(True)
                title.refresh()  # names may have changed, or a second added
                show(None)

        async def switch_to(business: Business) -> None:
            """Show another business's quotes, from the dropdown."""
            if business.id == current_business(conn).id:
                return
            if await may_leave():
                pick_business(conn, business.id)
                title.refresh()
                show(None)

        def search_changed() -> None:
            """Matches on the open quote follow the search, as the list's do."""
            if editor is not None:
                # Not drawn again: that would drop the form's edits.
                editor.search_changed(search_term())
                quote_list.refresh()
            elif current is not None:
                show(current)  # refreshes the list too
            else:
                quote_list.refresh()

        def revise_action(
            quote: Quote, versions: list[QuoteSummary]
        ) -> Callable[[], None] | None:
            """The Revise button's handler for `quote`, if it has one.

            Only the newest version can be revised (an older one's banner
            leads to the newest).
            """
            newest = versions[0]
            if newest.revision == quote.revision and quote.status in REVISABLE:
                return lambda: show(
                    revision_draft(quote, newest.revision + 1), new_revision=True
                )
            return None

        async def may_leave() -> bool:
            """True if there's nothing unsaved, or the user lets it go."""
            if editor is None or not editor.has_unsaved_changes():
                return True
            return await confirm_discard(editor.name)

        async def new_quote() -> None:
            if await may_leave():
                show(Quote(business_id=current_business(conn).id))

        async def open_quote(number: str, revision: int | None = None) -> None:
            """Open a version of a quote: its newest, if `revision` is None."""
            expire_overdue(conn, today())
            quote = load_quote(conn, number, revision)
            if quote is None:  # deleted since the list was drawn
                ui.notify(f"No quote {number}", type="warning")
                quote_list.refresh()
                return
            if current is not None and (current.number, current.revision) == (
                quote.number,
                quote.revision,
            ):
                return  # already open
            if not await may_leave():
                return
            show(quote)

        async def extend(quote: Quote) -> None:
            extend_days = current_business(conn).extend_days
            extended = await ask_extension(conn, quote, today(), extend_days)
            if extended is not None:
                ui.notify(
                    f"{name_of(extended)} valid through "
                    f"{format_numeric_date(extended.valid_until)}"
                )
                show(extended)

        async def version_history(quote: Quote) -> None:
            versions = list_versions(conn, quote.number)
            revision = await ask_version(quote.number, versions, quote.revision)
            if revision is not None:
                await open_quote(quote.number, revision)

        # behavior=desktop: always beside the quote. Otherwise Quasar turns
        # it into a pop-over below 1024 pixels wide (the window is 1000).
        # 350 wide: a row's "Q-WMW-M8KW-R1 · Accepted" fits on one line.
        with ui.left_drawer(value=True, fixed=True).props(
            "width=350 bordered behavior=desktop"
        ).mark("side-panel"):
            # Two views, one shown at a time: the quotes, and Settings.
            # Hidden, not cleared, so the search is still there on return.
            quotes_panel = ui.column().classes("w-full h-full no-wrap")
            settings_panel = ui.column().classes("w-full h-full no-wrap")
            settings_panel.set_visibility(False)

        with quotes_panel:

            @ui.refreshable
            def title() -> None:
                business = current_business(conn)
                businesses = list_businesses(conn)
                if len(businesses) > 1:
                    business_menu(business, businesses, on_pick=switch_to)
                    return
                # Its name once it has one; a pilot's in italics.
                label = ui.label(business.name or "Quote Builder")
                label.classes("text-h6").mark("title")
                if business.name and business.pilot:
                    label.classes("italic")

            title()
            search = ui.input("Search", on_change=search_changed).props(
                "clearable"
            ).classes("w-full").mark("search")
            ui.button("New Quote", icon="add", on_click=new_quote)

            @ui.refreshable
            def quote_list() -> None:
                # Expire overdue quotes first, so the list shows them so.
                expire_overdue(conn, today())
                term = (search.value or "").strip()
                summaries = list_quotes(conn, current_business(conn).id, term)
                if not summaries:
                    ui.label("No quotes found" if term else "No quotes yet")
                    return
                # Where each quote matched, for rows that don't show it.
                texts = {}
                if term:
                    texts = search_texts(conn, [s.number for s in summaries])
                with ui.list().props("separator").classes("w-full"):
                    for summary in summaries:
                        hidden = hidden_match(
                            summary, texts.get(summary.number, []), term
                        )
                        # A click opens the version the search found: the
                        # newest, if the row shows the match.
                        revision = hidden.revision if hidden else None
                        quote_list_item(
                            summary,
                            selected=current is not None
                            and summary.number == current.number,
                            # Defaults, so each row keeps its own values
                            # (a plain lambda would see the loop's last).
                            on_click=lambda n=summary.number, r=revision: (
                                open_quote(n, r)
                            ),
                            term=term,
                            hidden=hidden,
                        )

            # The list scrolls on its own, so Settings stays at the bottom.
            with ui.column().classes("w-full grow min-h-0 overflow-y-auto no-wrap"):
                quote_list()
            ui.separator()
            ui.button("Settings", icon="settings", on_click=open_settings).props(
                "flat no-caps"
            ).mark("settings")

        with settings_panel:
            ui.label("Settings").classes("text-h6")

            @ui.refreshable
            def business_list() -> None:
                with ui.list().props("separator").classes("w-full"):
                    for business in list_businesses(conn):
                        item = ui.item(
                            on_click=lambda b=business: open_business(b)
                        ).props("clickable")
                        item.mark(f"business-{business.id}")
                        if settings_for is not None and business.id == settings_for.id:
                            item.props("active")
                        with item, ui.item_section():
                            label = ui.item_label(business_name(business))
                            if business.pilot:
                                label.classes("italic")
                            kind = "Pilot" if business.pilot else "Business"
                            ui.item_label(kind).props("caption")

            # As the quote list does, the list scrolls on its own.
            with ui.column().classes("w-full grow min-h-0 overflow-y-auto no-wrap"):
                business_list()
                ui.button(
                    "Add business or pilot…", icon="add", on_click=new_business
                ).props("flat no-caps").mark("add-business")
            ui.separator()
            # Where Settings was, so one spot opens and closes it.
            ui.button(
                "Back to Quotes", icon="arrow_back", on_click=back_to_quotes
            ).props("flat no-caps").mark("back-to-quotes")

        body = ui.column().classes("w-full")

        show(None)

    return root


def name_of(quote: Quote) -> str:
    """`Q-7KQ-M9XD-R1`, or "this new quote" before it has a number."""
    if quote.number is None:
        return "this new quote"
    return version_name(quote.number, quote.revision)


def quote_heading(text: str, on_history: Callable[[], None] | None) -> None:
    """The quote's heading, with a Version history link at the right."""
    with ui.row().classes("w-full items-center justify-between no-wrap"):
        ui.label(text).classes("text-h6").mark("heading")
        if on_history is not None:
            ui.button("Version history", icon="history", on_click=on_history).props(
                "flat dense no-caps"
            ).mark("version-history")


async def ask_version(
    number: str, versions: list[QuoteSummary], open_revision: int
) -> int | None:
    """Ask which version of `number` to open; its revision, or None."""
    with ui.dialog() as dialog, ui.card().classes("min-w-[28rem]"):
        ui.label(f"Versions of {number}").classes("text-h6")
        with ui.list().props("separator").classes("w-full"):
            for version in versions:
                item = ui.item(
                    on_click=lambda revision=version.revision: dialog.submit(revision)
                )
                item.props("clickable").mark(f"version-{version.revision}")
                if version.revision == open_revision:
                    item.props("active")
                with item:
                    with ui.item_section():
                        rev = version.revision
                        name = f"R{rev}" if rev else "Original"
                        ui.item_label(f"{name} · {version.status}")
                        if version.issued_on and version.valid_until:
                            detail = (
                                f"Issued {format_numeric_date(version.issued_on)}"
                                " · valid through "
                                f"{format_numeric_date(version.valid_until)}"
                            )
                        else:
                            detail = f"Saved {short_date(version.updated_at)}"
                        ui.item_label(detail).props("caption")
                    with ui.item_section().props("side"):
                        ui.item_label(format_money(version.total_cents))
        with ui.row().classes("w-full justify-end"):
            ui.button("Close", on_click=lambda: dialog.submit(None)).props("flat")
    answer = await dialog
    dialog.delete()
    return answer


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


class Editor(NamedTuple):
    """What the page needs from a form on the right, once drawn."""

    name: str  # what it edits, for "Changes to … haven't been saved."
    has_unsaved_changes: Callable[[], bool]
    search_changed: Callable[[str], None]  # tints fields matching the term


def business_name(business: Business) -> str:
    """The business's name, or what stands in for it: only a lone first
    business can go without one."""
    if business.name:
        return business.name
    return "Unnamed pilot" if business.pilot else "Unnamed business"


def business_menu(
    current: Business,
    businesses: list[Business],
    on_pick: Callable[[Business], Awaitable[None]],
) -> None:
    """The current business's name at the top left, with a menu of all of
    them (businesses, then pilots, as listed) to pick another from."""
    button = ui.dropdown_button(current.name, auto_close=True)
    button.props("flat no-caps dense").classes("text-h6 self-start").mark("title")
    if current.pilot:
        button.classes("italic")
    with button, ui.list():
        for n, business in enumerate(businesses):
            if n and business.pilot and not businesses[n - 1].pilot:
                ui.separator()  # between the businesses and the pilots
            item = ui.item(on_click=lambda b=business: on_pick(b)).props("clickable")
            item.mark(f"pick-{business.id}")
            if business.id == current.id:
                item.props("active")
            with item, ui.item_section():
                label = ui.item_label(business.name)
                if business.pilot:
                    label.classes("italic")


def landing() -> None:
    """The right side before a quote is opened."""
    ui.label("Pick a quote on the left, or start a new one.").classes(
        "text-grey-7"
    )


def business_settings(
    conn: sqlite3.Connection,
    business: Business,
    on_saved: Callable[[Business], None],
) -> Editor:
    """A form for a business's settings, or a new business's if its id is
    None; `on_saved` gets it once saved."""
    heading = "New business or pilot" if business.id is None else business_name(business)
    label = ui.label(heading).classes("text-h6").mark("heading")
    if business.pilot:
        label.classes("italic")
    kind = (
        ui.radio(
            {"business": "Business", "pilot": "Pilot"},
            value="pilot" if business.pilot else "business",
            on_change=lambda: show_kind(),
        )
        .props("inline")
        .mark("business-kind")
    )
    # stack-label: the label stays above the field, so the example in
    # the placeholder shows while it's blank. Quasar draws it as dark
    # as typed text, which reads as a name already given: greyed here.
    name = (
        ui.input("Name", value=business.name)
        .props('stack-label input-class="placeholder:text-gray-400"')
        .classes("w-96")
        .mark("business-name")
    )

    def show_kind() -> None:
        """The name's example and note follow the kind picked."""
        if kind.value == "pilot":
            name.props["placeholder"] = "Pressure washing"
            name.props["hint"] = (
                "An activity name works well. Pilots show in italics in the list."
            )
        else:
            name.props["placeholder"] = "John Doe's Lawn Service"
            name.props.pop("hint", None)  # props is observed: no update() needed

    show_kind()
    valid_days = (
        ui.input("Quotes valid for (days)", value=str(business.valid_days))
        .props('hint="Mark Quoted starts valid-through this many days on"')
        .classes("w-96")
        .mark("business-valid-days")
    )
    extend_days = (
        ui.input("Extend by (days)", value=str(business.extend_days or ""))
        .props('hint="What Extend offers first; blank for 30"')
        .classes("w-96")
        .mark("business-extend-days")
    )
    fields = [kind, name, valid_days, extend_days]

    def save() -> None:
        # A cleared input's value is None, not "".
        try:
            days = parse_days(valid_days.value or "")
        except ValueError as problem:
            ui.notify(f"Quotes valid for: {problem}", type="negative")
            return
        extend = None  # blank is unset: Extend keeps its own first choice
        if (extend_days.value or "").strip():
            try:
                extend = parse_days(extend_days.value)
            except ValueError as problem:
                ui.notify(f"Extend by: {problem}", type="negative")
                return
        changed = replace(
            business,
            name=(name.value or "").strip(),
            pilot=kind.value == "pilot",
            valid_days=days,
            extend_days=extend,
        )
        try:
            if changed.id is None:
                changed = add_business(conn, changed)
            else:
                save_business(conn, changed)
        except NameNeeded:
            ui.notify(
                "Name: a name is needed once there's more than one business"
                " or pilot",
                type="negative",
            )
            return
        ui.notify("Settings saved")
        on_saved(changed)

    ui.button("Save", on_click=save).classes("mt-4")

    def form_state() -> tuple:
        return tuple(field.value or "" for field in fields)  # None: cleared

    # Saving shows the settings again, so this is also the saved state.
    opened_with = form_state()
    return Editor(
        "the settings", lambda: form_state() != opened_with, lambda term: None
    )


def quote_list_item(
    summary: QuoteSummary,
    selected: bool,
    on_click: Callable[[], None],
    term: str = "",
    hidden: HiddenMatch | None = None,
) -> None:
    """One quote in the side list: number, status, first line, date, total.

    While searching for `term`, matches are highlighted, and `hidden`
    (where it matched and an excerpt, from search.hidden_match) adds a
    line for a match the row doesn't otherwise show.
    """
    item = ui.item(on_click=on_click)
    item.props("clickable").mark(f"quote-{summary.number}")
    if selected:
        item.props("active")
    name = version_name(summary.number, summary.revision)
    first_line = summary.first_line or "No lines"
    with item:
        with ui.item_section():
            if not term:
                ui.item_label(f"{name} · {summary.status}")
                ui.item_label(first_line).props("caption lines=1")
            else:
                # highlight escapes the text; ui.html's sanitizer
                # (DOMPurify) keeps the <mark> tags.
                with ui.item_label():
                    ui.html(
                        f"{highlight(name, term)} · {summary.status}", tag="span"
                    )
                with ui.item_label().props("caption lines=1"):
                    ui.html(highlight(first_line, term), tag="span")
                if hidden is not None:
                    place, text, _revision = hidden
                    with ui.item_label().props("caption lines=2").mark(
                        f"match-{summary.number}"
                    ):
                        ui.html(
                            f"{html.escape(place)}: {highlight(text, term)}",
                            tag="span",
                        ).classes("italic")
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


# A field holding the search term. An input can't highlight part of its
# text, so the whole field is tinted, in the list's amber.
MATCHING_FIELD = "bg-amber-100"


def quote_editor(
    conn: sqlite3.Connection,
    quote: Quote,
    on_saved: Callable[[Quote], None],
    today: Callable[[], date],
    new_revision: bool = False,
    on_history: Callable[[], None] | None = None,
    term: str = "",
) -> Editor:
    """A form for a draft, new or saved; `on_saved` gets it once saved.

    `new_revision` if it's a revision draft not saved yet. While
    searching for `term`, description and notes fields holding it are
    tinted.
    """
    if quote.number is None:
        heading = "New Quote"
    elif new_revision:
        heading = f"{name_of(quote)} (New revision)"
    else:
        heading = f"{name_of(quote)} ({quote.status})"
    quote_heading(heading, on_history)
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
        show_matches()  # a description may have changed

    def show_matches() -> None:
        for field in [line.description for line in lines] + [notes]:
            if matches(field.value or "", term):
                field.classes(add=MATCHING_FIELD)
            else:
                field.classes(remove=MATCHING_FIELD)

    def search_changed(new_term: str) -> None:
        nonlocal term
        term = new_term
        show_matches()

    foot()
    notes = (
        ui.textarea("Notes", value=quote.notes, on_change=show_matches)
        .classes("w-96")
        .mark("notes")
    )

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
        elif new_revision:
            save_revision(conn, changed)
            saved = changed
        else:
            save_draft(conn, changed)
            saved = changed
        ui.notify(f"Saved {name_of(saved)}")
        on_saved(saved)

    async def quote_it() -> None:
        changed = changed_quote()
        if changed is None:
            return
        if not changed.line_items:
            ui.notify("Add a line before marking it quoted", type="negative")
            return
        valid_days = current_business(conn).valid_days
        dates = await ask_quoted_dates(name_of(changed), today(), valid_days)
        if dates is None:
            return
        # Saves the form's changes too, in the same transaction, and
        # supersedes the version before, if any.
        quoted = mark_quoted(conn, changed, *dates, new_revision=new_revision)
        ui.notify(f"{name_of(quoted)} marked quoted")
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
    return Editor(name_of(quote), lambda: form_state() != opened_with, search_changed)


async def ask_quoted_dates(
    name: str, today: date, valid_days: int
) -> tuple[date, date] | None:
    """Ask for the issued and valid-through dates to mark `name` quoted;
    valid through starts `valid_days` on.

    None if the user cancels.
    """
    with ui.dialog() as dialog, ui.card():
        ui.label(f"Mark {name} quoted?").classes("text-h6")
        issued = date_input("Issued", today, "issued-on")
        valid = date_input(
            "Valid through", default_valid_until(today, valid_days), "valid-until"
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
    conn: sqlite3.Connection, quote: Quote, today: date, extend_days: int | None
) -> Quote | None:
    """Ask how far to extend `quote`, and extend it. `extend_days` (the
    business's setting) picks the first choice: 30 or 7 picks that one,
    any other number a custom date that many days on; None picks 30.

    Returns the extended quote, or None if the user cancels.
    """
    choices = {"30": "30 more days", "7": "7 more days", "custom": "Custom date"}
    days = extend_days or 30  # 30 unset, as the usual choice
    first = str(days) if str(days) in choices else "custom"
    with ui.dialog() as dialog, ui.card():
        ui.label(f"Extend {name_of(quote)}?").classes("text-h6")
        through = format_numeric_date(quote.valid_until)
        if quote.status is Status.EXPIRED:
            ui.label(f"Expired; was valid through {through}.")
        else:
            ui.label(f"Currently valid through {through}.")
        choice = ui.radio(choices, value=first, on_change=lambda: show_new_date())
        choice.props("inline").mark("extend-choice")
        custom = date_input(
            "New valid through",
            extended_until(quote.valid_until, today, days),
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
                ui.notify(f"{name_of(quote)} changed meanwhile; open it again")
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


def quote_view(
    quote: Quote,
    on_extend: Callable[[], None],
    on_revise: Callable[[], None] | None = None,
    on_history: Callable[[], None] | None = None,
    newer: QuoteSummary | None = None,
    on_newest: Callable[[], None] | None = None,
    term: str = "",
) -> None:
    """A quote that's no longer a draft, read-only.

    `on_revise` is the Revise button's handler, if it has one.
    `newer` is the newest version, if `quote` is an older one;
    `on_newest` opens it. While searching for `term`, its matches in
    the lines and notes are highlighted.
    """
    quote_heading(f"{name_of(quote)} ({quote.status})", on_history)
    if newer is not None:
        older_version_banner(newer, on_newest)
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
    with ui.row():
        if quote.status in (Status.QUOTED, Status.EXPIRED):
            ui.button("Extend", icon="event", on_click=on_extend).props("outline")
        if on_revise is not None:
            ui.button("Revise", icon="edit_note", on_click=on_revise).props(
                "outline"
            ).mark("revise")
    # A quoted quote shows its frozen figures, not ones worked out again.
    for n, item in enumerate(quote.line_items, start=1):
        rest = f": {item.quantity} × {format_money(item.unit_price_cents)}"
        if discount := format_discount(item.discount_cents, item.discount_percent):
            rest += f", less {discount}"
        if item.tax_percent:
            rest += f", tax {item.tax_percent}%"
        rest += f" = {format_money(shown_line_totals(item).net_cents)}"
        searched_text(item.description, term, after=rest).mark(f"view-line-{n}")
    totals_foot(shown_quote_totals(quote))
    if quote.notes:
        searched_text(quote.notes, term).mark("view-notes")


def searched_text(text: str, term: str, after: str = "") -> ui.element:
    """`text`, then `after`; while searching for `term`, its matches in
    `text` are highlighted, as in the list."""
    if not term:
        return ui.label(text + after)
    # highlight escapes the text; ui.html's sanitizer keeps the <mark>s.
    return ui.html(highlight(text, term) + html.escape(after), tag="div")


def older_version_banner(newest: QuoteSummary, on_open: Callable[[], None]) -> None:
    """Says the quote shown is an older version, with a button to the
    newest, so it isn't taken for the current one in a hurry."""
    name = f"R{newest.revision}"  # never the original: it's the oldest
    # inline-actions: the button beside the text, not on a line below.
    with ui.element("q-banner").props("dense rounded inline-actions").classes(
        "w-full bg-amber-2"
    ).mark("older-version") as banner:
        with banner.add_slot("avatar"):
            ui.icon("history", size="sm", color="amber-10")
        ui.label(f"This is an older version. {name} ({newest.status}) is the newest.")
        with banner.add_slot("action"):
            # "Go to Draft R2" says it's unfinished, as the text does.
            draft = "Draft " if newest.status is Status.DRAFT else ""
            ui.button(f"Go to {draft}{name}", on_click=on_open).props(
                "flat no-caps"
            ).mark("go-to-newest")


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
