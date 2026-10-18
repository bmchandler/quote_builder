-- Run on every start; IF NOT EXISTS makes that safe. Until close to the
-- first release, change tables freely: delete the database to rebuild.
--
-- STRICT tables refuse a value of the wrong type, as SQLite otherwise
-- stores whatever it's given. Money is whole cents (INTEGER). Exact
-- decimals (quantities, percents) are TEXT, read back as Decimal; dates
-- are TEXT in ISO 8601 (2026-10-18), which also sorts correctly.

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
    UNIQUE (number, revision)
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
    -- A discount is an amount or a percent, never both.
    CHECK (discount_cents IS NULL OR discount_percent IS NULL),
    UNIQUE (quote_id, position)
) STRICT;
