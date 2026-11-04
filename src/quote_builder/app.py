"""The app's window: a list of quotes on the left, one quote on the right.

A first, bare layout, growing a step at a time.
"""

import html
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from typing import NamedTuple

from nicegui import ui

from quote_builder.business import Business, TaxPart, TaxRate, check_tax_rate
from quote_builder.catalog import CatalogItem, check_catalog_item
from quote_builder.customers import (
    Customer,
    check_customer,
    find_customers,
    is_exact_duplicate,
)
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
from quote_builder.phones import (
    format_phone,
    parse_ext,
    parse_phone,
    phone_matches,
)
from quote_builder.quotes import (
    REVISABLE,
    LineItem,
    Quote,
    QuoteSummary,
    QuoteTotals,
    Status,
    extend_tax_note,
    rate_changed_note,
    revision_draft,
    tax_change_note,
    version_name,
)
from quote_builder.storage import (
    NameNeeded,
    NotExtendable,
    RateInUse,
    add_business,
    add_customer,
    connect,
    current_business,
    delete_catalog_item,
    delete_customer,
    delete_tax_rate,
    expire_overdue,
    extend_quote,
    list_businesses,
    list_catalog_items,
    list_customers,
    list_quotes,
    list_tax_rates,
    list_versions,
    load_quote,
    mark_quoted,
    pick_business,
    save_business,
    save_catalog_item,
    save_draft,
    save_new_quote,
    save_revision,
    save_tax_rate,
    search_texts,
    update_customer,
)
from quote_builder.search import (
    HiddenMatch,
    hidden_match,
    highlight,
    highlight_details,
    highlight_phone,
    matches,
    row_text,
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
        editor: Editor | None = None  # the form on the right, if any
        # The business whose settings are on the right, while in Settings.
        settings_for: Business | None = None
        list_open = False  # that business's catalog or customers are instead

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
                        rate_changed=(
                            rate_changed_note(quote, rate_now(conn, quote))
                            if quote.status is Status.QUOTED
                            else None
                        ),
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
            nonlocal current, editor, settings_for, list_open
            current = None
            settings_for = business
            list_open = False
            body.clear()
            with body:
                editor = business_settings(conn, business, on_saved=show_business)
            # A new business gets a catalog and customers once saved, as it
            # does tax rates.
            catalog_button.set_enabled(business.id is not None)
            customers_button.set_enabled(business.id is not None)
            business_list.refresh()  # its name or kind may have changed

        async def open_list(view: Callable[..., None]) -> None:
            """Show `view` (a catalog or customers) of the business picked
            in Settings."""
            nonlocal editor, list_open
            if await may_leave():
                editor = None  # its dialog saves on its own: nothing to ask
                list_open = True
                body.clear()
                with body:
                    view(conn, settings_for)

        async def open_catalog() -> None:
            await open_list(catalog_view)

        async def open_customers() -> None:
            await open_list(customers_view)

        async def open_settings() -> None:
            """Settings takes over the side panel, opening on the business
            whose quotes were shown."""
            if await may_leave():
                quotes_panel.set_visibility(False)
                settings_panel.set_visibility(True)
                show_business(current_business(conn))

        async def open_business(business: Business) -> None:
            if (
                settings_for is not None
                and business.id == settings_for.id
                and not list_open
            ):
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
                business_id = current_business(conn).id
                # Taxed at the business's default rate, if it has one.
                default = next(
                    (r for r in list_tax_rates(conn, business_id) if r.is_default),
                    None,
                )
                show(
                    Quote(
                        business_id=business_id,
                        tax_rate_id=default.id if default else None,
                    )
                )

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
            versions = list_versions(conn, quote.number)
            on_revise = revise_action(quote, versions)
            # A quote being extended isn't a draft, so a draft is newer.
            draft = None
            if versions[0].status is Status.DRAFT:
                draft = load_quote(conn, quote.number, versions[0].revision)
            extended = await ask_extension(
                conn,
                quote,
                today(),
                extend_days,
                can_revise=on_revise is not None,
                draft=draft,
            )
            if extended is REVISE:
                on_revise()
            elif extended is not None:
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
        # 350 wide: a row's "Q-WMW-M8KW-R1 · Expired" fits on one line.
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
            catalog_button = (
                ui.button("Catalog", icon="inventory_2", on_click=open_catalog)
                .props("flat no-caps")
                .mark("catalog")
            )
            customers_button = (
                ui.button("Customers", icon="people", on_click=open_customers)
                .props("flat no-caps")
                .mark("customers")
            )
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


def quote_heading(
    text: str,
    on_history: Callable[[], None] | None,
    actions: Callable[[], None] | None = None,
) -> None:
    """The quote's heading, with `actions` (a quoted quote's Extend/Revise)
    at its right, and the Version history link tucked just below it, so the
    heading's width stays the same whether or not there's a history."""
    # A tight column so the history link sits right under the title, apart
    # from the page's usual spacing to what follows.
    with ui.column().classes("w-full gap-0"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label(text).classes("text-h6 whitespace-nowrap").mark("heading")
            if actions is not None:
                with ui.row().classes("items-center no-wrap gap-2"):
                    actions()
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
    if business.id is not None:  # a new business gets rates once saved
        tax_rates(conn, business.id)

    def form_state() -> tuple:
        return tuple(field.value or "" for field in fields)  # None: cleared

    # Saving shows the settings again, so this is also the saved state.
    opened_with = form_state()
    return Editor(
        "the settings", lambda: form_state() != opened_with, lambda term: None
    )


def tax_rates(conn: sqlite3.Connection, business_id: int) -> None:
    """A business's tax rates, below its settings. The dialog that adds
    or changes one saves it at once, apart from the form's Save."""
    ui.separator().classes("my-4")
    ui.label("Tax rates").classes("text-subtitle1 text-weight-medium")

    async def edit(rate: TaxRate) -> None:
        answer = await ask_tax_rate(rate)
        if answer is DELETE:
            try:
                delete_tax_rate(conn, rate.id)
                ui.notify(f"Deleted {rate.name}")
            except RateInUse as in_use:
                # For now; a flow to move those drafts to another rate
                # is planned (REQUIREMENTS.md).
                drafts = "1 draft" if in_use.drafts == 1 else f"{in_use.drafts} drafts"
                ui.notify(f"{rate.name} is used by {drafts}", type="negative")
        elif answer is not None:
            save_tax_rate(conn, answer)
            ui.notify(f"Saved {answer.name}")
        rate_list.refresh()

    @ui.refreshable
    def rate_list() -> None:
        rates = list_tax_rates(conn, business_id)
        if rates:
            with ui.list().props("separator bordered").classes("w-96 rounded"):
                for rate in rates:
                    text = f"{rate.name} · {rate.percent}%"
                    if rate.is_default:
                        text += " · Default"
                    item = ui.item(text, on_click=lambda r=rate: edit(r))
                    item.props("clickable").mark(f"tax-rate-{rate.id}")
        # The first rate starts as the default: a business has one rate
        # more often than not.
        new = TaxRate(
            business_id, parts=[TaxPart("", Decimal(0))], is_default=not rates
        )
        ui.button(
            "Add tax rate…", icon="add", on_click=lambda: edit(new)
        ).props("flat no-caps").mark("add-tax-rate")

    rate_list()


DELETE = object()  # a dialog's answer when Delete is clicked
REVISE = object()  # the Extend dialog's answer when Revise is clicked
UNTAXED = "untaxed"  # the Tax rate choice for no rate (the others are ids)


async def ask_tax_rate(rate: TaxRate) -> TaxRate | object | None:
    """Ask for a tax rate's name and parts: the rate as changed, DELETE,
    or None if the user cancels. A new one (no id) can't be deleted."""
    with ui.dialog() as dialog, ui.card().classes("min-w-[28rem]"):
        ui.label("Add tax rate" if rate.id is None else "Edit tax rate").classes(
            "text-h6"
        )
        # stack-label and greyed, as the business's Name is.
        name = (
            ui.input("Name", value=rate.name, placeholder="Home county")
            .props('stack-label input-class="placeholder:text-gray-400"')
            .classes("w-full")
            .mark("tax-rate-name")
        )
        parts_column = ui.column().classes("w-full gap-0")
        parts: list[tuple[ui.row, ui.input, ui.input]] = []  # in order
        added = 0  # parts ever added, so each gets its own test marker

        def add_part(part: TaxPart) -> None:
            nonlocal added
            added += 1
            with parts_column, ui.row().classes("w-full items-end no-wrap") as row:
                part_name = (
                    ui.input(
                        "Part",
                        value=part.name,
                        placeholder="State, County, or City, etc.",
                    )
                    .props('stack-label input-class="placeholder:text-gray-400"')
                    .classes("grow")
                    .mark(f"part-name-{added}")
                )
                percent = (
                    ui.input(
                        "Percent",
                        value=format_percent(part.percent),
                        placeholder="4.75",
                        on_change=lambda: show_combined(),
                    )
                    .props('stack-label input-class="placeholder:text-gray-400"')
                    .classes("w-24")
                    .mark(f"part-percent-{added}")
                )
                ui.button(icon="close", on_click=lambda: remove_part(row)).props(
                    "flat round dense"
                ).mark(f"remove-part-{added}")
            parts.append((row, part_name, percent))
            show_combined()

        def remove_part(row: ui.row) -> None:
            parts[:] = [p for p in parts if p[0] is not row]
            parts_column.remove(row)
            show_combined()

        ui.button(
            "Add part", icon="add", on_click=lambda: add_part(TaxPart("", Decimal(0)))
        ).props("flat no-caps dense").mark("add-part")
        combined = ui.label().mark("combined")
        default = ui.checkbox("Default for new quotes", value=rate.is_default)
        default.mark("tax-rate-default")

        def typed_parts() -> list[TaxPart]:
            """The parts as typed; ValueError names one that doesn't read."""
            read = []
            for n, (_, part_name, percent) in enumerate(parts, start=1):
                try:
                    read.append(
                        TaxPart(
                            (part_name.value or "").strip(),
                            parse_percent(percent.value or ""),
                        )
                    )
                except ValueError as problem:
                    raise ValueError(f"Part {n}: {problem}") from None
            return read

        def show_combined() -> None:
            try:
                total = f"{replace(rate, parts=typed_parts()).percent}%"
            except ValueError:
                total = "—"  # shown until every part reads
            combined.text = f"Combined: {total}"

        def changed_rate() -> TaxRate:
            """The rate as typed; ValueError says what's wrong."""
            changed = replace(
                rate,
                name=(name.value or "").strip(),
                parts=typed_parts(),
                is_default=default.value,
            )
            check_tax_rate(changed)
            return changed

        def confirm() -> None:
            try:
                dialog.submit(changed_rate())
            except ValueError as problem:
                ui.notify(str(problem), type="negative")

        for part in rate.parts:
            add_part(part)
        with ui.row().classes("w-full items-center"):
            if rate.id is not None:
                ui.button("Delete", on_click=lambda: dialog.submit(DELETE)).props(
                    "flat color=negative"
                ).mark("delete-tax-rate")
            ui.space()
            ui.button("Cancel", on_click=lambda: dialog.submit(None)).props("flat")
            ui.button("Save", on_click=confirm).mark("save-tax-rate")
    # Esc or a click outside closes it with None, as Cancel does.
    answer = await dialog
    dialog.delete()
    return answer


def catalog_view(conn: sqlite3.Connection, business: Business) -> None:
    """A business's catalog. The dialog that adds or changes an item saves
    it at once, as a tax rate's does."""
    label = ui.label(f"Catalog: {business_name(business)}")
    label.classes("text-h6").mark("heading")
    if business.pilot:
        label.classes("italic")

    async def edit(item: CatalogItem) -> None:
        answer = await ask_catalog_item(item)
        if answer is DELETE:
            delete_catalog_item(conn, item.id)
            ui.notify(f"Deleted {item.description}")
        elif answer is not None:
            save_catalog_item(conn, answer)
            ui.notify(f"Saved {answer.description}")
        item_list.refresh()

    @ui.refreshable
    def item_list() -> None:
        items = list_catalog_items(conn, business.id)
        if items:
            with ui.list().props("separator bordered").classes("w-full rounded"):
                for item in items:
                    parts = (item.description, item.price_text)
                    row = ui.item(
                        " · ".join(part for part in parts if part),
                        on_click=lambda i=item: edit(i),
                    )
                    row.props("clickable").mark(f"catalog-item-{item.id}")
        ui.button(
            "Add catalog item…",
            icon="add",
            on_click=lambda: edit(CatalogItem(business.id)),
        ).props("flat no-caps").mark("add-catalog-item")

    item_list()


def customers_view(conn: sqlite3.Connection, business: Business) -> None:
    """A business's customers. The dialog that adds or changes one saves
    it at once, as a catalog item's does."""
    label = ui.label(f"Customers: {business_name(business)}")
    label.classes("text-h6").mark("heading")
    if business.pilot:
        label.classes("italic")

    async def edit(customer: Customer) -> None:
        answer = await ask_customer(customer, list_customers(conn, business.id))
        if answer is DELETE:
            delete_customer(conn, customer.id)
            ui.notify(f"Deleted {customer.name}")
        elif answer is not None:
            if customer.id is None:
                add_customer(conn, answer)
                ui.notify(f"Added {answer.name}")
            else:
                update_customer(conn, answer)
                ui.notify(f"Saved {answer.name}")
        customer_list.refresh()

    @ui.refreshable
    def customer_list() -> None:
        customers = list_customers(conn, business.id)
        if customers:
            with ui.list().props("separator bordered").classes("w-full rounded"):
                for customer in customers:
                    customer_row(
                        customer,
                        lambda c=customer: edit(c),
                        f"customer-row-{customer.id}",
                    )
        ui.button(
            "Add customer…",
            icon="add",
            on_click=lambda: edit(Customer(business.id)),
        ).props("flat no-caps").mark("add-customer")

    customer_list()


async def ask_catalog_item(item: CatalogItem) -> CatalogItem | object | None:
    """Ask for a catalog item's details: the item as changed, DELETE, or
    None if the user cancels. A new one (no id) can't be deleted."""
    with ui.dialog() as dialog, ui.card().classes("min-w-[28rem]"):
        ui.label("Add catalog item" if item.id is None else "Edit catalog item").classes(
            "text-h6"
        )
        description = (
            ui.input("Description", value=item.description)
            .classes("w-full")
            .mark("catalog-description")
        )
        price = (
            ui.input(
                "Default price",
                value="" if item.price_cents is None else format_money(item.price_cents),
            )
            .classes("w-full")
            .mark("catalog-price")
        )
        # stack-label and greyed, as the business's Name is.
        unit = (
            ui.input("Unit", value=item.unit, placeholder="hour, each, flat, etc.")
            .props('stack-label input-class="placeholder:text-gray-400"')
            .classes("w-full")
            .mark("catalog-unit")
        )
        taxable = ui.checkbox("Taxable", value=item.taxable).mark("catalog-taxable")

        def changed_item() -> CatalogItem:
            """The item as typed; ValueError says what's wrong."""
            typed_price = (price.value or "").strip()
            try:
                cents = parse_money(typed_price) if typed_price else None
            except ValueError as problem:
                raise ValueError(f"Default price: {problem}") from None
            changed = replace(
                item,
                description=(description.value or "").strip(),
                price_cents=cents,
                unit=(unit.value or "").strip(),
                taxable=taxable.value,
            )
            check_catalog_item(changed)
            return changed

        def confirm() -> None:
            try:
                dialog.submit(changed_item())
            except ValueError as problem:
                ui.notify(str(problem), type="negative")

        with ui.row().classes("w-full items-center"):
            if item.id is not None:
                ui.button("Delete", on_click=lambda: dialog.submit(DELETE)).props(
                    "flat color=negative"
                ).mark("delete-catalog-item")
            ui.space()
            ui.button("Cancel", on_click=lambda: dialog.submit(None)).props("flat")
            ui.button("Save", on_click=confirm).mark("save-catalog-item")
    # Esc or a click outside closes it with None, as Cancel does.
    answer = await dialog
    dialog.delete()
    return answer


def quote_list_item(
    summary: QuoteSummary,
    selected: bool,
    on_click: Callable[[], None],
    term: str = "",
    hidden: HiddenMatch | None = None,
) -> None:
    """One quote in the side list: number, status, customer (or without
    one, the first line), date, total.

    While searching for `term`, matches are highlighted, and `hidden`
    (where it matched and an excerpt, from search.hidden_match) adds a
    line for a match the row doesn't otherwise show.
    """
    item = ui.item(on_click=on_click)
    item.props("clickable").mark(f"quote-{summary.number}")
    if selected:
        item.props("active")
    name = version_name(summary.number, summary.revision)
    second_line = row_text(summary) or "No lines"
    with item:
        with ui.item_section():
            if not term:
                ui.item_label(f"{name} · {summary.status}")
                ui.item_label(second_line).props("caption lines=1")
            else:
                # highlight escapes the text; ui.html's sanitizer
                # (DOMPurify) keeps the <mark> tags.
                with ui.item_label():
                    ui.html(
                        f"{highlight(name, term)} · {summary.status}", tag="span"
                    )
                with ui.item_label().props("caption lines=1"):
                    ui.html(highlight(second_line, term), tag="span")
                if hidden is not None:
                    inner = (
                        highlight_phone(hidden.excerpt, term)
                        if hidden.is_phone
                        else highlight(hidden.excerpt, term)
                    )
                    with ui.item_label().props("caption lines=2").mark(
                        f"match-{summary.number}"
                    ):
                        ui.html(
                            f"{html.escape(hidden.place)}: {inner}",
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
        on_add_to_catalog: Callable[["LineInputs"], Awaitable[None]],
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
            ).props('input-class="truncate"')  # ... where it doesn't fit
            with self.description:
                # Only over the text, as the (+) has its own hint: this
                # id is on the <input> inside the field.
                self.full_description = ui.tooltip().props(
                    f'target="#{self.description.html_id}"'
                )
            with self.description.add_slot("append"):
                self.add_to_catalog = (
                    ui.button(
                        icon="add_circle_outline",
                        on_click=lambda: on_add_to_catalog(self),
                    )
                    # tabindex: Tab goes from Description straight to Qty.
                    .props('flat round dense size=sm tabindex="-1"')
                    .tooltip("Add to Catalog")
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
            # Untaxed to start, as a line was with a blank Tax %.
            self.taxed = (
                ui.checkbox(
                    "Tax", value=item.taxed if item else False, on_change=on_change
                )
                .props("dense")
                .classes("pb-2")
                .mark(f"taxed-{marker}")
            )
            self.total = (
                ui.label().classes("w-20 text-right pb-2").mark(f"line-total-{marker}")
            )
            ui.button(icon="delete", on_click=lambda: on_remove(self)).props(
                "flat dense"
            ).mark(f"remove-{marker}")
        self.description.on_value_change(self.show_description)
        self.show_description()

    def show_description(self) -> None:
        """The hover text and the (+) wait for a description: a catalog
        item needs one."""
        text = (self.description.value or "").strip()
        self.full_description.text = text
        self.full_description.set_visibility(bool(text))
        self.add_to_catalog.set_visibility(bool(text))

    def is_blank(self) -> bool:
        """True if nothing's been entered: as a new line starts."""
        return (
            not self.description.value.strip()
            and self.quantity.value.strip() == "1"
            and not self.price.value.strip()
            and not self.discount.value.strip()
            and not self.taxed.value
        )

    def item(self) -> LineItem:
        """The line as typed; ValueError if a number doesn't read.

        A blank description is allowed here, so totals show while typing.
        """
        discount_cents, discount_percent = parse_discount(self.discount.value)
        return LineItem(
            description=self.description.value.strip(),
            quantity=parse_quantity(self.quantity.value),
            unit_price_cents=parse_money(self.price.value),
            taxed=self.taxed.value,
            discount_cents=discount_cents,
            discount_percent=discount_percent,
        )


# How Add from catalog draws a choice: its description, and below it its
# price. A choice's label is both, on two lines, so typing finds an item
# by any of it: NiceGUI filters the choices by label. Vue's {{ }} escapes
# the text.
TWO_LINE_OPTION = r"""
<q-item v-bind="props.itemProps">
  <q-item-section>
    <q-item-label>{{ props.opt.label.split('\n')[0] }}</q-item-label>
    <q-item-label caption>{{ props.opt.label.split('\n')[1] }}</q-item-label>
  </q-item-section>
</q-item>
"""


class CustomerFields:
    """A draft's customer: its own copy of the details, typed in or filled
    in from the business's saved customers, with a way to save what's
    typed as one of them."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        business_id: int,
        customer: Customer | None,
        on_change: Callable[[], None],
    ) -> None:
        self.conn = conn
        self.business_id = business_id
        self.on_change = on_change
        given = customer or Customer(business_id)
        with ui.row().classes("items-center gap-2"):
            ui.label("Customer").classes("text-subtitle1")
            self.find = (
                ui.button("Find customer", icon="search", on_click=self.fill_from_saved)
                .props("flat dense no-caps")
                .mark("find-customer")
            )
        self.show_find()
        with ui.grid(columns=2).classes("w-full gap-x-4 gap-y-0"):
            self.name = self.field(ui.input, "Name", given.name, "name")
            with self.name.add_slot("append"):
                self.add_to_customers = (
                    ui.button(icon="add_circle_outline", on_click=self.add)
                    # tabindex: Tab goes from Name straight to Phone.
                    .props('flat round dense size=sm tabindex="-1"')
                    .tooltip("Add to Customers")
                )
            with ui.row().classes("no-wrap gap-2 w-full"):
                self.phone = self.field(
                    ui.input, "Phone", format_phone(given.phone), "phone"
                ).classes("grow")
                self.phone.on("blur", self.reformat_phone)
                self.ext = self.field(ui.input, "Ext.", given.ext, "ext").classes("w-16")
            self.email = self.field(ui.input, "Email", given.email, "email")
            self.address = self.field(ui.textarea, "Address", given.address, "address")
            self.address.props("autogrow")
        self.fields = [self.name, self.phone, self.ext, self.email, self.address]
        self.show_add()

    def reformat_phone(self) -> None:
        """On leaving the field, snap a valid number to (123) 456-7890;
        leave anything else for Save to flag."""
        try:
            self.phone.value = format_phone(parse_phone(self.phone.value or ""))
        except ValueError:
            pass

    def field(
        self, kind: Callable[..., ui.element], label: str, value: str, marker: str
    ) -> ui.element:
        return kind(label, value=value, on_change=lambda: self.typed()).mark(
            f"quote-customer-{marker}"
        )

    def typed(self) -> None:
        self.show_add()
        self.on_change()

    def show_find(self) -> None:
        """Only once there's a saved customer to find."""
        self.find.set_visibility(bool(list_customers(self.conn, self.business_id)))

    def show_add(self) -> None:
        self.add_to_customers.set_visibility(bool((self.name.value or "").strip()))

    def customer(self) -> Customer | None:
        """The details as typed, or None if they're all blank. A phone
        or extension that doesn't read raises ValueError, as a line's
        amount does."""
        typed = Customer(
            self.business_id,
            name=" ".join((self.name.value or "").split()),
            email=(self.email.value or "").strip(),
            phone=parse_phone(self.phone.value or ""),
            ext=parse_ext(self.ext.value or ""),
            address=(self.address.value or "").strip(),
        )
        return None if typed.is_blank else typed

    def state(self) -> tuple:
        return tuple(field.value for field in self.fields)

    async def fill_from_saved(self) -> None:
        saved = await ask_find_customer(list_customers(self.conn, self.business_id))
        if saved is not None:
            self.name.value = saved.name
            self.phone.value = format_phone(saved.phone)
            self.ext.value = saved.ext
            self.email.value = saved.email
            self.address.value = saved.address

    async def add(self) -> None:
        """Saving one doesn't count as a change to the quote, as with Add
        to Catalog."""
        try:
            prefilled = self.customer()
        except ValueError as problem:
            ui.notify(str(problem), type="negative")
            return
        answer = await ask_customer(
            prefilled, list_customers(self.conn, self.business_id)
        )
        if answer is not None:
            add_customer(self.conn, answer)
            ui.notify(f"Added {answer.name} to Customers")
            self.show_find()


async def ask_find_customer(customers: list[Customer]) -> Customer | None:
    """Search the saved customers: the one clicked, or None if the user
    cancels."""
    with ui.dialog() as dialog, ui.card().classes("min-w-[28rem]"):
        ui.label("Find customer").classes("text-h6")
        search = (
            ui.input("Search", on_change=lambda: results.refresh())
            .props("autofocus")
            .classes("w-full")
            .mark("find-customer-text")
        )

        @ui.refreshable
        def results() -> None:
            found = find_customers(customers, search.value or "")
            if not found:
                ui.label("No customers match").classes("text-grey-7")
                return
            with ui.list().props("separator bordered").classes(
                "w-full rounded max-h-72 overflow-y-auto"
            ):
                for customer in found:
                    customer_row(
                        customer,
                        lambda c=customer: dialog.submit(c),
                        f"found-customer-{customer.id}",
                    )

        results()
        with ui.row().classes("w-full justify-end"):
            ui.button("Cancel", on_click=lambda: dialog.submit(None)).props("flat")
    # Esc or a click outside closes it with None, as Cancel does.
    answer = await dialog
    dialog.delete()
    return answer


def customer_row(
    customer: Customer, on_click: Callable[[], None], marker: str
) -> None:
    """A saved customer in a list: the name, and below it what tells
    customers of the same name apart."""
    row = ui.item(on_click=on_click)
    row.props("clickable").mark(marker)
    with row, ui.item_section():
        ui.item_label(customer.name)
        if customer.details:
            ui.item_label(customer.details).props("caption")


async def ask_customer(
    customer: Customer, saved: list[Customer]
) -> Customer | object | None:
    """Ask for a saved customer's details, new or changed: the customer as
    typed, DELETE if a saved one's Delete is clicked, or None if the user
    cancels. One exactly like another of `saved` is refused."""
    editing = customer.id is not None
    others = [other for other in saved if other.id != customer.id]
    with ui.dialog() as dialog, ui.card().classes("min-w-[28rem]"):
        ui.label("Edit customer" if editing else "New customer").classes("text-h6")
        name = (
            ui.input("Name", value=customer.name)
            .classes("w-full")
            .mark("customer-name")
        )
        email = ui.input("Email", value=customer.email).classes("w-full")
        email.mark("customer-email")
        with ui.row().classes("no-wrap gap-2 w-full"):
            phone = ui.input("Phone", value=format_phone(customer.phone)).classes("grow")
            phone.mark("customer-phone")
            ext = ui.input("Ext.", value=customer.ext).classes("w-16")
            ext.mark("customer-ext")

        def reformat_phone() -> None:
            try:
                phone.value = format_phone(parse_phone(phone.value or ""))
            except ValueError:
                pass

        phone.on("blur", reformat_phone)
        address = (
            ui.textarea("Address", value=customer.address)
            .props("autogrow")
            .classes("w-full")
        ).mark("customer-address")

        def typed() -> Customer:
            """The customer as typed; ValueError says what's wrong."""
            return replace(
                customer,
                name=" ".join((name.value or "").split()),
                email=(email.value or "").strip(),
                phone=parse_phone(phone.value or ""),
                ext=parse_ext(ext.value or ""),
                address=(address.value or "").strip(),
            )

        def save() -> None:
            try:
                new = typed()
                check_customer(new)
            except ValueError as problem:
                ui.notify(str(problem), type="negative")
                return
            if is_exact_duplicate(new, others):
                ui.notify(
                    f"{new.name} already exists with these exact details",
                    type="negative",
                )
                return
            dialog.submit(new)

        with ui.row().classes("w-full justify-end"):
            if editing:
                ui.button("Delete", on_click=lambda: dialog.submit(DELETE)).props(
                    "flat color=negative"
                ).mark("delete-customer")
                ui.space()
            ui.button("Cancel", on_click=lambda: dialog.submit(None)).props("flat")
            ui.button("Save", on_click=save).mark("save-customer")
    # Esc or a click outside closes it with None, as Cancel does.
    answer = await dialog
    dialog.delete()
    return answer


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
    show_tax_change = None
    if quote.revision > 0:
        before = load_quote(conn, quote.number, quote.revision - 1)
        show_tax_change = tax_change_banner(before)
    customer = CustomerFields(
        conn, quote.business_id, quote.customer, on_change=lambda: show_matches()
    )
    # The business's rates as they are now: a draft follows its rate.
    rates = {rate.id: rate for rate in list_tax_rates(conn, quote.business_id)}
    tax_rate = (
        ui.select(
            {UNTAXED: "Untaxed"}
            | {rate.id: f"{rate.name} · {rate.percent}%" for rate in rates.values()},
            label="Tax rate",
            value=quote.tax_rate_id if quote.tax_rate_id in rates else UNTAXED,
            on_change=lambda: rate_picked(),
        )
        .classes("w-64")
        .mark("tax-rate")
    )

    def with_tax_rate(changed: Quote) -> Quote:
        """`changed` taxed at the rate picked."""
        rate = rates.get(tax_rate.value)
        if rate is None:
            return replace(
                changed, tax_rate_id=None, tax_name="", tax_percent=Decimal(0)
            )
        return replace(
            changed, tax_rate_id=rate.id, tax_name=rate.name, tax_percent=rate.percent
        )

    def rate_picked() -> None:
        if show_tax_change:
            show_tax_change(with_tax_rate(quote))
        update_totals()

    if show_tax_change:
        show_tax_change(with_tax_rate(quote))

    lines_column = ui.column().classes("w-full")
    lines: list[LineInputs] = []  # in order on the quote
    added = 0  # lines ever added, so each gets its own test marker

    def add_line(item: LineItem | None = None) -> LineInputs:
        nonlocal added
        added += 1
        with lines_column:
            line = LineInputs(added, item, update_totals, remove, add_to_catalog)
        lines.append(line)
        update_totals()
        return line

    def remove(line: LineInputs) -> None:
        lines.remove(line)
        lines_column.remove(line.row)
        update_totals()

    catalog: dict[int, CatalogItem] = {}

    def load_catalog() -> None:
        nonlocal catalog
        catalog = {item.id: item for item in list_catalog_items(conn, quote.business_id)}
        from_catalog.set_options(
            {
                item.id: f"{item.description}\n{item.price_text}"
                for item in catalog.values()
            }
        )
        # Only once there's something to pick.
        from_catalog.set_visibility(bool(catalog))

    async def add_to_catalog(line: LineInputs) -> None:
        """A new catalog item from `line`, which stays as it is."""
        try:
            price = parse_money(line.price.value)
        except ValueError:
            price = None  # blank, or doesn't read yet: left to type
        answer = await ask_catalog_item(
            CatalogItem(
                quote.business_id,
                line.description.value.strip(),
                price,
                taxable=line.taxed.value,
            )
        )
        if answer is not None:
            save_catalog_item(conn, answer)
            ui.notify(f"Added {answer.description} to the catalog")
            load_catalog()

    def add_from_catalog() -> None:
        item = catalog.get(from_catalog.value)
        if item is None:
            return  # the field being cleared, below
        # In place of a blank line, as a new quote opens with one, which
        # Save would otherwise refuse.
        if lines and lines[-1].is_blank():
            remove(lines[-1])
        line = add_line(item.as_line())
        if item.price_cents is None:
            line.price.value = ""  # priced job by job: left to type
        # Ready for the next pick.
        from_catalog.value = None
        from_catalog.run_method("updateInputValue", "")
        # Clearing the typing would otherwise leave the choices open.
        from_catalog.run_method("hidePopup")

    with ui.row().classes("items-center"):
        ui.button("Add Line", on_click=lambda: add_line())
        from_catalog = (
            ui.select(
                {},
                label="Add from catalog",
                with_input=True,
                on_change=add_from_catalog,
            )
            .classes("w-64")
            .mark("add-from-catalog")
        )
        from_catalog.add_slot("option", TWO_LINE_OPTION)
    load_catalog()

    @ui.refreshable
    def foot() -> None:
        percent = with_tax_rate(quote).tax_percent
        items = []
        for line in lines:
            if not line.price.value.strip():
                # No price yet: nothing to add up (Save still asks for one).
                line.total.text = ""
                items.append(None)
                continue
            try:
                item = line.item()
                # The line's figure includes its tax when it's taxed (tax is
                # zero otherwise), so ticking Tax changes the number: a line's
                # share of the tax is plain, not only the foot's total.
                line.total.text = format_money(line_totals(item, percent).total_cents)
                items.append(item)
            except ValueError:
                line.total.text = "—"  # shown until the line reads
        if len(items) == len(lines):
            totals_foot(
                quote_totals((item for item in items if item is not None), percent)
            )
        else:
            totals_foot(None)

    def update_totals() -> None:
        foot.refresh()
        show_matches()  # a description may have changed

    def show_matches() -> None:
        descriptions = [line.description for line in lines]
        for field in descriptions + [notes] + customer.fields:
            if field is customer.ext:
                continue  # the extension isn't searched
            if field is customer.phone:
                tint(field, phone_matches(field.value or "", term))
            else:
                tint(field, matches(field.value or "", term))

    def tint(field: ui.element, matching: bool) -> None:
        if matching:
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
            typed_customer = customer.customer()
        except ValueError as problem:
            ui.notify(str(problem), type="negative")
            return None
        return with_tax_rate(
            replace(
                quote,
                notes=notes.value.strip(),
                line_items=items,
                customer=typed_customer,
            )
        )

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
                line.taxed.value,
            )
            for line in lines
        )
        return (customer.state(), tax_rate.value, typed_lines, notes.value)

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
    conn: sqlite3.Connection,
    quote: Quote,
    today: date,
    extend_days: int | None,
    can_revise: bool = False,
    draft: Quote | None = None,
) -> Quote | object | None:
    """Ask how far to extend `quote`, and extend it. `extend_days` (the
    business's setting) picks the first choice: 30 or 7 picks that one,
    any other number a custom date that many days on; None picks 30.
    `can_revise` offers Revise too, when its rate has changed. `draft`
    is its newer draft, if it has one.

    Returns the extended quote, REVISE if the user would rather revise,
    or None if the user cancels.
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
        rate = rate_now(conn, quote)
        tax_note = extend_tax_note(quote, rate, draft)
        if tax_note:
            ui.label(tax_note).mark("extend-tax-note")

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
            # Only where the note says to revise: a deleted rate has no
            # new rate to take.
            if can_revise and tax_note and rate is not None:
                ui.button("Revise", on_click=lambda: dialog.submit(REVISE)).props(
                    "outline"
                ).mark("extend-revise")
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
    rate_changed: str | None = None,
) -> None:
    """A quote that's no longer a draft, read-only.

    `on_revise` is the Revise button's handler, if it has one.
    `newer` is the newest version, if `quote` is an older one;
    `on_newest` opens it. While searching for `term`, its matches in
    the lines and notes are highlighted. `rate_changed` says how its
    tax rate has changed since it was quoted, if it should say.
    """
    def view_actions() -> None:
        """Extend and Revise, at the heading's right (none on a version
        that's neither Quoted nor Expired and can't be revised)."""
        if quote.status in (Status.QUOTED, Status.EXPIRED):
            ui.button("Extend", icon="event", on_click=on_extend).props("outline")
        if on_revise is not None:
            ui.button("Revise", icon="edit_note", on_click=on_revise).props(
                "outline"
            ).mark("revise")

    quote_heading(f"{name_of(quote)} ({quote.status})", on_history, actions=view_actions)
    if newer is not None:
        older_version_banner(newer, on_newest)
    if rate_changed:
        _, note = tax_banner()
        note.text = rate_changed
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
    # The customer and rate as they were when quoted, kept with the quote.
    if quote.customer is not None:
        if quote.customer.name:
            searched_text(quote.customer.name, term, before="Customer: ").mark(
                "view-customer"
            )
        if quote.customer.details:
            searched_text(
                quote.customer.details, term, highlighter=highlight_details
            ).classes("text-grey-7").mark("view-customer-details")
    if quote.tax_name:
        tax = f"Tax: {quote.tax_name} {quote.tax_percent}%"
    else:
        tax = "Tax: Untaxed"
    ui.label(tax).mark("view-tax-rate")
    # A quoted quote shows its frozen figures, not ones worked out again.
    for n, item in enumerate(quote.line_items, start=1):
        rest = f": {item.quantity} × {format_money(item.unit_price_cents)}"
        if discount := format_discount(item.discount_cents, item.discount_percent):
            rest += f", less {discount}"
        if item.taxed:
            rest += ", taxed"
        # The figure includes the line's tax when taxed, as the editor's
        # does (tax is zero otherwise), so a line's share of the tax shows.
        total = shown_line_totals(item, quote.tax_percent).total_cents
        rest += f" = {format_money(total)}"
        searched_text(item.description, term, after=rest).mark(f"view-line-{n}")
    totals_foot(shown_quote_totals(quote))
    if quote.notes:
        searched_text(quote.notes, term).mark("view-notes")


def searched_text(
    text: str,
    term: str,
    after: str = "",
    before: str = "",
    highlighter: Callable[[str, str], str] = highlight,
) -> ui.element:
    """`text`, between `before` and `after`; while searching for `term`,
    its matches in `text` are highlighted, as in the list. `highlighter`
    swaps in another (e.g. highlight_details, for a phone by its digits)."""
    if not term:
        return ui.label(before + text + after)
    # highlight escapes the text; ui.html's sanitizer keeps the <mark>s.
    return ui.html(
        html.escape(before) + highlighter(text, term) + html.escape(after), tag="div"
    )


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


def rate_now(conn: sqlite3.Connection, quote: Quote) -> TaxRate | None:
    """`quote`'s tax rate as it is now; None if it has none, or it's
    been deleted."""
    rates = list_tax_rates(conn, quote.business_id)
    return next((rate for rate in rates if rate.id == quote.tax_rate_id), None)


def tax_banner() -> tuple[ui.element, ui.label]:
    """An amber banner about a quote's tax, and the label for its text."""
    with ui.element("q-banner").props("dense rounded").classes(
        "w-full bg-amber-2"
    ) as banner:
        with banner.add_slot("avatar"):
            ui.icon("percent", size="sm", color="amber-10")
        note = ui.label().mark("tax-change")
    return banner, note


def tax_change_banner(before: Quote) -> Callable[[Quote], None]:
    """A banner for a revision draft's tax differing from the quoted
    version `before` it; returns what shows or hides it for the draft
    as it now stands."""
    banner, note = tax_banner()

    def show(draft: Quote) -> None:
        text = tax_change_note(before, draft)
        note.text = text or ""
        banner.set_visibility(text is not None)

    return show


def _checked_item(n: int, line: LineInputs) -> LineItem:
    """Line `n` of the form, ready to save; ValueError names the line."""
    try:
        if not line.description.value.strip():
            raise ValueError("A description is needed")
        item = line.item()
        line_totals(item, Decimal(0))  # refuses a discount over the line
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
