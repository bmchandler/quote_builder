# Quote Builder — Requirements

## Purpose

A simple desktop app for building and tracking quotes, for micro
businesses and solo consultants: odd software jobs, yard work, house
cleaning, and the like. Built for real use by its owner for freelance
work first, and as a portfolio piece second.

## Scope

In scope:

- One user, one business, on one machine. No accounts or sign-in.
- Linux as the target system, run as a native desktop window (NiceGUI's
  native mode), not in a browser (decided 2026-10-17). macOS and
  Windows aren't targeted or tested. The window is pywebview on GTK
  (WebKitGTK), with PyGObject built in the venv against stock Debian
  `-dev` packages (decided 2026-10-18; see DEVELOPMENT.md): no Qt, and
  no venv reaching system site-packages.
- Local storage in SQLite.
- A business profile, clients, a catalog of reusable services, and
  quotes made of line items.
- Tracking each quote's status.

Out of scope:

- More than one user or business, and syncing between machines.
- Installers or packaging beyond what uv gives.
- Sending email from the app.

Future (not now):

- Turning an accepted quote into an invoice.
- Duplicating a quote, or quote templates.
- CSV export.
- Printing a quote, and exporting it as a PDF (put off until much
  later, decided 2026-10-17). Print straight from the app first, if the
  native window can. A PDF library must have an MIT-like license.
- A simple dashboard (quote counts, extensions, and the like).
- A time of day on the valid-through date, such as the end of office
  hours: "Valid through 11/18/2026 6:30 pm EST" (decided 2026-10-19).
  The zone label would follow the date (EST in winter, EDT in summer,
  from the time zone's rules); whether to offer plain "Eastern" or a
  fixed "EST" too is to be decided.

## Data

Money is held as a whole number of cents, never as a float; amounts
are worked out with `Decimal` and rounded to the cent where shown.

- **Business profile** (one): name, contact details, logo, default
  tax rate, and terms printed at the foot of each quote.
- **Client**: name, email, phone, address.
- **Tax rate**: a name (`Home county`) and its parts, each a name and a
  percent (State 4.75%, County 1.5%, City 1%); its combined rate is
  their sum.
- **Catalog item**: a reusable service or part, with a description,
  default price, unit (hour, each, flat, and so on), and whether it's
  taxable (often not, for a service).
- **Quote**: number, client, tax rate, date issued, valid-through
  date, status, notes, and line items.
- **Line item**: description, quantity, unit price, discount, and tax
  rate.
  Picking a catalog item fills these in; they can then be changed for
  this quote only. A line can also be typed in by hand, with no catalog
  item, its tax rate set by hand (none, if untaxed).

Tax is per line item (decided 2026-10-17): parts usually carry sales
tax, services often don't, and the app doesn't decide which; the user
does. Fees (trip, disposal, and so on) are line items like any other,
taxed or not as the user sets them (decided 2026-10-17).

Whether something is taxed and at what rate are kept apart (decided
2026-10-19), as they hang on different things: what's sold, and where.
A catalog item says only whether it's taxable; a tax rate says how
much, built from its parts (state, county, city, district), so a part
that changes is changed once. A quote takes the business's default
tax rate, changeable for a job elsewhere. Picking a catalog item fills
in a line's tax with the quote's combined rate if the item is taxable,
none if not. The line still stores the number itself, copied in, so a
line typed by hand works as now, and a quoted quote's figures freeze as
below. A tax category per item (parts, food, services) instead of
taxable yes or no is a later option, for states that tax such groups
differently. A quote shows one Tax line; tax by part (state, local) is
an option, as the parts are kept. Built with the catalog and business
profile steps.

Discounts are per line item, as an amount or a percent (decided
2026-10-17); a line's tax is worked out on its discounted amount.
There's no whole-quote discount. A discount can't be more than its
line. In the form, one Discount field takes either: `10%` is a percent,
anything else an amount (`5`, `$5.50`); blank or zero is none. Tax %
takes `7.25` or `7.25%`, blank for none (decided 2026-10-19).

Each line is worked out to the cent on its own (totals.py): quantity ×
unit price, less the discount, then tax on what's left, each rounded
half up (half a cent rounds up). The quote's totals add up the lines'
cents, so the foot always matches the lines (decided 2026-10-19).

That's the usual US sales tax rule (tax carried to a third decimal
place, rounded up from 5), with tax figured per item, which most
states allow beside per invoice, on the combined state and local
rate. States that use bracket tables instead (Maryland, and Alabama in
part) aren't supported, nor is rounding per invoice (decided
2026-10-19).

A draft's totals are worked out from its lines whenever shown, never
stored. Once a quote is quoted, its figures are frozen (decided
2026-10-19): each line's amount, discount, and tax (its total is
their sum), and the foot's totals are stored with it and shown from
then on, so a later
change to how totals are worked out never changes what a client was
given. A revision starts as a draft, so it's worked out with the rules
of the day until it's quoted and frozen in turn. Old rules aren't kept
around to rework old quotes.

The quote's foot shows totals: items before discounts, discounts, tax,
and the total. They update as the form is typed in; a line with no
price yet counts as nothing, and while any line doesn't read, its total
and the foot show a dash.

Quote numbers (decided 2026-10-17) are `Q-` and a random code shaped
like a phone number, three characters then four: `Q-7KQ-M9XD`. The
characters are Crockford's Base32 (digits and capital letters, leaving
out I, L, O, and U, which are easy to misread), so about 34 billion
codes. A new code is drawn when a quote is made; the database refuses
a code already used, and a new one is drawn on that rare clash. The
code says nothing about the date or how many quotes there are. An
invoice made from a quote will later share its code, with `I-` for
`Q-`.

Once a quote has been quoted to the client, changes to it are
revisions, numbered with a suffix: `Q-7KQ-M9XD-R1`, `-R2`, and so on.
A draft has no suffix, however often it's changed.

Revisions (decided 2026-10-17):

- A revision starts as a Draft. Until it's quoted, the last quoted
  version stays Quoted, as it's what the client holds, and its
  valid-through date still counts.
- Once the revision is quoted, the version before it becomes
  Superseded: read-only, kept for history.
- Quoted, Declined, and Expired quotes can be revised; Accepted ones
  can't (a change after acceptance is a matter for invoicing, later).
- Each revision has its own valid-through date, and its own
  extensions.

Quote statuses: Draft, Quoted, Accepted, Declined, Expired, and
Superseded for a revised version (Quoted, not Sent, as a quote may be
given in person; decided 2026-10-17). A Quoted quote becomes Expired
on its own once past its valid-through date (decided 2026-10-17).

A quote's date is its last good day, inclusive, and always worded
"Valid through", the clearest common form (decided 2026-10-19):
"until" is read both ways (in contracts it's often taken to leave the
day out), and "expires on" is used both for the last good day and the
first dead one. So a quote valid through 11/18/2026 is good all of
that day and Expired from 11/19/2026. The database column keeps the
name `valid_until`.

The user can extend a Quoted or Expired quote, such as when a client
asks for more time at the quoted price, by setting a later
valid-through date (decided 2026-10-17); an expired one is then
Quoted again (decided 2026-10-19). The new date replaces the old one
on the quote; each extension is also logged out of the way (date
extended, old and new valid-through dates), so the original date and
the number of extensions can be looked up later.

## Code layout

- Business logic (totals, tax, numbering, status changes) is plain
  Python, apart from the UI, and tested without it.
- The NiceGUI pages only call into that logic.
- All SQL is in storage.py and schema.sql; the rest of the app works
  with the dataclasses in quotes.py.
- Amounts are typed as text and read straight into Decimal (money.py),
  never through float (so no `ui.number`).

## Storage

One SQLite database file, kept where pota_logger keeps its data
(decided 2026-10-17): `data/` in a clone, `~/.local/share/quote-builder`
for an installed release, and `~/.local/share/quote-builder-dev` for
an installed development build, so testing never touches the real data.
Built so far: `data/` and the installed release's folder
(data_folder.py); the development build's folder comes with releases.

Plain `sqlite3` from the standard library, no ORM (decided 2026-10-18):
a small single-user app, and the SQL stays in plain view. The schema is
in schema.sql, run on every start. Tables are STRICT; money is whole
cents (INTEGER), exact decimals TEXT, dates ISO 8601 TEXT.

## Status and plan

Built (as of 2026-10-19), each with tests:

- Quote numbers (quote_numbers.py).
- SQLite storage (schema.sql, storage.py): saving a new quote with its
  line items, saving changes to a draft (lines replaced), loading one
  back, and listing quotes with search.
- Totals (totals.py): per-line discount and tax, the quote's foot.
- The screen (app.py), in the native window:
  - The quote list down the left side, always shown beside the quote
    at any window width (never a pop-over; decided 2026-10-19). Each
    quote has one row, for its newest version (decided 2026-10-19),
    showing the number and status, the first line's description, the
    date last saved (local time), and the total; newest first, the open
    quote highlighted. The time saved is kept to the second, in UTC
    (decided 2026-10-19): enough to keep quotes in order. Search, as
    you type, matches the number, the notes, or any line's description,
    in any case, in any version (decided 2026-10-19).
  - Search matches are highlighted (decided 2026-10-19), in a soft
    amber, in the row's number and first line. A match the row doesn't
    show (notes, a later line, an older version) adds a small italic
    line with where and an excerpt: "Notes: …the back hedges need…",
    "Line Item 2: Flush downspouts", "R1, Line Item 3: …" ("Line
    Item", not "Line", which reads like code, or "Item", odd for a
    service). On trial: if it's too busy, it may become just where
    ("Match in notes"), or go.
  - On the right: a landing message until a quote is picked; New Quote
    opens a blank form, and clicking a quote in the list opens it. A
    draft opens in the form (description, quantity, unit price,
    discount, tax %, and notes, with totals updating as you type); Save
    saves it. Any other status opens read-only.
  - Leaving a form with unsaved changes asks first (decided
    2026-10-19): New Quote, or opening another quote from the list,
    shows "Discard unsaved changes?" with Keep Editing and Discard; Esc
    or a click outside keeps editing. Changes means the form differs
    from when it was opened or last saved, so a change undone by hand
    doesn't count. Clicking the quote already open does nothing.
    Closing the window doesn't ask: that waits for NiceGUI to pass on
    pywebview's closing event, which it doesn't yet (decided
    2026-10-19; no workaround). Until then, the README tells users to
    save before closing.
  - Dates (decided 2026-10-19): the list shows `Oct 19, 2026`; a
    quote and its dialogs show `10/19/2026`. Date fields take
    `11/18/2026` (or `2026-11-18`), typed or picked from a calendar.
  - Marking a draft Quoted (decided 2026-10-19): Mark Quoted, beside
    Save, asks for the date issued (today) and valid-through (30 days
    on, until the business profile makes it a setting). Valid-through
    can't be before the date issued, and a quote needs a line.
    Confirming saves the form's changes and marks it Quoted together,
    freezing its figures (see Data); it then opens read-only, showing
    both dates. The database refuses a non-draft without its dates and
    frozen totals.
  - Expiry: Quoted quotes past their valid-through date are marked
    Expired whenever the list is drawn or a quote is opened. That
    isn't a save, so the time last saved stays as it was.
  - Extending (decided 2026-10-19): Extend, on a Quoted or Expired
    quote, offers 30 more days (picked to start), 7 more days (both
    counted from the valid-through date, or from today if that's
    past), or a custom date, showing the new date as it's picked. A
    setting for which one starts picked may come later. The new date
    must be later than the old one and not past. Once extended, the
    quote shows "Extended once; first valid through 11/18/2026" (or
    "2 times", and so on).
  - Revisions (decided 2026-10-19): Revise, right of Extend on the
    newest version when it's Quoted, Declined, or Expired, opens a
    form copied from it (lines and notes; no dates), headed
    "Q-7KQ-M9XD-R1 (New revision)". Nothing is stored until Save or
    Mark Quoted, so leaving it unchanged leaves no trace. Quoting it
    makes the versions before it Superseded. A quote has at most one
    draft (the database refuses a second); on an older version,
    Revise reads "Open Draft R1" and opens it instead.
  - Version history (decided 2026-10-19): once a quote has more than
    one version, a "Version history" link at the top right of it
    opens a list of its versions, newest first, each with its status,
    dates (or date saved, for a draft), and total; clicking one opens
    it.

Next, growing the screen, storage, and tests together in small steps:

1. Open the version a search found (planned 2026-10-19): clicking a
   row while searching opens the version the snippet points to (an
   older one, if that's where it matched), so the user can confirm
   it's the quote they remember. Any older version then shows a
   banner at the top, such as "This is an older version; R2 (Draft)
   is current", with a button to go to the current one, so it's
   never taken for the current one in a hurry. It also helps find a
   draft in progress through an older version's text.
2. The business profile and tax rates, clients, then the catalog.
