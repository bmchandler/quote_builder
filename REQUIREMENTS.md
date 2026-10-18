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
  Windows aren't targeted or tested.
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

## Data

Money is held as a whole number of cents, never as a float; amounts
are worked out with `Decimal` and rounded to the cent where shown.

- **Business profile** (one): name, contact details, logo, default
  sales tax rate, and terms printed at the foot of each quote.
- **Client**: name, email, phone, address.
- **Catalog item**: a reusable service or part, with a description,
  default price, unit (hour, each, flat, and so on), and tax rate
  (often none for a service).
- **Quote**: number, client, date issued, valid-until date, status,
  notes, and line items.
- **Line item**: description, quantity, unit price, discount, and tax
  rate.
  Picking a catalog item fills these in; they can then be changed for
  this quote only. A line can also be typed in by hand, with no catalog
  item, its tax rate set by hand (none, if untaxed).

Tax is per line item (decided 2026-10-17): parts usually carry sales
tax, services often don't, and the app doesn't decide which; the user
does. Fees (trip, disposal, and so on) are line items like any other,
taxed or not as the user sets them (decided 2026-10-17).

Discounts are per line item, as an amount or a percent (decided
2026-10-17); a line's tax is worked out on its discounted amount.
There's no whole-quote discount.

The quote's foot shows totals: items before discounts, discounts, tax,
and the total.

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
  valid-until date still counts.
- Once the revision is quoted, the version before it becomes
  Superseded: read-only, kept for history.
- Quoted, Declined, and Expired quotes can be revised; Accepted ones
  can't (a change after acceptance is a matter for invoicing, later).
- Each revision has its own valid-until date, and its own extensions.

Quote statuses: Draft, Quoted, Accepted, Declined, Expired, and
Superseded for a revised version (Quoted, not Sent, as a quote may be
given in person; decided 2026-10-17). A Quoted
quote
becomes Expired on its own once past its valid-until date (decided
2026-10-17). The user can extend it, such as when a client asks for
more time at the quoted price, by setting a later valid-until date.
The new date replaces the old one on the quote (decided 2026-10-17);
each extension is also logged out of the way (date extended, old and
new valid-until dates), so the original date and the number of
extensions can be looked up later.

## Code layout

- Business logic (totals, tax, numbering, status changes) is plain
  Python, apart from the UI, and tested without it.
- The NiceGUI pages only call into that logic.

## Storage

One SQLite database file, kept where pota_logger keeps its data
(decided 2026-10-17): `data/` in a clone, `~/.local/share/quote-builder`
for an installed release, and `~/.local/share/quote-builder-dev` for
an installed development build, so testing never touches the real data.

## Status and plan

Built: quote number generation (quote_numbers.py).

Next: build the business logic and storage, test first, then the quote screen: building a quote, saving
it, and opening it again (the first focus, decided 2026-10-17). A
single view per quote for now.
