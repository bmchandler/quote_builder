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
- Quote templates.
- CSV export.
- Printing a quote, and exporting it as a PDF (put off until much
  later, decided 2026-10-17; now underway, see Status and plan). The
  printout opens as its own page in the user's default browser, where
  Print → Save as PDF gives a PDF with no library and no licensing
  (decided 2026-11-16, from a spike; the native window can't print on
  its own). It brings the business's details and terms (see Data), copied onto
  a quote when it's marked Quoted. The layout is the letterhead
  (layout A), chosen 2026-11-16 from three sketches on 2026-10-24 (the
  others: details at the top right beside the heading, or From and To
  boxes under it; a single line of details was ruled out).
  A pilot's printout shows its activity name as the From, like a
  business (decided 2026-11-16, replacing the earlier sketch of a
  person's name): "Pressure washing" with its contact details reads
  as a trade-name header, and a pilot has no separate person's name.
  A quote without a customer gets a "Prepared for:" label and a ruled
  line to write a name on by hand (noted 2026-11-01; done 2026-11-16).
  Lines read plainly — `2.5 × $30.00, less 10% ($7.50) = $67.50`, the
  net after any discount — with no per-line tax, since tax is pooled at
  the foot (decided 2026-11-18, superseding the per-line "taxed $X"
  shown briefly on 2026-11-17). The customer checks tax against the
  foot's Taxable row instead (Taxable × rate = Taxes).
  A percent discount shows its worked-out dollars in parentheses
  (done 2026-11-17): `less 10% ($7.50)`, so a customer needn't do the
  percentage math to check it; the dollars are the line's discount_cents
  (shown_line_totals). A flat-amount discount is already dollars
  (`less $5.00`), so it's unchanged. Both on the Quoted display and the
  printout, not the draft editor. See format_discount_detail (money.py).
  A line's unit is shown to the customer (done 2026-11-17, settling
  the 2026-11-01 open question): the quantity reads `2.5 hrs.` rather
  than a bare `2.5`, on the Quoted display and the printout. The units
  are a fixed pair, Hour and Each, stored as a short code and shown as
  `hr.`/`hrs.` (one versus any other count) or `ea.` (either way); a
  flat-rate line is one Each (`1 ea.`). A line is picked in the editor
  (a Hour/Each select by Qty), filled from a catalog item when added
  from the catalog, and a hand-typed line starts on Each. The catalog's
  own Unit is the same fixed pair (was free text; "flat" dropped, as a
  flat item is Each). See units.py.
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
  first; for printing, phone, email, website, address (one field, as
  typed), and terms (all added 2026-11-16), with a logo still to come.
  A default tax rate comes with tax rates. Every
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
  default price, unit (Hour or Each; decided 2026-11-16), and whether
  it's taxable (often not, for a service). A description is needed; the
  rest is optional, a blank price being for work priced job by job.
  Kept per business. The unit fills a line's unit when the item is
  picked, and stays in the catalog (decided 2026-11-01; see Future).
  A line copies from an item and keeps no link to it, so changing or
  deleting an item never touches a quote.
- **Quote**: number, customer (optional), tax rate, an optional Quote
  Discount (an amount or a percent; decided 2026-11-17), date issued,
  valid-through date, status, notes, and line items.
- **Line item**: description, quantity, unit (Hour or Each; how the
  quantity reads to the customer, decided 2026-11-16), unit price,
  discount, and whether it's taxed (at the quote's rate; decided
  2026-10-25). Picking a catalog item fills these in; they can then be
  changed for this quote only. A line can also be typed in by hand,
  with no catalog item, starting on Each, taxed or not as the user
  ticks it.

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

A quote is discounted in one of two ways, never both at once (decided
2026-11-17; the full reasoning and a worked walkthrough are in
[CALCULATIONS.md](CALCULATIONS.md)):

- **Line discounts** (decided 2026-10-17), per line item, as an amount
  or a percent; a line's tax is worked out on its discounted amount. A
  line discount can't be more than its line.
- **A Quote Discount** (decided 2026-11-17), one discount on the whole
  quote, as an amount or a percent, applied before tax: it comes off the
  taxable and non-taxable parts in proportion to each part's share of
  the subtotal (the odd split penny going to the taxable side, the
  customer's favor), and tax falls on what's left of the taxable part. A
  Quote Discount can't be more than the subtotal.

Only one mode per quote: allowing both would force a whole-quote
discount onto each line's tax base, with uneven-cent splits and lines
that no longer add up on their own — a known billing-confusion trap. So
with a Quote Discount no line carries its own discount, and tax is
worked out once for the quote as a whole; the app refuses, on Save, to
use both. The coupon case is still served: use a Quote Discount on that
quote. With a Quote Discount the lines read plainly (`qty × price =
amount`), the discount and tax showing once each in the foot. So the
tax stays checkable without per-line figures, the foot then also shows
(decided 2026-11-18) the "Discounted Subtotal" (Line Items − Quote
Discount) split into "Post Discount Untaxed" and "Post Discount
Taxable", the taxable part sitting just above Taxes as the figure the
rate is applied to. These three always show in Quote Discount mode, at
$0.00 where a part is empty, rather than being hidden.

In the form, a line's Discount field and the Quote Discount field each
take either style: `10%` is a percent, anything else an amount (`5`,
`$5.50`); blank or zero is none. A tax rate's Percent takes `7.25` or
`7.25%`, blank for none (decided 2026-10-19, for the Tax % a line had
then).

Each line is worked out to the cent (totals.py): quantity × unit price,
less the discount, rounded half up (half a cent rounds up). Tax,
though, is figured once for the whole quote, not per line (decided
2026-11-18): on the pooled taxable base — the sum of the taxed lines'
nets, after discounts — so a shown Taxable × the rate lands on the
Taxes row exactly. (Earlier the app taxed each line and summed; pooling
is what makes the aggregate check hold, and it unifies the two discount
modes — both now read plainly and tax once in the foot.)

That's per-invoice (aggregate) rounding, a standard US method on the
combined state and local rate; QD mode already used it. States that use
bracket tables instead (Maryland, and Alabama in part) aren't supported
(decided 2026-10-19). Per-item rounding (tax each line, then sum) is no
longer used; it can differ from the pooled figure by a cent or two, and
can't be checked against a single Taxable row. Neither method is the
filed return — the business reconciles real tax at filing on period
totals — and this isn't tax advice; see [CALCULATIONS.md](CALCULATIONS.md).

A draft's totals are worked out from its lines whenever shown, never
stored. Once a quote is quoted, its figures are frozen (decided
2026-10-19): each line's amount and discount (a line carries no tax of
its own now that tax is pooled; with a Quote Discount its discount is
zero too, being a whole-quote figure), and the foot's totals (the
worked-out Quote Discount among them) are stored with it and shown from
then on, so a later
change to how totals are worked out never changes what a customer was
given. A revision starts as a draft, so it's worked out with the rules
of the day until it's quoted and frozen in turn. Old rules aren't kept
around to rework old quotes.

The tax rate's name and percent freeze onto a quote the same way when
it's quoted, and so do the business's details for the printout
(decided 2026-11-16): the name, address, phone and extension, email,
website, and terms as they were, kept on the quote so its printout
stays as it was even if the business later changes. A draft keeps no
such copy (it prints, when it can, from the business as it is now).

The quote's foot shows totals: line items before discounts (labelled
"Line Items", for specificity so a customer doesn't take it for
physical items only), then the discount in play — "Discounts" for line
discounts, "Quote Discount" for a whole-quote one, and neither when
there's none — then taxes and the total. A discount row shows only for
the mode in use, so the foot always reads cleanly. Since tax is pooled,
the foot also shows the base it's figured on, so a customer can check
it (decided 2026-11-18): in Quote Discount mode the "Discounted
Subtotal", "Post Discount Untaxed", and "Post Discount Taxable"
breakdown (above); in line-discount mode a "Discounted Subtotal" (only
when there are discounts) and a "Taxable" row (only when there's tax)
just above Taxes, where Taxable × rate = Taxes. Line-discount mode
leaves out an "Untaxed" row for simplicity — it's the more common mode
and often has no discount at all, so the foot stays minimal; an
all-services quote just shows Taxes $0.00. They update as the form is
typed in; a line with no price yet counts as nothing, and while any
line doesn't read, its total and the foot show a dash.

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

Schema changes are versioned with SQLite's `PRAGMA user_version`
(decided 2026-11-20; storage.py). schema.sql is the latest schema: it
builds a fresh database, stamped at the current version, and by `CREATE
TABLE IF NOT EXISTS` it also adds any new table to an existing database
for free. A change to a table already there — a new column, a changed
constraint — can't come that way, so it gets a migration: `_MIGRATIONS[v]`
brings a database from version v-1 to v, the migrations between its
version and the current one run in order when it's opened, each with its
version stamp in one transaction, so a failed migration leaves the old
version behind. Version 0 is the first release's schema (2026.11.20). A
database written by a newer app than the one opening it is refused
(`DatabaseTooNew`), not guessed at. Before the first release this wasn't
needed — the rule was "delete the database", and it retires here (see
[Path to first release](#path-to-first-release), step 9).

Dropping a column or changing a constraint can't go through `ALTER TABLE`
(SQLite refuses `DROP COLUMN` on a table whose definition carries
comments, as ours do, and can't alter a constraint at all), so a
migration rebuilds the table: create it anew, copy the rows, drop the
old, rename. A rebuilt table's children would lose their link, so the
migrations run with `PRAGMA foreign_keys` off and a `foreign_key_check`
at the end (`MigrationFailed` if anything dangles). A throwaway `probe`
column exercised the framework end to end: migration 1 added it (an easy
`ADD COLUMN`) and migration 2 dropped it (the rebuild), leaving the
schema where it started.

## Versioning

Ported from pota_logger (decided 2026-11-19; tooling and the branch
cutover both landed the same day — see [Path to first
release](#path-to-first-release), step 3).

- Calendar versioning: a release is named for the date it's made, as
  `YYYY.M.D` (`2026.10.10`), with `.1`, `.2` for a second or third
  release the same day (`2026.10.10.1`). The app isn't a library: no
  code depends on it, so semantic versioning's "is this change
  breaking?" has no one to answer to, and the date needs no judgment
  call. A quote's own number and revision (see Data) are unrelated to
  the app's version.
- No leading zeros (`2026.1.5`, not `2026.01.05`): Python's version
  rules (PEP 440) drop them, so `uv version 2026.01.05` writes
  `2026.1.5`, and the tag must read the same as `pyproject.toml`. The
  version stays `0.1.0` until the first dated release.
- A release is made with `uv run tag_new_version.py`
  ([RELEASING.md](RELEASING.md) has the steps for a person), whether an
  agent or a person makes it, for every version bump. It takes today's
  date, with `.1`, `.2` when that's tagged, or a version given, refused
  if malformed, already tagged, or older than the newest tag. It refuses
  a tree with changes, a branch other than `dev`, a `main` that `dev`
  doesn't lead on from, or nothing under `## Unreleased` in CHANGELOG.md,
  and asks `Tag <version>? [y/N]` before changing anything; on `y` it
  runs the tests first (they take a while, so a mistake stops at once).
  Then, always together and in this order:
  1. `uv version <date>`, which sets the version in `pyproject.toml`
     and `uv.lock` (checked to read exactly `<date>`).
  2. Rename CHANGELOG.md's `## Unreleased` heading to `## <date>`, and
     commit the three files, as `Version <date>`.
  3. Tag that commit with the same `<date>` (no `v`; a plain tag).
  4. Move `main` to that commit, only forward (see Branches below).
  5. `uv version <date>+dev`, committed (`pyproject.toml`, `uv.lock`)
     on `dev` as `Version <date>+dev`, so dev builds don't report the
     release's version.

  It never pushes; it prints `git push origin dev main <date>`. An agent
  making a release still pauses for the operator's go-ahead before
  running it, as before any commit.
- Why together: what the app reports as its version (shown in About,
  app_version.py) comes from `pyproject.toml` (the installed package's
  metadata), never from the tag. A tag alone leaves the app reporting
  the last release's version; a version set without a tag names a
  release no commit can be found by. Done together, the reported version
  points at exactly one tagged commit.
- Between releases, `dev`'s version is the last release's plus `+dev`
  (`2026.10.12+dev`, a PEP 440 local version), and a dev build installed
  from git reports the commit it was built from too
  (`2026.10.12+dev.5f820a58`, the first 8 characters), wherever the app
  reports its version (app_version.py). The commit can't be written in
  `pyproject.toml` (a commit can't contain its own hash), so it's read
  when the app runs, from the `direct_url.json` an installer writes for
  an install from git (PEP 610). A clone run (`uv run`) or an install
  from a package index has no commit there, so its version is reported
  as written. PyPI refuses local versions, which never reach it.
- Branches: `main` only ever points at the newest release's tag, so an
  install from git without a branch or tag (`uv tool install
  git+<repo-url>`) gets the newest release, and `uv tool upgrade` the
  next one. Work goes on `dev`, and releases are made there; `main` is
  never committed to, only moved forward by `tag_new_version.py`. Tags
  are for releases only: a dev build is installed by branch (`@dev`,
  which `uv tool upgrade` follows) or by commit (`@<commit>`, which it
  doesn't).
- An installed dev build (its version ends `+dev`) keeps its data in
  `~/.local/share/quote-builder-dev/` instead of a release's
  `quote-builder/`, so testing one never touches a release's quotes
  (data_folder.py). A clone keeps its `data/` either way.
- `branch_guard.py` (beside `tag_new_version.py`, for developers, not
  in the package) installs git hooks that refuse a commit on `main`, and
  a push that would set the remote's `main` to a commit no release tag
  points at, or delete it. Its install changes only its own line in each
  hook file (git_hooks.py); see [DEVELOPMENT.md](DEVELOPMENT.md).

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
- Totals (totals.py): per-line discount and tax, a whole-quote discount
  (one discount mode per quote), the quote's foot. The math and its
  reasoning are documented in [CALCULATIONS.md](CALCULATIONS.md).
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
  - Business details and terms (decided 2026-11-16): for the printout
    (see Future), on the same form. Between Name and "Quotes valid for
    (days)": Address (a multi-line box), Phone with a narrow Ext.
    beside it, Email, and Website, each optional, each with a greyed
    example. After "Extend by (days)": Terms, a single free-text block
    (not structured fields), its example "Payment due within 30 days.
    50% deposit to schedule." The phone is stored as its ten digits and
    shown in the standard form, snapping to it on leaving the field,
    and the extension is digits only, as a customer's are (see Phone
    numbers); a phone that isn't ten digits, or an extension that isn't
    digits, holds up Save with "Phone: …" or "Ext.: …", like a bad day
    count. A business extension is less common than a customer's but
    useful for a partnership or a PBX line (decided 2026-11-16). Blank
    is fine for all of them. They save with the form's Save, and apply to a pilot as to a
    business. Not on the screen yet beyond Settings: the printout
    carries them, and freezing a copy onto a quote at Mark Quoted comes
    next (see Status and plan).
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
    settings. One row per item ("Mow lawn · $45.00 / hr."), by
    description in any case, and "Add catalog item…". Adding or
    clicking one opens a dialog: Description, Default price, Unit (a
    Hour/Each select), and Taxable. It saves on its own, as a tax
    rate's does; an item already saved has Delete.
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
  - About (decided 2026-11-19): in Settings' side panel, below
    Customers and above Back to Quotes, an About button opens, on the
    right, "About Quote Builder": the one-line description and credit,
    then "Version:", "GitHub Repo:" (a link), and "License:" (MIT, a
    link to opensource.org), and where this install keeps its data. The
    repo and license links open the system browser (as the printout
    does), not the native window's webview. The libraries the app
    builds on, with their licenses, are listed in DEVELOPMENT.md
    (Licensing), not on this screen. The version (app_version.py)
    reports `0.1.0` until the first dated release, and
    `<release>+dev.<commit>` on a dev build installed from git; the
    reader is built ahead of the release tooling (see Path to first
    release, step 3) and reports a plain version until then.
  - Add from catalog (decided 2026-11-01): once the business has an
    item, a field beside a draft's Add Line. Typing narrows the items
    by description, price, or unit, each shown as its description with
    "$45.00 / hr." below. Picking one adds a line of it: its
    description, quantity 1, its unit, its price (blank if it has
    none), and Tax ticked if it's taxable; all can then be changed for this
    quote only. It fills a last line that's still blank instead, as a
    new quote opens with one. The field then clears for the next pick.
  - Add to Catalog (decided 2026-11-01): once a line has a description,
    a circled plus shows at the right of its Description field, with
    "Add to Catalog" on mouse-over. Tab skips it, going on to Qty.
    Clicking it opens the catalog's dialog, filled in from the line
    (a price that doesn't read starts blank; Unit takes the line's).
    Saving adds the item, ready to pick; the line
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
    draft opens in the form (description, quantity, unit, unit price,
    discount, Tax, and notes, a Quote Discount beside the Tax rate, with
    totals updating as you type); Save saves it, refusing a Quote
    Discount used alongside a line discount. Any other status opens
    read-only.
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
    A quoted quote shows "Tax: Home county 7.25%" ("Tax: Untaxed").
    A line's figure (in the form, and on a quoted quote after "= ") is
    its net after any discount; tax is pooled at the foot (decided
    2026-11-18), so ticking Tax doesn't change a line's figure — it
    moves the line into the foot's Taxable base and so changes Taxes.
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
    Save, pinned to the form's bottom-right corner (decided 2026-11-04):
    right-justified so the bottom-centre status toast doesn't cover them
    until it clears, and dropped to the foot (the form fills the window
    height) so they stay in the corner when the window is taller than
    the content. Mark Quoted asks for the date issued (today) and
    valid-through (the business's days valid on, 30 to start). Valid-through
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
  - Buttons on a quoted quote (decided 2026-11-04): Extend and Revise
    (outlined, as they were) sit at the quote heading's right, Extend
    then Revise, then Copy (decided 2026-11-16), on one line. The
    Version history link, when there is one, tucks below the quote
    number instead of beside them, so the heading's width stays the same
    with or without a history. The buttons were below the tax line in
    the body before; up here a line's figures aren't split by them.
    Their icons were dropped (decided 2026-11-16) so the three text-only
    labels fit comfortably at the 1000-pixel window width.
  - Duplicating a quote (decided 2026-11-16): a Copy button, at the
    heading's right, starts a new quote (its own number, drawn on save)
    copying the lines, notes, tax rate, and customer, as changeable; it
    opens as an unsaved "New Quote" draft, so nothing is stored until
    Save. None of what a finalized version was given carries over (its
    number and revision, dates, frozen figures, extensions, status), so
    a copy is a plain new quote, not a revision. Copy is offered on any
    quote: a draft (new or saved) as well as a finalized one. On a draft
    it copies the current form contents, so unsaved edits come along; a
    draft with unsaved changes is saved first, through a "Save before
    copying?" dialog (Keep Editing, Save & Copy), so those edits aren't
    left only on the copy. A quote's tax rate follows the business's
    rates as they are now, as a revision's does, so a copy of a quote
    taxed at a since-deleted rate opens Untaxed.
  - Printout (decided 2026-11-16): a Print button, at a finalized
    quote's heading right (after Copy), writes the quote as a
    standalone HTML page and opens it in the user's default browser,
    where the page asks to print itself so Save as PDF is one step away
    (no PDF library; see Status and plan for the spike). Layout A, the
    letterhead: the business's name and contact details centered at the
    top, above the quote's heading and dates, "Prepared for" the
    customer, the tax rate, the lines (each with its figure), the
    totals foot, then Notes and, below them, Terms when present (Terms
    are the bottom-most part of the page; decided 2026-11-16). The
    page's own "Print / Save as PDF" button is in the app's primary
    blue, so the printout matches the window. It reads the business's
    details frozen onto the quote at Mark Quoted (see Data), so an
    issued quote's printout doesn't shift if those details later change.
    On a draft there's no Print yet (a draft is a work in progress, not
    something to send). A pilot's letterhead shows its activity name,
    like a business's name (decided 2026-11-16). A quote with no
    customer shows a "Prepared for:" label and a ruled line to write a
    name on by hand, in place of the customer's details. The page is
    self-contained (its styles inline) and written to a temp file, so
    it opens from a file, not the running server.
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

Next: printing, for a production release, is underway (started
2026-11-16). The on-screen app was feature-complete after duplicating
(2026-11-16); printing is the largest piece left. Duplicating had been
deferred to Future on 2026-11-11, then brought back on 2026-11-16 to
round off the non-print work first.

The print path (decided 2026-11-16, from a spike): the printout opens
in the user's default browser as its own page, where Print → Save as
PDF gives a PDF with no library and no licensing to vet. The spike
found pywebview 6.2.1 exposes no native print API and doesn't wire
WebKitGTK's print signal, so the native window can't print on its own;
the browser route sidesteps that and keeps the print layout decoupled
from the working screen. The earlier plan to try native print first,
with a PDF library as fallback, is dropped.

The steps (reordered 2026-11-16 to keep each one tryable: the print
route went before freezing, since freezing alone shows nothing on
screen while the route is something to try end to end):

1. Business details and terms: done (2026-11-16). A business's Address,
   Phone (with an extension), Email, Website, and a single free-text
   Terms block, entered in its Settings and stored per business; the
   printout carries them. See the Settings screen item.
2. The print route: done (2026-11-16), layout A, the letterhead (see
   the Printout screen item).
3. Freeze a copy of the business's details and terms onto the quote
   when it's marked Quoted: done (2026-11-16), as totals and the tax
   rate freeze (see Data). The printout now reads the frozen copy, so a
   quoted quote's printout doesn't shift if the business's details
   later change; a draft (which has none) still prints from the
   business as it is now.
4. From and To: done (2026-11-16). The pilot rule was reversed (a
   pilot's From is its activity name, like a business; see the Printout
   item), so this came down to the handwrite space: a quote with no
   customer gets a "Prepared for:" label and a ruled line to write on.

Printing is feature-complete with step 4 (2026-11-16): details and
terms, the print route, freezing, and the handwrite space are all in.
What's left for a production release is weighing the printing polish
in Future (a banner image, the line-unit question) if wanted.

Terms are a single free-text block (decided 2026-11-16), not structured
fields, as the cuts had weighed; structured fields can come later if it
proves too loose.

## Path to first release

The roadmap to a first release (an MVP / 1.0), captured 2026-11-18. The
aim is to have something releasable to show at a meetup (the next is
2026-11-19 evening; more follow, so the date isn't hard-committed), and
— just as important — to **go through a post-release change for real**,
to learn what updating the app and an existing user's database will be
like once people already have data. The git and release mechanics follow
what worked on the **pota_logger** project (also a `uv` project); part
of this work is comparing the two and porting pota_logger's setup and
its automation here, not reinventing it.

Today this repo still commits on `main` (see CLAUDE.md, "How we work");
the dev/release split below is what changes that.

Ordered, though some can overlap:

1. **Write the docs for a first release.** `README.md` (currently empty)
   as the MVP's front door — what the app is, install via `uv`, basic
   use — plus any other Markdown that a first release needs. Keep it
   terse and user-facing (developer material stays in the developer
   docs). Link [CALCULATIONS.md](CALCULATIONS.md) from it (this folds in
   the Later-polish item below).

   Drafted 2026-11-19: `README.md` (terse front door, links
   CALCULATIONS.md), `LICENSE.md` (MIT), and a `CHANGELOG.md` stub. The
   install block points at `github.com/bmchandler/quote_builder`, which
   only goes live at step 5 (wire up GitHub); a screenshot is still to
   be added. The two apt lines (Debian 13 / LMDE, and Ubuntu 24.04+ /
   Mint 22+) share the same package names now that Ubuntu 24.04 ships
   `libgirepository-2.0-dev`; keep DEVELOPMENT.md's line in step.
2. **Last double-checks and polish** before preparing the release: a
   pass over wording, the full test suite, and anything in Later polish
   worth pulling in first.
3. **Set up the dev/release git methodology from pota_logger.** A
   separate `dev` branch for development; `main` becomes purely a
   release branch (only ever the newest release's tag, moved by the
   release step). Port pota_logger's automated tooling that aids this
   workflow and guards against the usual mistakes — including its
   `RELEASING.md` (the release procedure) and the release script(s)
   (e.g. `tag_new_version.py`), adapted to this project.

   Done 2026-11-19. Tooling: `tag_new_version.py`, `branch_guard.py`,
   `src/quote_builder/git_hooks.py`, `RELEASING.md`, the dev-build data
   folder split (data_folder.py), and the [Versioning](#versioning)
   section, all with tests. Cutover: `dev` created from the last `main`
   commit, the branch guard installed, work now on `dev`, and CLAUDE.md
   and DEVELOPMENT.md flipped to the dev/main workflow. Next: step 4.
4. **Compare the two projects** and confirm the development and release
   workflow is nailed down correctly here — that this project's setup
   matches pota_logger's where it should.
5. **Wire up GitHub** similar to pota_logger (the public mirror; vet
   that what's going out is safe to publish first, per CLAUDE.md).
6. **Do the initial release** and check that install via `uv` works as
   it did on pota_logger.
7. **Make a small development change** on `dev` and run the full release
   procedure (changelog, the merge, the tag, etc.) to exercise it.
8. **Check that a release update works** as expected for someone already
   on the previous version.
9. **Post-release DB change.** Discuss, and possibly do, a small schema
   change to see how it plays out when users already have data in their
   databases — i.e. a migration / update script run on version update.
   This is the main thing to learn from the exercise; until now the rule
   has been "delete the DB" (no migrations before release, see CLAUDE.md
   and [Storage](#storage)), and this is where that rule retires.

   Done 2026-11-20: a phase-1 smoke test confirmed the failure mode (a
   column added to an existing table isn't created by `CREATE TABLE IF NOT
   EXISTS`, so the app hits `no such column`), and the migration framework
   was built (approach A, `PRAGMA user_version`; see [Storage](#storage)).
   It ran end to end through real releases: a throwaway `probe` column was
   added in 2026.11.20.1 and a real 2026.11.20→2026.11.20.1 update migrated
   an existing database with its data intact, then 2026.11.20.2 dropped the
   column with a table rebuild (the harder path: foreign keys off, checked
   after). With that, the rule in [Storage](#storage) and CLAUDE.md is now
   migrations, not "delete the database".

## Later polish

Polish to weigh once the main features are done (started
2026-11-01). Captured so it isn't lost, not promised: an item may no
longer fit by then, or the work before may have changed it.

- A setting to open the printout to the browser's normal view rather
  than straight to the print dialog (noted 2026-11-16, possible not
  planned): the page asks to print itself on load today; some users may
  prefer to see it first and print when ready.

(The earlier "link CALCULATIONS.md from the README" item now lives in
[Path to first release](#path-to-first-release), step 1.)
