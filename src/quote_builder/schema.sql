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
    extend_days INTEGER CHECK (extend_days > 0)
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

-- A business's customers, kept for the next job.
CREATE TABLE IF NOT EXISTS customers (
    id          INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses (id),
    name        TEXT    NOT NULL CHECK (name != ''),
    email       TEXT    NOT NULL DEFAULT '',
    phone       TEXT    NOT NULL DEFAULT '',
    address     TEXT    NOT NULL DEFAULT '',  -- as typed, line breaks and all
    -- For quotes' foreign key below, which needs a unique key to point at.
    UNIQUE (business_id, id)
) STRICT;

-- A business's services and parts. A line copies what it needs, so nothing
-- points here and an item can always be changed or deleted.
CREATE TABLE IF NOT EXISTS catalog_items (
    id          INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses (id),
    description TEXT    NOT NULL CHECK (description != ''),
    price_cents INTEGER CHECK (price_cents >= 0),  -- NULL: priced job by job
    unit        TEXT    NOT NULL DEFAULT '',
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
    -- Its customer, if any. A quoted quote keeps it too, so a customer
    -- with quotes can't be deleted (no ON DELETE: the database refuses).
    customer_id INTEGER,
    -- When last saved: UTC, ISO 8601 with the offset, shown in local time.
    updated_at  TEXT    NOT NULL,
    -- The foot's totals, stored once quoted (frozen) and shown from then
    -- on; a draft's are worked out from its lines whenever shown.
    frozen_items_cents    INTEGER,
    frozen_discount_cents INTEGER,
    frozen_tax_cents      INTEGER,
    frozen_total_cents    INTEGER,
    -- The rate as it was when quoted ('' and '0' for Untaxed).
    frozen_tax_name       TEXT,
    frozen_tax_percent    TEXT,
    -- The customer's details as they were when quoted ('' for none), so
    -- fixing them later changes only drafts and later quotes.
    frozen_customer_name    TEXT,
    frozen_customer_email   TEXT,
    frozen_customer_phone   TEXT,
    frozen_customer_address TEXT,
    UNIQUE (number, revision),
    -- Both columns: a quote's customer is one of its own business's. (A
    -- NULL customer_id skips the check.)
    FOREIGN KEY (business_id, customer_id)
        REFERENCES customers (business_id, id),
    -- Only a draft goes without dates and frozen totals.
    CHECK (status = 'Draft' OR (issued_on IS NOT NULL
                                AND valid_until IS NOT NULL)),
    CHECK ((status = 'Draft') = (frozen_items_cents IS NULL)),
    CHECK ((status = 'Draft') = (frozen_discount_cents IS NULL)),
    CHECK ((status = 'Draft') = (frozen_tax_cents IS NULL)),
    CHECK ((status = 'Draft') = (frozen_total_cents IS NULL)),
    CHECK ((status = 'Draft') = (frozen_tax_name IS NULL)),
    CHECK ((status = 'Draft') = (frozen_tax_percent IS NULL)),
    CHECK ((status = 'Draft') = (frozen_customer_name IS NULL)),
    CHECK ((status = 'Draft') = (frozen_customer_email IS NULL)),
    CHECK ((status = 'Draft') = (frozen_customer_phone IS NULL)),
    CHECK ((status = 'Draft') = (frozen_customer_address IS NULL))
) STRICT;

-- Each quote's customer details as it shows them: a quoted one's as
-- kept, a draft's as they are now. Only quotes with a customer. (A
-- view is a stored SELECT, used like a table; to change one, drop it
-- first, as IF NOT EXISTS leaves an old one be.)
CREATE VIEW IF NOT EXISTS quote_customers AS
    SELECT q.id AS quote_id,
           coalesce(q.frozen_customer_name, c.name) AS name,
           coalesce(q.frozen_customer_email, c.email) AS email,
           coalesce(q.frozen_customer_phone, c.phone) AS phone,
           coalesce(q.frozen_customer_address, c.address) AS address
    FROM quotes AS q JOIN customers AS c ON c.id = q.customer_id;

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
