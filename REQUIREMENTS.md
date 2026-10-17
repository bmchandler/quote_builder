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
- Exporting a quote as a PDF to send to a client.
- Tracking each quote's status.

Out of scope:

- More than one user or business, and syncing between machines.
- Installers or packaging beyond what uv gives.
- Sending email from the app (the user attaches the PDF themselves).

Future (not now):

- Turning an accepted quote into an invoice.
- Duplicating a quote, or quote templates.
- CSV export.

## Data

Money is held as a whole number of cents, never as a float; amounts
are worked out with `Decimal` and rounded to the cent where shown.

- **Business profile** (one): name, contact details, logo, default tax
  rate, and terms printed at the foot of each quote.
- **Client**: name, email, phone, address.
- **Catalog item**: a reusable service or product, with a description,
  default price, and unit (hour, each, flat, and so on).
- **Quote**: number, client, date issued, valid-until date, status,
  notes, line items, and an optional discount.
- **Line item**: description, quantity, unit price. Picking a catalog
  item fills these in; they can then be changed for this quote only.

Quote statuses: Draft, Sent, Accepted, Declined, Expired.

## Code layout

- Business logic (totals, tax, numbering, status changes) is plain
  Python, apart from the UI, and tested without it.
- The NiceGUI pages only call into that logic.
- PDF rendering is its own module.

## Open questions

- Quote numbering: plain sequence (`Q-0001`), or year-based
  (`2026-001`)?
- Tax: one rate per quote, or per line item (some services taxed,
  others not)?
- Discount: per quote, per line item, or both? Amount, percent, or
  both?
- Expired: set automatically once past the valid-until date, or by
  hand?
- PDF: WeasyPrint (HTML template; needs system Pango) or ReportLab
  (pure Python, more layout code)?
- Where data lives for an installed copy (`~/.local/share/...`) versus
  a clone (`data/`).

## Status and plan

Built: nothing yet beyond the uv project.

Next: settle the open questions, then build the business logic and
storage, test first, before any UI.
