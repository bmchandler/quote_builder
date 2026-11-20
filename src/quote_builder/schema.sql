-- Run on every start; IF NOT EXISTS makes that safe. Until close to the
-- first release, change tables freely: delete the database to rebuild.
--
-- STRICT tables refuse a value of the wrong type, as SQLite otherwise
-- stores whatever it's given. Money is whole cents (INTEGER). Exact
-- decimals (quantities, percents) are TEXT, read back as Decimal; dates
-- are TEXT in ISO 8601 (2026-10-18), which also sorts correctly.

-- A business (or pilot) the user quotes for, and its settings.
CREATE TABLE IF NOT EXISTS businesses (
    id         INTEGER PRIMARY KEY,
    -- Blank until given; a pilot's is what the work is, not a business's.
    name       TEXT    NOT NULL DEFAULT '',
    -- 1 for a pilot (an idea being tried out), 0 for a business. STRICT
    -- has no boolean type.
    pilot      INTEGER NOT NULL DEFAULT 0 CHECK (pilot IN (0, 1)),
    -- Days from issue to a new quote's valid-through date.
    valid_days INTEGER NOT NULL DEFAULT 30 CHECK (valid_days > 0),
    -- Days Extend offers first; NULL (unset) for its own first, 30. A
    -- CHECK passes on NULL (NULL > 0 is unknown, not false).
    extend_days INTEGER CHECK (extend_days > 0),
    -- Details for the printout, each blank until given. The phone is
    -- stored as its ten digits (shown formatted), as a customer's is.
    address    TEXT    NOT NULL DEFAULT '',
    phone      TEXT    NOT NULL DEFAULT '',
    -- A phone extension, digits only, kept apart as a customer's is.
    ext        TEXT    NOT NULL DEFAULT '',
    email      TEXT    NOT NULL DEFAULT '',
    website    TEXT    NOT NULL DEFAULT '',
    -- A single free-text block, as typed, line breaks and all.
    terms      TEXT    NOT NULL DEFAULT ''
) STRICT;

-- A business's sales tax rates, each the sum of its parts.
CREATE TABLE IF NOT EXISTS tax_rates (
    id          INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses (id),
    name        TEXT    NOT NULL CHECK (name != ''),
    -- 1 for the rate a new quote starts with.
    is_default  INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1))
) STRICT;

-- At most one default per business (a partial index, as for drafts).
CREATE UNIQUE INDEX IF NOT EXISTS one_default_tax_rate
    ON tax_rates (business_id) WHERE is_default = 1;

CREATE TABLE IF NOT EXISTS tax_rate_parts (
    id          INTEGER PRIMARY KEY,
    tax_rate_id INTEGER NOT NULL REFERENCES tax_rates (id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,           -- order in the rate
    name        TEXT    NOT NULL,           -- State, County; may be blank
    percent     TEXT    NOT NULL,
    UNIQUE (tax_rate_id, position)
) STRICT;

-- A business's saved customers, its regulars mostly. A quote copies what it
-- needs, so nothing points here and a customer can always be changed or
-- deleted, as with the catalog.
CREATE TABLE IF NOT EXISTS customers (
    id          INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses (id),
    name        TEXT    NOT NULL CHECK (name != ''),
    email       TEXT    NOT NULL DEFAULT '',
    phone       TEXT    NOT NULL DEFAULT '',   -- ten digits (1234567890)
    ext         TEXT    NOT NULL DEFAULT '',   -- a phone extension, digits only
    address     TEXT    NOT NULL DEFAULT ''   -- as typed, line breaks and all
) STRICT;

-- A business's services and parts. A line copies what it needs, so nothing
-- points here and an item can always be changed or deleted.
CREATE TABLE IF NOT EXISTS catalog_items (
    id          INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses (id),
    description TEXT    NOT NULL CHECK (description != ''),
    price_cents INTEGER CHECK (price_cents >= 0),  -- NULL: priced job by job
    -- How a line made from this item reads its quantity; see units.py.
    unit        TEXT    NOT NULL DEFAULT 'each' CHECK (unit IN ('hour', 'each')),
    taxable     INTEGER NOT NULL DEFAULT 0 CHECK (taxable IN (0, 1))
) STRICT;

-- What the app remembers between runs: one row at most (id 1).
CREATE TABLE IF NOT EXISTS app_state (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    -- The business picked last, which the app opens on.
    business_id INTEGER REFERENCES businesses (id)
) STRICT;

CREATE TABLE IF NOT EXISTS quotes (
    id          INTEGER PRIMARY KEY,
    -- Every version of a quote belongs to the same business.
    business_id INTEGER NOT NULL REFERENCES businesses (id),
    number      TEXT    NOT NULL,                -- Q-7KQ-M9XD
    revision    INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    status      TEXT    NOT NULL DEFAULT 'Draft' CHECK (status IN
                    ('Draft', 'Quoted', 'Expired', 'Superseded')),
    issued_on   TEXT,
    valid_until TEXT,
    notes       TEXT    NOT NULL DEFAULT '',
    -- The tax rate its taxed lines use; NULL for Untaxed. Deleting a
    -- rate leaves a quoted quote its frozen copy below (the app refuses
    -- while a draft uses it).
    tax_rate_id INTEGER REFERENCES tax_rates (id) ON DELETE SET NULL,
    -- A whole-quote discount: an amount (cents) or a percent (TEXT),
    -- never both, and never with a line's own discount (one discount mode
    -- per quote; see CALCULATIONS.md). As typed, kept on a draft and a
    -- quoted quote alike; the frozen worked-out amount is below.
    quote_discount_cents   INTEGER,
    quote_discount_percent TEXT,
    -- When last saved: UTC, ISO 8601 with the offset, shown in local time.
    updated_at  TEXT    NOT NULL,
    -- The foot's totals, stored once quoted (frozen) and shown from then
    -- on; a draft's are worked out from its lines whenever shown.
    frozen_items_cents          INTEGER,
    frozen_discount_cents       INTEGER,
    -- The quote discount worked out to cents when quoted (0 if none).
    frozen_quote_discount_cents INTEGER,
    frozen_tax_cents      INTEGER,
    frozen_total_cents    INTEGER,
    -- The rate as it was when quoted ('' and '0' for Untaxed).
    frozen_tax_name       TEXT,
    frozen_tax_percent    TEXT,
    -- Its customer's details, its own copy, as typed or filled in from
    -- the customers table ('' for none). Nothing points at that table.
    customer_name    TEXT NOT NULL DEFAULT '',
    customer_email   TEXT NOT NULL DEFAULT '',
    customer_phone   TEXT NOT NULL DEFAULT '',   -- ten digits (1234567890)
    customer_ext     TEXT NOT NULL DEFAULT '',   -- a phone extension, digits only
    customer_address TEXT NOT NULL DEFAULT '',
    -- The business's details frozen onto the quote when quoted, for its
    -- printout (NULL on a draft, which prints from the business as it is
    -- now). Written as one snapshot, so the single CHECK below on the
    -- name guards the whole group.
    frozen_business_name    TEXT,
    frozen_business_address TEXT,
    frozen_business_phone   TEXT,
    frozen_business_ext     TEXT,
    frozen_business_email   TEXT,
    frozen_business_website TEXT,
    frozen_business_terms   TEXT,
    -- A quote discount is an amount or a percent, never both.
    CHECK (quote_discount_cents IS NULL OR quote_discount_percent IS NULL),
    UNIQUE (number, revision),
    -- Only a draft goes without dates and frozen totals.
    CHECK (status = 'Draft' OR (issued_on IS NOT NULL
                                AND valid_until IS NOT NULL)),
    CHECK ((status = 'Draft') = (frozen_items_cents IS NULL)),
    CHECK ((status = 'Draft') = (frozen_discount_cents IS NULL)),
    CHECK ((status = 'Draft') = (frozen_quote_discount_cents IS NULL)),
    CHECK ((status = 'Draft') = (frozen_tax_cents IS NULL)),
    CHECK ((status = 'Draft') = (frozen_total_cents IS NULL)),
    CHECK ((status = 'Draft') = (frozen_tax_name IS NULL)),
    CHECK ((status = 'Draft') = (frozen_tax_percent IS NULL)),
    CHECK ((status = 'Draft') = (frozen_business_name IS NULL))
) STRICT;

-- At most one draft per quote number: a revision is worked on one at
-- a time. (A partial index: only rows matching WHERE are indexed.)
CREATE UNIQUE INDEX IF NOT EXISTS one_draft_per_quote
    ON quotes (number) WHERE status = 'Draft';

-- Each time a quote's valid-through date was moved later, so the
-- original date and the number of extensions can be looked up.
CREATE TABLE IF NOT EXISTS quote_extensions (
    id              INTEGER PRIMARY KEY,
    quote_id        INTEGER NOT NULL
                        REFERENCES quotes (id) ON DELETE CASCADE,
    extended_on     TEXT    NOT NULL,
    old_valid_until TEXT    NOT NULL,
    new_valid_until TEXT    NOT NULL,
    CHECK (new_valid_until > old_valid_until)  -- ISO dates sort as text
) STRICT;

CREATE TABLE IF NOT EXISTS line_items (
    id               INTEGER PRIMARY KEY,
    quote_id         INTEGER NOT NULL
                         REFERENCES quotes (id) ON DELETE CASCADE,
    position         INTEGER NOT NULL,           -- order on the quote
    description      TEXT    NOT NULL,
    quantity         TEXT    NOT NULL,
    -- How the quantity reads to the customer; see units.py.
    unit             TEXT    NOT NULL DEFAULT 'each' CHECK (unit IN ('hour', 'each')),
    unit_price_cents INTEGER NOT NULL,
    discount_cents   INTEGER,
    discount_percent TEXT,
    -- 1 if taxed at the quote's rate. STRICT has no boolean type.
    taxed            INTEGER NOT NULL DEFAULT 0 CHECK (taxed IN (0, 1)),
    -- The line's figures once quoted, as for the quote's foot: all or none.
    frozen_amount_cents   INTEGER,
    frozen_discount_cents INTEGER,
    frozen_tax_cents      INTEGER,
    -- A discount is an amount or a percent, never both.
    CHECK (discount_cents IS NULL OR discount_percent IS NULL),
    CHECK ((frozen_amount_cents IS NULL) = (frozen_discount_cents IS NULL)
           AND (frozen_amount_cents IS NULL) = (frozen_tax_cents IS NULL)),
    UNIQUE (quote_id, position)
) STRICT;
