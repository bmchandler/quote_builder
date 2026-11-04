# Quote Builder — Requirements

## Purpose

A simple desktop app for building quotes to give to customers, for
micro businesses and solo consultants: odd software jobs, yard work,
house cleaning, and the like. Built for real use by its owner for
freelance work first, and as a portfolio piece second.

## Scope

In scope:

- One user, on one machine. No accounts or sign-in.
- One or more businesses (decided 2026-10-20): gig workers often run
  a main business and a side one or two. Each has its own quotes,
  customers, catalog, and settings; nothing is shared between them.
- Linux as the target system, run as a native desktop window (NiceGUI's
  native mode), not in a browser (decided 2026-10-17). macOS and
  Windows aren't targeted or tested. The window is pywebview on GTK
  (WebKitGTK), with PyGObject built in the venv against stock Debian
  `-dev` packages (decided 2026-10-18; see DEVELOPMENT.md): no Qt, and
  no venv reaching system site-packages.
- Local storage in SQLite.
- Business details and settings, customers, a catalog of reusable
  services, and quotes made of line items.
- Each quote's status up to giving it to the customer: whether it's
  still a draft, still valid, or replaced by a newer version.

Out of scope:

- More than one user, and syncing between machines.
- Installers or packaging beyond what uv gives.
- Sending email from the app.
- Following a quote to its outcome, such as accepted or declined, or
  any tracking at that level (decided 2026-11-02). The app builds
  quotes to give to customers; what happens after is up to the user,
  whose way of handling acceptance could be anything.
- Checking for likely duplicate customers, or merging them (decided
  2026-11-02). Two Jane Does, or a shared phone or address, may well
  be different people, and one person may use two emails, so a check
  can only guess, and its false alarms grow with the list. A duplicate
  costs little, as the details tell them apart. The exception: a
  customer identical to another in every field, which can't be told
  apart and adds nothing, is refused.

Future (not now):

- Turning a quote into an invoice.
- Duplicating a quote, or quote templates.
- CSV export.
- Printing a quote, and exporting it as a PDF (put off until much
  later, decided 2026-10-17). Print straight from the app first, if the
  native window can. A PDF library must have an MIT-like license.
  It brings the business's details and terms (see Data), copied onto
  a quote when it's marked Quoted, and a From and To on the printout:
  for a pilot, a person's name and contact details, never the
  pilot's name. Layouts to weigh then, from sketches on 2026-10-24:
  a letterhead above the heading, the details at the top right
  beside the heading, or From and To boxes under it (a single line
  of details was ruled out).
  A quote without a customer gets a space on the printout to write a
  name or a note by hand (noted 2026-11-01).
  Whether and how a customer sees a line's unit ("3 hours") is to be
  settled with it (noted 2026-11-01): a line has no unit today, and
  a field for one is tight in a line's row at the window's width.
- A banner image at the top left instead of the business's name.
- Archiving or purging old quotes (noted 2026-11-01).
  Brainstorm, nothing decided (noted 2026-11-02): an Archived area to
  search, holding each quote as its printed or PDF version, with
  export and delete: delete anything before a certain year, say, or
  first export the PDFs as a tar.gz to keep a digital copy.
- Deleting a tax rate drafts use, guided (noted 2026-10-25): in place
  of the refusal, a dialog listing those drafts, each a link to open
  it and pick another rate, with a button to make the new rate first.
  The order matters: a user who moves drafts to a stand-in rate before
  the right one exists can lose track of which drafts to move again.
- A tax rate changed, on the printout (noted 2026-10-25): a short
  note when the region's rate changed since the previous quote or
  extension. Which rate applies appears to have no single rule
  (looked into 2026-11-02): often the one in effect when the sale
  completes, not when it's quoted, with the seller owing any
  shortfall; some places appear to protect contracts signed before a
  change, often with conditions; services may go by billing period or
  by when the work is accepted. A quote usually isn't a signed
  contract yet, so the old rate looks less likely to be protected.
  Likely varies by state: check before building. So the printout
  should also say that its tax is figured at today's rates and may
  change if they do before the sale (wording to settle); a final
  requote before the sale may be what a careful business does.
- A simple dashboard (quote counts, extensions, and the like): counts
  per business or pilot and in all, drafts, and metrics around
  extensions (noted 2026-10-24). Likely a section opened as Settings
  is (noted 2026-10-25). Maybe, a ways out: a count of open quotes
  whose tax rate has changed since they were quoted, with a way to
  get to each, for calling customers ahead of the sale.
- A time of day on the valid-through date, such as the end of office
  hours: "Valid through 11/18/2026 6:30 pm EST" (decided 2026-10-19).
  The zone label would follow the date (EST in winter, EDT in summer,
  from the time zone's rules); whether to offer plain "Eastern" or a
  fixed "EST" too is to be decided.
- A minimum window size (noted 2026-10-20): made narrow enough, the
  quote's layout starts to break (the totals' "Discounts" slides left
  of the Extend/Revise buttons' left edge). pywebview takes a
  `min_size`, passed through NiceGUI's `app.native.window_args`;
  the size is to be found by trying it.

## Data

Money is held as a whole number of cents, never as a float; amounts
are worked out with `Decimal` and rounded to the cent where shown.

- **Business** (one or more): a business or a pilot (decided
  2026-10-24), and a name. A pilot is an idea being tried out, not
  yet worth a business of its own; its name says what the work is
  (`Pressure washing`), for the user to tell pilots apart, and is
  never printed. A business's name (`John Doe's Lawn Service`) is
  the one customers see. A pilot becomes a business by switching it to
  Business and naming it, in its Settings: its quotes stay with it,
  as they belong to it, not to its name. Also how many days a new
  quote is valid for (30 to start) and how many days Extend offers
  first; later, for printing, phone, email, website, address (one
  field, as typed), terms printed at the foot of each quote, and a
  logo; for a pilot, a person's name and contact details instead of
  a business name. A default tax rate comes with tax rates. Every
  detail is optional, the name too (decided 2026-10-20): work often
  starts before a business has a legal name, and software that won't
  start without one is a common irritation. An unnamed business is
  made on first start, filled in later from Settings. A quoted quote
  will keep a copy of its business's details as they were (as with
  its figures), so a later change doesn't alter what a customer was
  given; to give a customer new details, revise the quote.
- **Customer** (decided 2026-11-01; "customer", not "client", which
  reads as consulting, while customer is understood about
  everywhere): name, email, phone, address (one field, as typed).
  Reworked 2026-11-02: a quote's customer exists to print its details
  and change them for the print, so every quote holds its own copy,
  all of it optional, as a line holds its catalog item's. Details are
  mostly typed quote by quote. A business's saved customers are only
  a shortcut for filling those in, meant for regulars, though a user
  may save everyone; a saved customer needs a name. Nothing points at
  one, so changing or deleting it never touches a quote, draft or
  quoted, and a quote changing its copy never touches the list.
- **Tax rate**: a name (`Home county`) and its parts, each a name and a
  percent (State 4.75%, County 1.5%, City 1%); its combined rate is
  their sum.
- **Catalog item**: a reusable service or part, with a description,
  default price, unit (hour, each, flat, and so on), and whether it's
  taxable (often not, for a service). A description is needed; the
  rest is optional, a blank price being for work priced job by job.
  Kept per business. The unit is for the business user choosing an
  item, and stays in the catalog (decided 2026-11-01; see Future).
  A line copies from an item and keeps no link to it, so changing or
  deleting an item never touches a quote.
- **Quote**: number, customer (optional), tax rate, date issued, valid-through
  date, status, notes, and line items.
- **Line item**: description, quantity, unit price, discount, and
  whether it's taxed (at the quote's rate; decided 2026-10-25).
  Picking a catalog item fills these in; they can then be changed for
  this quote only. A line can also be typed in by hand, with no catalog
  item, taxed or not as the user ticks it.

Tax is per line item (decided 2026-10-17): parts usually carry sales
tax, services often don't, and the app doesn't decide which; the user
does. Fees (trip, disposal, and so on) are line items like any other,
taxed or not as the user sets them (decided 2026-10-17).

Whether something is taxed and at what rate are kept apart (decided
2026-10-19), as they hang on different things: what's sold, and where.
A catalog item says only whether it's taxable; a tax rate says how
much, built from its parts (state, county, city, district), so a part
that changes is changed once. A quote takes the business's default
tax rate, changeable for a job elsewhere, or Untaxed (an exempt
customer). Each line is taxed or not (decided 2026-10-25): taxed
lines all use the quote's rate, so a line can't have a rate of its
own; picking a catalog item ticks it if the item is taxable. A
draft follows its rate as it is now, so a county's change reaches
drafts already written; marking it Quoted keeps the rate's name and
percent with the quote, with its figures, so a later change to the
rate never alters what a customer was given. A tax category per item
(parts, food, services) instead of taxable yes or no is a later
option, for states that tax such groups differently: it's the case a
single rate per quote doesn't cover. A quote shows one Tax line; tax
by part (state, local) is an option, as the parts are kept.

Discounts are per line item, as an amount or a percent (decided
2026-10-17); a line's tax is worked out on its discounted amount.
There's no whole-quote discount. A discount can't be more than its
line. In the form, one Discount field takes either: `10%` is a percent,
anything else an amount (`5`, `$5.50`); blank or zero is none. A tax
rate's Percent takes `7.25` or `7.25%`, blank for none (decided
2026-10-19, for the Tax % a line had then).

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
change to how totals are worked out never changes what a customer was
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

Once a quote has been quoted to the customer, changes to it are
revisions, numbered with a suffix: `Q-7KQ-M9XD-R1`, `-R2`, and so on.
A draft has no suffix, however often it's changed.

Revisions (decided 2026-10-17):

- A revision starts as a Draft. Until it's quoted, the last quoted
  version stays Quoted, as it's what the customer holds, and its
  valid-through date still counts.
- Once the revision is quoted, the version before it becomes
  Superseded: read-only, kept for history.
- Quoted and Expired quotes can be revised, even if the customer has
  accepted one (decided 2026-11-02): something unknown to both may
  turn up mid-work. The app assumes the user revises only when that
  makes sense.
- Each revision has its own valid-through date, and its own
  extensions.

Quote statuses: Draft, Quoted, Expired, and Superseded for a revised
version (Quoted, not Sent, as a quote may be given in person; decided
2026-10-17). A Quoted quote becomes Expired
on its own once past its valid-through date (decided 2026-10-17).

A quote's date is its last good day, inclusive, and always worded
"Valid through", the clearest common form (decided 2026-10-19):
"until" is read both ways (in contracts it's often taken to leave the
day out), and "expires on" is used both for the last good day and the
first dead one. So a quote valid through 11/18/2026 is good all of
that day and Expired from 11/19/2026. The database column keeps the
name `valid_until`.

The user can extend a Quoted or Expired quote, such as when a customer
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

Built (as of 2026-11-01), each with tests:

- Quote numbers (quote_numbers.py).
- SQLite storage (schema.sql, storage.py): saving a new quote with its
  line items, saving changes to a draft (lines replaced), loading one
  back, and listing a business's quotes with search. Businesses and
  their settings (business.py): one made on first start, more added
  from Settings, each holding whether it's a pilot, its name, days
  valid, Extend's days, and tax rates (each its parts, one the
  default) so far. Every quote belongs to one, and
  every version of it to the same one. The business picked last is
  remembered (decided 2026-10-24), so the app opens on it. Saved
  customers (customers.py), each a business's, and a quote's own copy
  of its customer's details. Catalog items (catalog.py), each a
  business's.
- Totals (totals.py): per-line discount and tax, the quote's foot.
- The screen (app.py), in the native window:
  - The quote list down the left side, always shown beside the quote
    at any window width (never a pop-over; decided 2026-10-19), 350
    pixels wide, so a row's number and status stay on one line even
    for a revision (decided 2026-10-20; at 300, "Q-…-R1 · Quoted"
    wrapped). Each
    quote has one row, for its newest version (decided 2026-10-19),
    showing the number and status, its customer's name (decided
    2026-11-01: in the first line's place, the row's layout kept as
    it was) or, without one, the first line's description, the
    date last saved (local time), and the total; newest first, the open
    quote highlighted. The time saved is kept to the second, in UTC
    (decided 2026-10-19): enough to keep quotes in order. Search, as
    you type, matches the number, the notes, any line's description,
    or the customer's name, email, phone, or address on the quote
    (decided 2026-11-01), in any case, in any version (decided
    2026-10-19). The list
    and search cover only the business shown (decided 2026-10-20),
    and a new quote belongs to it. The list scrolls on its own, below Search
    and New Quote.
  - Settings (decided 2026-10-20; reworked 2026-10-24): at the bottom
    of the side panel, below a divider, a Settings button. Settings
    takes over the side panel, in place of the name, Search, and the
    quotes (hidden, not cleared: the search is still there on
    return): "Settings", then the businesses and pilots, each with
    its kind ("Business", "Pilot") under its name, businesses first,
    then pilots, each by name in any case; "Add business or pilot…"
    below them; and at the bottom, where Settings was, "Back to
    Quotes", so one spot opens and closes it. No quote counts: those
    belong in a dashboard (see Future). Settings opens on the
    business shown; clicking another in the list opens its settings
    on the right, not its quotes. Add opens a blank form, headed "New
    business or pilot". The right side holds the form, headed by the
    business's name ("Unnamed business", or "Unnamed pilot", for a
    lone one without), with Save. First, Business or Pilot (Business
    to start) and Name (decided 2026-10-24), whose example follows the
    choice: "John Doe's Lawn Service", or "Pressure washing" with the
    note "An activity name works well. Pilots show in italics in the
    list." A name is needed once there's more than one: "Name: a name
    is needed once there's more than one business or pilot". Then
    "Quotes valid for (days)", which Mark Quoted's valid-through
    starts from, and "Extend by (days)", blank to start, which picks
    Extend's first choice. Each is a whole number above 0; a message
    names the field that isn't. Leaving the form with unsaved changes
    (another business, Add, or Back to Quotes) asks first, as a
    quote's form does.
  - Tax rates (decided 2026-10-24): below a business's settings, under
    "Tax rates", one row per rate ("Home county · 7.25% · Default"),
    by name in any case, and "Add tax rate…". A saved business only:
    a new one gets them once saved. Adding or clicking one opens a
    dialog: Name, its parts (each a Part, its example "State, County,
    or City, etc.", which may be blank, and a
    Percent; "Add part", and an × to remove one),
    "Combined: 7.25%" as it's typed ("—" until every part reads), and
    "Default for new quotes", checked to start for a business's first
    rate. A rate needs a name and a part; a message says which, or
    which part doesn't read. The dialog saves on its own, apart from
    the form's Save, so a rate never waits unsaved; a rate already
    saved has Delete. One default per business: making another the
    default takes over. Delete is refused while a draft uses the rate
    (decided 2026-10-25): "Home county is used by 2 drafts", as the
    drafts would lose their tax without a word. A quoted quote keeps
    its own copy, so it doesn't hold a delete up. For now; a guided
    flow is planned (see Future).
  - Catalog (decided 2026-11-01): in Settings' side panel, below the
    divider and above Back to Quotes, a Catalog button opens, on the
    right, the catalog of the business picked in the list, headed
    "Catalog: John Doe's Lawn Service". It's off for a new business
    until saved. Clicking a business, even that one, goes back to its
    settings. One row per item ("Mow lawn · $45.00 / hour"), by
    description in any case, and "Add catalog item…". Adding or
    clicking one opens a dialog: Description, Default price, Unit (its
    example "hour, each, flat, etc."), and Taxable. It saves on its
    own, as a tax rate's does; an item already saved has Delete.
  - Customers (decided 2026-11-02): in Settings' side panel, below
    Catalog, a Customers button opens, on the right, the customers of
    the business picked in the list, headed "Customers: John Doe's Lawn
    Service", as Catalog does. It's off for a new business until saved,
    and clicking a business goes back to its settings. One row per
    customer, by name in any case, with their details below, and "Add
    customer…". Adding or clicking one opens a dialog, "New customer"
    or "Edit customer": Name (needed), Email, Phone (with Ext. beside
    it; see Phone numbers), Address. It saves
    on its own, as a catalog item's does; a customer already saved has
    Delete. Nothing points at a saved customer, so neither changes any
    quote. Adding or editing a customer so they match another in every
    field, case included once spaces are tidied, is refused, with the
    dialog left open: "Jane Doe already exists with these exact
    details". That's the only duplicate check (see Scope).
  - Add from catalog (decided 2026-11-01): once the business has an
    item, a field beside a draft's Add Line. Typing narrows the items
    by description, price, or unit, each shown as its description with
    "$45.00 / hour" below. Picking one adds a line of it: its
    description, quantity 1, its price (blank if it has none), and
    Tax ticked if it's taxable; all can then be changed for this
    quote only. It fills a last line that's still blank instead, as a
    new quote opens with one. The field then clears for the next pick.
  - Add to Catalog (decided 2026-11-01): once a line has a description,
    a circled plus shows at the right of its Description field, with
    "Add to Catalog" on mouse-over. Tab skips it, going on to Qty.
    Clicking it opens the catalog's dialog, filled in from the line
    (a price that doesn't read starts blank; Unit starts blank, as a
    line has none). Saving adds the item, ready to pick; the line
    stays as it is and doesn't count as a change to the quote. The
    catalog allows duplicates, so nothing checks for one.
  - A long description (decided 2026-11-01): Description widens with
    the window. Where it doesn't fit, it ends in "…" before the plus
    while the field isn't being typed in, and mouse-over shows it all.
    "Tax", not "Taxed", labels a line's box, for the room.
  - The top left (decided 2026-10-24) shows "Quote Builder" until the
    business has a name, then the name, in italics for a pilot. Once
    there's a second, it's a dropdown of all the names, in the same
    order as Settings, with a line between the businesses and the
    pilots; picking one shows its quotes (asking first, with unsaved
    changes). The window's title stays "Quote Builder".
  - Search matches are highlighted (decided 2026-10-19), in a soft
    amber, in the row's number and second line (customer or first
    line). A match the row doesn't show (notes, a later line, the
    customer's other details, an older version) adds a small italic
    line with where and an excerpt: "Notes: …the back hedges need…",
    "Line Item 2: Flush downspouts", "Customer: 555-0134", "R1, Line
    Item 3: …" ("Line Item", not "Line", which reads like code, or
    "Item", odd for a service). A row showing its customer hides the
    first line, so a match there gets its line too ("Line Item 1: Mow
    lawn"). On trial: if it's too busy, it may become just where
    ("Match in notes"), or go.
  - On the right: a landing message until a quote is picked; New Quote
    opens a blank form, and clicking a quote in the list opens it. A
    draft opens in the form (description, quantity, unit price,
    discount, Tax, and notes, with totals updating as you type); Save
    saves it. Any other status opens read-only.
  - Customer on a quote (decided 2026-11-02, replacing a picker tied
    to saved customers): a draft's "Customer", above Tax rate, is Name
    and Phone (with Ext. beside it), then Email and Address, in two
    columns, each optional, even to mark it Quoted (but a phone or
    extension that's entered must read; see Phone numbers). Changes
    count for "Discard
    unsaved changes?". A quoted quote shows "Customer: Jane Doe" with
    the details under it, below its dates; without a name, just the
    details. A revision starts from the version before's details.
  - Phone numbers (decided 2026-11-04): a phone is stored as its ten
    digits and shown in the standard form `(123) 456-7890`, so storage
    and display stay decoupled. Entry takes the common forms
    (`1234567890`, `123.456.7890`, `(123) 456-7890`); on leaving the
    field it snaps to the standard form. Only ten digits are taken (the
    user base is US); anything else is refused with a message that, like
    a bad amount, holds up Save and Mark Quoted until it's fixed or
    cleared. A phone stays optional: blank is fine, even to mark Quoted.
    An extension sits in a narrow "Ext." field beside the phone, digits
    only, optional, shown after it as `(123) 456-7890 ext. 12`. Search
    matches a phone by its digits, any punctuation on either side
    ignored, so `456`, `1234567890`, and `(123) 456` all find it; the
    extension isn't searched. A phone match is highlighted by its
    digits, so a run that spans the shown form's separators is marked
    whole: searching `4567890` highlights `456-7890` (in the list's
    match line and on an open quote), not nothing.
  - Find customer (decided 2026-11-02): once the business has a saved
    customer, a button beside the "Customer" heading opens a dialog,
    "Find customer": Search, narrowing as you type by name, email,
    phone (by its digits; see Phone numbers), or address, in any case,
    each shown as its name with its
    details below, so several Jane Does can be told apart ("No
    customers match" when none do). Clicking one closes it and fills
    every field (the extension included), replacing what's there, even
    with blanks; Cancel
    leaves them. Search is its own dialog, not suggestions in the Name
    field, so typing a walk-in's name stays plain typing.
  - Add to Customers (decided 2026-11-02): once Name holds text, a
    circled plus shows at its right, with "Add to Customers" on
    mouse-over. Tab skips it. Clicking it opens the "New customer"
    dialog filled in from the quote. Saving adds them, ready to find;
    it doesn't count as a change to the quote.
  - Tax on a quote (decided 2026-10-25): a draft's "Tax rate", above
    its lines, lists "Untaxed" and the business's rates ("Home county
    · 7.25%"), starting on the default (Untaxed without one). Each
    line has a Tax box, unticked to start (as a blank Tax % was).
    Changing the rate works the taxed lines out again at once;
    Untaxed leaves the boxes ticked, so switching back restores the
    tax. The rate counts as a change for "Discard unsaved changes?".
    A quoted quote shows "Tax: Home county 7.25%" ("Tax: Untaxed"),
    and its lines say "taxed". A line's own figure (in the form, after
    its Tax box; on a quoted quote, its "= ") includes its tax when it's
    taxed, so ticking Tax changes it and a line's share of the tax is
    plain, not only the foot's total (decided 2026-11-04).
  - Tax changed on a revision (decided 2026-11-02): a revision draft
    takes its rate as it is now, so when its percent differs from what
    the version before was quoted at, an amber banner under the heading
    says so, following the Tax rate picked: "Home county's rate changed
    since R1 was quoted: 7.25% to 7.5%"; with another rate picked, or
    Untaxed, "Tax changed since R1 was quoted: Home county 7.25% to
    Other county 6%"; with the rate since deleted and the draft left
    Untaxed, "Home county, which R1 was quoted at (7.25%), is no
    longer a tax rate." The first version goes by its number in place
    of "R1". Same percent, no banner, even under a new name. It's only
    told, not chosen for: which rate applies is the user's call. A new
    quote has no banner, as nothing was quoted before it.
  - Rate changed on a quoted quote (decided 2026-11-02): a Quoted one
    shows the same banner when its rate has changed since: "Home
    county's rate changed since this was quoted: 7.25% to 7.5%", or
    "Home county, which this was quoted at (7.25%), is no longer a tax
    rate." Expired and Superseded ones show none: their price isn't
    live. Extend, on a Quoted or Expired quote, says the same in its
    dialog, adding "Extending keeps 7.25%." and, when the rate still
    exists, "To use the new rate, revise instead." with a Revise
    button between Cancel and Extend, which opens the revision, so
    the user needn't know to cancel first. An older version has no
    such button, as it has no Revise; its newest is always a draft,
    so it says "Draft R1 uses the new rate." instead (nothing, if the
    draft has moved to another rate). A line that's only a status has
    no period; more than one sentence takes them. Extending never
    changes a quote's tax: its total is what the customer holds, so
    the new rate comes through Revise.
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
    Save, asks for the date issued (today) and valid-through (the
    business's days valid on, 30 to start). Valid-through
    can't be before the date issued, and a quote needs a line.
    Confirming saves the form's changes and marks it Quoted together,
    freezing its figures and its tax rate as it is then (see Data); it
    then opens read-only, showing
    both dates. The database refuses a non-draft without its dates and
    frozen totals.
  - Expiry: Quoted quotes past their valid-through date are marked
    Expired whenever the list is drawn or a quote is opened. That
    isn't a save, so the time last saved stays as it was.
  - Extending (decided 2026-10-19): Extend, on a Quoted or Expired
    quote, offers 30 more days (picked to start), 7 more days (both
    counted from the valid-through date, or from today if that's
    past), or a custom date, showing the new date as it's picked.
    Settings' "Extend by (days)" picks the first choice (decided
    2026-10-20): 30 or 7 picks that one; any other number picks
    Custom, its date that many days on; blank, 30. The new date
    must be later than the old one and not past. Once extended, the
    quote shows "Extended once; first valid through 11/18/2026" (or
    "2 times", and so on).
  - Revisions (decided 2026-10-19): Revise, right of Extend on the
    newest version when it's Quoted or Expired, opens a
    form copied from it (lines and notes; no dates), headed
    "Q-7KQ-M9XD-R1 (New revision)". Nothing is stored until Save or
    Mark Quoted, so leaving it unchanged leaves no trace. Quoting it
    makes the versions before it Superseded. A quote has at most one
    draft (the database refuses a second). An older version has no
    Revise; its banner leads to the newest (see Older versions).
  - Version history (decided 2026-10-19): once a quote has more than
    one version, a "Version history" link at the top right of it
    opens a list of its versions, newest first, each with its status,
    dates (or date saved, for a draft), and total; clicking one opens
    it.
  - Opening the version a search found (decided 2026-10-20): while
    searching, clicking a row opens the newest version that matched
    (an older one, if that's where the match is), so the user can
    confirm it's the quote they remember. Without a search, or when
    the row shows the match, a click opens the newest version. A
    search matching several versions still gives one row (decided
    2026-10-20): lines and notes mostly carry over between
    revisions, so a row per version would mostly repeat.
  - Highlights on the open quote (decided 2026-10-20): while
    searching, a read-only quote highlights the matches in its
    customer, lines, and notes, as the list does, following the
    search as it's typed or cleared, and across versions opened from
    Version history: a quick way to see which versions word it
    differently. In a draft's form, an input can't highlight part of
    its text, so each description or notes field holding the term is
    tinted pale amber instead, following the search and the typing,
    and each customer field too (decided 2026-11-02). That way the
    user needn't wonder whether the draft holds the term.
  - Older versions (decided 2026-10-20): any version but the newest,
    however it was opened, shows an amber banner under its heading:
    "This is an older version. R2 (Draft) is the newest.", with "Go
    to Draft R2" ("Go to R2" if it isn't a draft: the button says
    what it opens). "Newest", not "current": while R2 is a draft, the
    quoted R1 is still the one the customer has. The point is that a
    stale version is plain at a glance. The banner replaced the "Open
    Draft R2" button an older version had: both went to the newest.

Next, in order (decided 2026-11-02):

1. Duplicating a quote.

Business details and terms wait for printing (decided 2026-10-24):
the app doesn't need them on screen, and keeping them to the
printout leaves its layout, wording, and output free to change apart
from the working screen. See Future.

## Later polish

Polish to weigh once the main features are done (started
2026-11-01). Captured so it isn't lost, not promised: an item may no
longer fit by then, or the work before may have changed it.

- A quoted quote's buttons, such as Extend and Revise, moved
  elsewhere on it (where is to be settled).
