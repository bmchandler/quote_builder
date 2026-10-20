-- Run on every start; IF NOT EXISTS makes that safe. Until close to the
-- first release, change tables freely: delete the database to rebuild.
--
-- STRICT tables refuse a value of the wrong type, as SQLite otherwise
-- stores whatever it's given. Money is whole cents (INTEGER). Exact
-- decimals (quantities, percents) are TEXT, read back as Decimal; dates
-- are TEXT in ISO 8601 (2026-10-18), which also sorts correctly.

-- A business the user quotes for, and its settings. One so far; the
-- table is shaped for several, as the plan has them.
CREATE TABLE IF NOT EXISTS businesses (
    id         INTEGER PRIMARY KEY,
    -- Days from issue to a new quote's valid-through date.
    valid_days INTEGER NOT NULL DEFAULT 30 CHECK (valid_days > 0)
) STRICT;

CREATE TABLE IF NOT EXISTS quotes (
    id          INTEGER PRIMARY KEY,
    number      TEXT    NOT NULL,                -- Q-7KQ-M9XD
    revision    INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    status      TEXT    NOT NULL DEFAULT 'Draft' CHECK (status IN
                    ('Draft', 'Quoted', 'Accepted', 'Declined', 'Expired',
                     'Superseded')),
    issued_on   TEXT,
    valid_until TEXT,
    notes       TEXT    NOT NULL DEFAULT '',
    -- When last saved: UTC, ISO 8601 with the offset, shown in local time.
    updated_at  TEXT    NOT NULL,
    -- The foot's totals, stored once quoted (frozen) and shown from then
    -- on; a draft's are worked out from its lines whenever shown.
    frozen_items_cents    INTEGER,
    frozen_discount_cents INTEGER,
    frozen_tax_cents      INTEGER,
    frozen_total_cents    INTEGER,
    UNIQUE (number, revision),
    -- Only a draft goes without dates and frozen totals.
    CHECK (status = 'Draft' OR (issued_on IS NOT NULL
                                AND valid_until IS NOT NULL)),
    CHECK ((status = 'Draft') = (frozen_items_cents IS NULL)),
    CHECK ((status = 'Draft') = (frozen_discount_cents IS NULL)),
    CHECK ((status = 'Draft') = (frozen_tax_cents IS NULL)),
    CHECK ((status = 'Draft') = (frozen_total_cents IS NULL))
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
    unit_price_cents INTEGER NOT NULL,
    discount_cents   INTEGER,
    discount_percent TEXT,
    tax_percent      TEXT    NOT NULL DEFAULT '0',
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
