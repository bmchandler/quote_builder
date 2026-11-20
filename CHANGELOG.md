# Changelog

What changed in each release, newest first. Changes not released yet are
under Unreleased.

(The version scheme is set when the release methodology is ported from
pota_logger; see REQUIREMENTS.md, "Path to first release".)

## 2026.11.20.2

### Changed

- Dropped the throwaway `probe` column added in 2026.11.20.1, now that it
  has served its purpose, exercising the table-rebuild migration path.
  Your data migrates automatically on update, as before.

## 2026.11.20.1

### Changed

- The database now carries a schema version and brings itself up to date
  when you update the app, so a release can change the schema without
  asking you to start over (groundwork; see REQUIREMENTS.md, Storage). A
  database from a newer app than the one opening it is refused rather
  than guessed at.

### Added

- A throwaway column (`probe` on businesses), read by nothing, to
  exercise the migration path end to end.

## 2026.11.20

The first release: a desktop app for building price quotes, for micro
businesses and solo consultants. It runs as a native window on Linux,
stores everything locally in one SQLite file, and works offline.

### Added

- Businesses and pilots, each with its own settings: name, how many days
  a quote stays valid, a default Extend-by, and the address, phone (with
  extension), email, website, and free-text terms used on the printout.
  A pilot shows in italics; the business last used reopens on start.
- Tax rates per business, each with named parts and a combined percent,
  one of them the default; a rate a draft still uses can't be deleted.
- Saved customers per business, and a reusable catalog of services and
  parts (description, default price, unit, taxable).
- Quotes with line items (description, quantity, unit, unit price, a
  per-line discount, and tax), a whole-quote discount as an alternative,
  and tax pooled at the foot. Add a line from the catalog, or add a
  line to the catalog.
- A customer on each quote, found from the saved customers or typed in
  for a walk-in, with phone numbers in a standard US form.
- Quote numbers with revisions (R1, R2, …). Mark Quoted freezes the
  quote's figures, its tax rate, and the business's details for the
  printout; Extend moves the valid-through date; Revise opens a new
  revision; Copy starts a fresh quote from an existing one.
- Statuses kept current — Draft, Quoted, Expired (past valid-through),
  Superseded — with a banner when a tax rate has changed since a quote
  was quoted.
- A quote list with search as you type (number, notes, line
  descriptions, customer), matches highlighted and scoped to the
  business shown, and a version history per quote.
- A printout: a standalone HTML page opened in your browser as a
  letterhead, where Print / Save as PDF makes a PDF with no extra
  software.
- Local SQLite storage; once installed, your data lives in
  `~/.local/share/quote-builder/` (see README.md, "Your data").
- MIT license. README.md (install and use) and CALCULATIONS.md (how
  discounts and tax are figured) for users; DEVELOPMENT.md and
  RELEASING.md for working on the app.
