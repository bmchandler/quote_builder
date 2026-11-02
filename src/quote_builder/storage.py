"""SQLite storage for quotes and businesses, with plain sqlite3.

All SQL lives here and in schema.sql; the rest of the app works with
the dataclasses in quotes.py and business.py.
"""

import sqlite3
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from importlib.resources import files
from pathlib import Path

from quote_builder.business import Business, TaxPart, TaxRate
from quote_builder.catalog import CatalogItem
from quote_builder.customers import Customer
from quote_builder.quote_numbers import new_quote_number
from quote_builder.quotes import (
    Extension,
    LineItem,
    LineTotals,
    Quote,
    QuoteSummary,
    QuoteTotals,
    SearchText,
    Status,
)
from quote_builder.totals import freeze, quote_totals

SCHEMA = files("quote_builder").joinpath("schema.sql").read_text()

# With 34 billion codes, a second clash in a row means something's wrong.
MAX_NUMBER_TRIES = 5


class NoFreeQuoteNumber(Exception):
    """Every quote number drawn was already used."""


class NotADraft(Exception):
    """The quote to change isn't a draft in the database."""


class NotExtendable(Exception):
    """The quote to extend isn't Quoted or Expired, or changed meanwhile."""


def connect(path: Path | str) -> sqlite3.Connection:
    """Open the database, creating its tables if needed."""
    # Autocommit while setting up: PRAGMA foreign_keys does nothing inside
    # a transaction. It's off by default, and only holds per connection.
    conn = sqlite3.connect(path, autocommit=True)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    # From here on, `with conn:` wraps a transaction: commit on success,
    # roll back on an exception.
    conn.autocommit = False
    conn.row_factory = sqlite3.Row
    return conn


class NameNeeded(Exception):
    """A business was left without a name while there's more than one."""


_BUSINESS_COLUMNS = "id, name, pilot, valid_days, extend_days"


def _business(row: sqlite3.Row) -> Business:
    # The columns are named as its fields; pilot is stored as 0 or 1.
    return Business(**{**dict(row), "pilot": bool(row["pilot"])})


def current_business(conn: sqlite3.Connection) -> Business:
    """The business the app shows: the one picked last, or the first
    made. One is made, with the default settings, the first time it's
    asked for."""
    with conn:
        # INSERT ... SELECT inserts a row only where the SELECT finds one;
        # a NULL id is given the next free one.
        conn.execute(
            """
            INSERT INTO businesses (id)
            SELECT NULL WHERE NOT EXISTS (SELECT 1 FROM businesses)
            """
        )
        # The picked one first (true sorts after false, hence DESC); with
        # none picked, id = NULL is NULL for every row, so the first made.
        row = conn.execute(
            f"""
            SELECT {_BUSINESS_COLUMNS}
            FROM businesses
            ORDER BY id = (SELECT business_id FROM app_state) DESC, id
            LIMIT 1
            """
        ).fetchone()
    return _business(row)


def list_businesses(conn: sqlite3.Connection) -> list[Business]:
    """Every business, then every pilot, each by name in any case."""
    rows = conn.execute(
        f"""
        SELECT {_BUSINESS_COLUMNS}
        FROM businesses
        ORDER BY pilot, name COLLATE NOCASE, id
        """
    ).fetchall()
    return [_business(row) for row in rows]


def pick_business(conn: sqlite3.Connection, business_id: int) -> None:
    """Make this the business the app shows, now and at the next start."""
    with conn:
        # An upsert: insert the one row, or change it if it's there.
        conn.execute(
            """
            INSERT INTO app_state (id, business_id) VALUES (1, ?)
            ON CONFLICT (id) DO UPDATE SET business_id = excluded.business_id
            """,
            (business_id,),
        )


def add_business(conn: sqlite3.Connection, business: Business) -> Business:
    """Store a new business; returns a copy with its id.

    Raises NameNeeded without a name: with it there's more than one.
    """
    if not business.name:
        raise NameNeeded
    with conn:
        row = conn.execute(
            """
            INSERT INTO businesses (name, pilot, valid_days, extend_days)
            VALUES (:name, :pilot, :valid_days, :extend_days)
            RETURNING id
            """,
            vars(business),
        ).fetchone()
    return replace(business, id=row["id"])


def save_business(conn: sqlite3.Connection, business: Business) -> None:
    """Save changes to a business already stored.

    Raises NameNeeded if it's left without a name while there's more
    than one.
    """
    with conn:
        # The check is in the WHERE clause, so checking and changing are
        # one step.
        row = conn.execute(
            """
            UPDATE businesses
            SET name = :name, pilot = :pilot, valid_days = :valid_days,
                extend_days = :extend_days
            WHERE id = :id
              AND (:name != '' OR (SELECT count(*) FROM businesses) = 1)
            RETURNING id
            """,
            vars(business),
        ).fetchone()
    if row is None:
        raise NameNeeded


def list_tax_rates(conn: sqlite3.Connection, business_id: int) -> list[TaxRate]:
    """A business's tax rates by name, in any case, each with its parts."""
    rows = conn.execute(
        """
        SELECT id, business_id, name, is_default
        FROM tax_rates
        WHERE business_id = ?
        ORDER BY name COLLATE NOCASE, id
        """,
        (business_id,),
    ).fetchall()
    # Every rate's parts in one query, as for line items.
    parts: dict[int, list[TaxPart]] = {}
    for part in conn.execute(
        """
        SELECT p.tax_rate_id, p.name, p.percent
        FROM tax_rate_parts AS p JOIN tax_rates AS r ON r.id = p.tax_rate_id
        WHERE r.business_id = ?
        ORDER BY p.tax_rate_id, p.position
        """,
        (business_id,),
    ):
        parts.setdefault(part["tax_rate_id"], []).append(
            TaxPart(part["name"], _decimal(part["percent"]))
        )
    return [
        TaxRate(
            business_id=row["business_id"],
            name=row["name"],
            parts=parts.get(row["id"], []),
            is_default=bool(row["is_default"]),
            id=row["id"],
        )
        for row in rows
    ]


def save_tax_rate(conn: sqlite3.Connection, rate: TaxRate) -> TaxRate:
    """Store a tax rate, new (no id) or changed, with its parts; returns
    it with its id. Made the default, it takes over from the business's
    old one."""
    values = {**vars(rate), "parts": None}  # parts go in their own table
    with conn:
        if rate.is_default:
            # First, as only one can be the default at a time.
            conn.execute(
                """
                UPDATE tax_rates SET is_default = 0
                WHERE business_id = :business_id AND id IS NOT :id
                """,
                values,
            )
        if rate.id is None:
            rate_id = conn.execute(
                """
                INSERT INTO tax_rates (business_id, name, is_default)
                VALUES (:business_id, :name, :is_default)
                RETURNING id
                """,
                values,
            ).fetchone()["id"]
        else:
            rate_id = rate.id
            conn.execute(
                "UPDATE tax_rates SET name = :name, is_default = :is_default"
                " WHERE id = :id",
                values,
            )
            # Replaced rather than matched up, as a quote's lines are.
            conn.execute("DELETE FROM tax_rate_parts WHERE tax_rate_id = ?", (rate_id,))
        conn.executemany(
            """
            INSERT INTO tax_rate_parts (tax_rate_id, position, name, percent)
            VALUES (?, ?, ?, ?)
            """,
            [
                (rate_id, position, part.name, _text(part.percent))
                for position, part in enumerate(rate.parts)
            ],
        )
    return replace(rate, id=rate_id)


class RateInUse(Exception):
    """A tax rate a draft uses can't be deleted; `drafts` says how many."""

    def __init__(self, drafts: int):
        super().__init__(f"{drafts} drafts use it")
        self.drafts = drafts


def delete_tax_rate(conn: sqlite3.Connection, rate_id: int) -> None:
    """Delete a tax rate, and its parts with it.

    Raises RateInUse while a draft uses it: the draft would lose its
    tax without a word. A quoted quote keeps its own copy of the rate.
    """
    with conn:
        # The check is in the WHERE clause, so checking and deleting are
        # one step.
        row = conn.execute(
            """
            DELETE FROM tax_rates
            WHERE id = :id
              AND NOT EXISTS (SELECT 1 FROM quotes
                              WHERE tax_rate_id = :id AND status = 'Draft')
            RETURNING id
            """,
            {"id": rate_id},
        ).fetchone()
        if row is None:
            drafts = conn.execute(
                "SELECT count(*) FROM quotes WHERE tax_rate_id = ? AND status = 'Draft'",
                (rate_id,),
            ).fetchone()[0]
            if drafts:
                raise RateInUse(drafts)


_CUSTOMER_COLUMNS = "id, business_id, name, email, phone, address"


def list_customers(conn: sqlite3.Connection, business_id: int) -> list[Customer]:
    """A business's customers by name, in any case."""
    rows = conn.execute(
        f"""
        SELECT {_CUSTOMER_COLUMNS}
        FROM customers
        WHERE business_id = ?
        ORDER BY name COLLATE NOCASE, id
        """,
        (business_id,),
    ).fetchall()
    return [Customer(**dict(row)) for row in rows]


def add_customer(conn: sqlite3.Connection, customer: Customer) -> Customer:
    """Store a new customer; returns a copy with its id."""
    with conn:
        row = conn.execute(
            """
            INSERT INTO customers (business_id, name, email, phone, address)
            VALUES (:business_id, :name, :email, :phone, :address)
            RETURNING id
            """,
            vars(customer),
        ).fetchone()
    return replace(customer, id=row["id"])


def update_customer(conn: sqlite3.Connection, customer: Customer) -> None:
    """Store a customer's changed details. Quotes keep their own copies."""
    with conn:
        conn.execute(
            """
            UPDATE customers
            SET name = :name, email = :email, phone = :phone, address = :address
            WHERE id = :id
            """,
            vars(customer),
        )


def delete_customer(conn: sqlite3.Connection, customer_id: int) -> None:
    """Delete a customer. Quotes keep their own copies."""
    with conn:
        conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))


def list_catalog_items(conn: sqlite3.Connection, business_id: int) -> list[CatalogItem]:
    """A business's catalog by description, in any case."""
    rows = conn.execute(
        """
        SELECT id, business_id, description, price_cents, unit, taxable
        FROM catalog_items
        WHERE business_id = ?
        ORDER BY description COLLATE NOCASE, id
        """,
        (business_id,),
    ).fetchall()
    return [
        CatalogItem(**(dict(row) | {"taxable": bool(row["taxable"])})) for row in rows
    ]


def save_catalog_item(conn: sqlite3.Connection, item: CatalogItem) -> CatalogItem:
    """Store a catalog item, new or changed; returns a copy with its id."""
    with conn:
        if item.id is not None:
            conn.execute(
                """
                UPDATE catalog_items
                SET description = :description, price_cents = :price_cents,
                    unit = :unit, taxable = :taxable
                WHERE id = :id
                """,
                vars(item),
            )
            return item
        row = conn.execute(
            """
            INSERT INTO catalog_items
                (business_id, description, price_cents, unit, taxable)
            VALUES (:business_id, :description, :price_cents, :unit, :taxable)
            RETURNING id
            """,
            vars(item),
        ).fetchone()
    return replace(item, id=row["id"])


def delete_catalog_item(conn: sqlite3.Connection, item_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM catalog_items WHERE id = ?", (item_id,))


def save_new_quote(
    conn: sqlite3.Connection,
    quote: Quote,
    draw_number: Callable[[], str] = new_quote_number,
    now: datetime | None = None,
) -> Quote:
    """Save a quote not yet in the database, giving it a new number.

    Returns a copy with the number; `quote` itself is left as it was.
    The quote and its line items are saved together or not at all.
    `now` (the time saved; the current time if None) is for tests.
    """
    updated_at = _timestamp(now)
    with conn:
        for _ in range(MAX_NUMBER_TRIES):
            number = draw_number()
            # On a clash, DO NOTHING inserts no row, so RETURNING gives
            # none: no exception to catch, and the transaction goes on.
            row = conn.execute(
                f"""
                INSERT INTO quotes ({_QUOTE_COLUMNS})
                VALUES ({_QUOTE_VALUES})
                ON CONFLICT (number, revision) DO NOTHING
                RETURNING id
                """,
                _quote_values(quote, number, updated_at),
            ).fetchone()
            if row is not None:
                break
        else:
            raise NoFreeQuoteNumber(f"{MAX_NUMBER_TRIES} numbers drawn, all used")
        _insert_line_items(conn, row["id"], quote.line_items)
    return replace(quote, number=number)


def save_draft(
    conn: sqlite3.Connection, quote: Quote, now: datetime | None = None
) -> None:
    """Save changes to a draft already in the database.

    Raises NotADraft if no draft has the quote's number and revision: once
    quoted, a quote changes only by a new revision. `now` as for
    save_new_quote.
    """
    with conn:
        _overwrite_draft(conn, quote, now)


def save_revision(
    conn: sqlite3.Connection, quote: Quote, now: datetime | None = None
) -> None:
    """Save a new revision draft (from quotes.revision_draft) for the
    first time.

    Raises sqlite3.IntegrityError if that revision is already saved, or
    the quote already has a draft. `now` as for save_new_quote.
    """
    with conn:
        _insert_revision(conn, quote, now)


def mark_quoted(
    conn: sqlite3.Connection,
    quote: Quote,
    issued_on: date,
    valid_until: date,
    draw_number: Callable[[], str] = new_quote_number,
    now: datetime | None = None,
    new_revision: bool = False,
) -> Quote:
    """Save a draft, new or saved, as Quoted, with its figures frozen.

    `new_revision` is True for a revision draft not saved yet. Once a
    revision is quoted, the versions before it are Superseded. Returns
    the quoted copy (with its number, if new). It's all saved together
    or not at all. Raises NotADraft as save_draft does, and
    IntegrityError as save_revision does; `draw_number` and `now` as for
    save_new_quote.
    """
    # The tax rate as it is now is the one frozen, whatever the quote was
    # shown with.
    taxed = _with_rate(quote, _rates_now(conn, [quote.tax_rate_id]))
    quoted = freeze(
        replace(
            taxed, status=Status.QUOTED, issued_on=issued_on, valid_until=valid_until
        )
    )
    if quoted.number is None:
        return save_new_quote(conn, quoted, draw_number, now)
    with conn:
        if new_revision:
            _insert_revision(conn, quoted, now)
        else:
            _overwrite_draft(conn, quoted, now)
        conn.execute(
            """
            UPDATE quotes SET status = 'Superseded'
            WHERE number = ? AND revision < ?
              AND status IN ('Quoted', 'Expired')
            """,
            (quoted.number, quoted.revision),
        )
    return quoted


def _insert_revision(
    conn: sqlite3.Connection, quote: Quote, now: datetime | None
) -> None:
    """Insert a revision not yet saved, inside the caller's transaction."""
    row = conn.execute(
        f"""
        INSERT INTO quotes ({_QUOTE_COLUMNS})
        VALUES ({_QUOTE_VALUES})
        RETURNING id
        """,
        _quote_values(quote, quote.number, _timestamp(now)),
    ).fetchone()
    _insert_line_items(conn, row["id"], quote.line_items)


def _overwrite_draft(
    conn: sqlite3.Connection, quote: Quote, now: datetime | None
) -> None:
    """Write `quote` over its saved draft, inside the caller's transaction."""
    # The status check is in the WHERE clause, so checking and changing
    # are one step: no window for the status to change in between.
    row = conn.execute(
        """
        UPDATE quotes
        SET status = :status, issued_on = :issued_on,
            valid_until = :valid_until, notes = :notes,
            tax_rate_id = :tax_rate_id, updated_at = :updated_at,
            frozen_items_cents = :items_cents,
            frozen_discount_cents = :discount_cents,
            frozen_tax_cents = :tax_cents, frozen_total_cents = :total_cents,
            frozen_tax_name = :tax_name, frozen_tax_percent = :tax_percent,
            customer_name = :customer_name,
            customer_email = :customer_email,
            customer_phone = :customer_phone,
            customer_address = :customer_address
        WHERE number = :number AND revision = :revision AND status = 'Draft'
        RETURNING id
        """,
        _quote_values(quote, quote.number, _timestamp(now)),
    ).fetchone()
    if row is None:
        raise NotADraft(f"{quote.number} isn't a draft")
    # Replace the lines rather than matching old to new: simpler, and
    # nothing refers to a line's id.
    conn.execute("DELETE FROM line_items WHERE quote_id = ?", (row["id"],))
    _insert_line_items(conn, row["id"], quote.line_items)


def expire_overdue(conn: sqlite3.Connection, today: date) -> None:
    """Mark Expired every Quoted quote whose valid-through date is past.

    Valid through is inclusive: a quote valid through today is still
    good today. The time last saved is left alone, as nothing was saved.
    """
    with conn:
        conn.execute(
            """
            UPDATE quotes SET status = 'Expired'
            WHERE status = 'Quoted' AND valid_until < ?
            """,
            (_iso(today),),
        )


def extend_quote(
    conn: sqlite3.Connection,
    quote: Quote,
    new_valid_until: date,
    today: date,
    now: datetime | None = None,
) -> Quote:
    """Move a Quoted or Expired quote's valid-through date later.

    It's Quoted again afterwards, and the change is logged. Returns the
    updated copy. Raises ValueError, with a message for the user, if the
    new date isn't later than the old one or is already past; and
    NotExtendable if the quote isn't Quoted or Expired in the database,
    or its date changed since it was loaded. `now` as for save_new_quote.
    """
    old_valid_until = quote.valid_until
    if old_valid_until is None or new_valid_until <= old_valid_until:
        raise ValueError("The new date must be later than the current one")
    if new_valid_until < today:
        raise ValueError("The new date can't be in the past")
    with conn:
        # As in save_draft, the checks are in the WHERE clause, so checking
        # and changing are one step.
        row = conn.execute(
            """
            UPDATE quotes
            SET status = 'Quoted', valid_until = ?, updated_at = ?
            WHERE number = ? AND revision = ?
              AND status IN ('Quoted', 'Expired') AND valid_until = ?
            RETURNING id
            """,
            (
                _iso(new_valid_until),
                _timestamp(now),
                quote.number,
                quote.revision,
                _iso(old_valid_until),
            ),
        ).fetchone()
        if row is None:
            raise NotExtendable(f"{quote.number} can't be extended")
        extension = Extension(today, old_valid_until, new_valid_until)
        conn.execute(
            """
            INSERT INTO quote_extensions
                (quote_id, extended_on, old_valid_until, new_valid_until)
            VALUES (?, ?, ?, ?)
            """,
            (
                row["id"],
                _iso(extension.extended_on),
                _iso(extension.old_valid_until),
                _iso(extension.new_valid_until),
            ),
        )
    return replace(
        quote,
        status=Status.QUOTED,
        valid_until=new_valid_until,
        extensions=[*quote.extensions, extension],
    )


# A new quote's columns, and the names in _quote_values they're given,
# in the same order: for the two INSERTs.
_QUOTE_COLUMNS = """
    business_id, number, revision, status, issued_on, valid_until, notes,
    tax_rate_id, updated_at, frozen_items_cents, frozen_discount_cents,
    frozen_tax_cents, frozen_total_cents, frozen_tax_name, frozen_tax_percent,
    customer_name, customer_email, customer_phone, customer_address
"""
_QUOTE_VALUES = """
    :business_id, :number, :revision, :status, :issued_on, :valid_until,
    :notes, :tax_rate_id, :updated_at, :items_cents, :discount_cents,
    :tax_cents, :total_cents, :tax_name, :tax_percent,
    :customer_name, :customer_email, :customer_phone, :customer_address
"""


def _quote_values(quote: Quote, number: str | None, updated_at: str) -> dict:
    """The quote's columns, by name, for INSERT and UPDATE."""
    frozen = quote.frozen
    customer = quote.customer
    return {
        "business_id": quote.business_id,
        "number": number,
        "revision": quote.revision,
        "status": quote.status,
        "issued_on": _iso(quote.issued_on),
        "valid_until": _iso(quote.valid_until),
        "notes": quote.notes,
        "tax_rate_id": quote.tax_rate_id,
        "updated_at": updated_at,
        "items_cents": frozen.items_cents if frozen else None,
        "discount_cents": frozen.discount_cents if frozen else None,
        "tax_cents": frozen.tax_cents if frozen else None,
        "total_cents": frozen.total_cents if frozen else None,
        # The rate's name and percent are kept only once quoted: a
        # draft's follow the rate as it is now.
        "tax_name": quote.tax_name if frozen else None,
        "tax_percent": str(quote.tax_percent) if frozen else None,
        "customer_name": customer.name if customer else "",
        "customer_email": customer.email if customer else "",
        "customer_phone": customer.phone if customer else "",
        "customer_address": customer.address if customer else "",
    }


def _rates_now(conn: sqlite3.Connection, rate_ids: list[int]) -> dict[int, TaxRate]:
    """These tax rates as they are now, by id: what a draft is taxed at.

    Their percents are added up here, as Decimal: SQLite's sum() would
    go through floating point.
    """
    ids = sorted({rate_id for rate_id in rate_ids if rate_id is not None})
    if not ids:
        return {}
    placeholders = ", ".join("?" * len(ids))
    rates: dict[int, TaxRate] = {}
    for row in conn.execute(
        f"""
        SELECT r.id, r.business_id, r.name, r.is_default,
               p.name AS part_name, p.percent
        FROM tax_rates AS r JOIN tax_rate_parts AS p ON p.tax_rate_id = r.id
        WHERE r.id IN ({placeholders})
        ORDER BY r.id, p.position
        """,
        ids,
    ):
        rate = rates.setdefault(
            row["id"],
            TaxRate(
                row["business_id"],
                row["name"],
                is_default=bool(row["is_default"]),
                id=row["id"],
            ),
        )
        rate.parts.append(TaxPart(row["part_name"], _decimal(row["percent"])))
    return rates


def _with_rate(quote: Quote, rates: dict[int, TaxRate]) -> Quote:
    """A draft with its rate's name and percent as they are now; Untaxed
    if it has none."""
    rate = rates.get(quote.tax_rate_id)
    if rate is None:
        return replace(quote, tax_rate_id=None, tax_name="", tax_percent=Decimal(0))
    return replace(quote, tax_name=rate.name, tax_percent=rate.percent)


def list_quotes(
    conn: sqlite3.Connection, business_id: int, search: str = ""
) -> list[QuoteSummary]:
    """Each of a business's quotes' newest version, last changed first,
    matching `search` if given.

    A quote matches if any version's number, notes, line description,
    or customer's details (name, email, phone, address) hold the search
    text, in any case.
    """
    # In LIKE, % and _ are wildcards: escape them (and the escape
    # character itself) so they match only themselves.
    escaped = (
        search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    pattern = f"%{escaped}%"
    # q is the newest version; v runs over every version of its number.
    rows = conn.execute(
        rf"""
        SELECT {_SUMMARY_COLUMNS}
        FROM quotes AS q
        WHERE q.business_id = :business_id
          AND q.revision = (SELECT max(revision) FROM quotes
                            WHERE number = q.number)
          AND EXISTS (
              SELECT 1 FROM quotes AS v
              WHERE v.number = q.number
                AND (v.number LIKE :pattern ESCAPE '\'
                     OR v.notes LIKE :pattern ESCAPE '\'
                     OR EXISTS (SELECT 1 FROM line_items
                                WHERE quote_id = v.id
                                  AND description LIKE :pattern ESCAPE '\')
                     OR v.customer_name LIKE :pattern ESCAPE '\'
                     OR v.customer_email LIKE :pattern ESCAPE '\'
                     OR v.customer_phone LIKE :pattern ESCAPE '\'
                     OR v.customer_address LIKE :pattern ESCAPE '\'))
        ORDER BY q.updated_at DESC, q.id DESC
        """,
        {"business_id": business_id, "pattern": pattern},
    ).fetchall()
    return _summaries(conn, rows)


def list_versions(conn: sqlite3.Connection, number: str) -> list[QuoteSummary]:
    """Every version of a quote, newest first."""
    rows = conn.execute(
        f"""
        SELECT {_SUMMARY_COLUMNS}
        FROM quotes AS q
        WHERE q.number = ?
        ORDER BY q.revision DESC
        """,
        (number,),
    ).fetchall()
    return _summaries(conn, rows)


# A customer's details search looks in, in order: column names, from our
# own code, never the user's.
CUSTOMER_DETAILS = ("name", "email", "phone", "address")


def search_texts(
    conn: sqlite3.Connection, numbers: list[str]
) -> dict[str, list[SearchText]]:
    """The customer details, line descriptions, and notes of every
    version of these quotes, by number: newest version first; in each,
    the customer's name, email, phone, and address, the lines in
    order, then the notes.

    One query for all the quotes, as for line items.
    """
    if not numbers:
        return {}
    placeholders = ", ".join("?" * len(numbers))
    # One row per customer detail, numbered in the order above.
    details = " UNION ALL ".join(
        f"""
        SELECT q.number AS number, q.revision AS revision,
               'customer' AS field, {position} AS position,
               q.customer_{column} AS text
        FROM quotes AS q
        WHERE q.number IN ({placeholders}) AND q.customer_{column} != ''
        """
        for position, column in enumerate(CUSTOMER_DETAILS)
    )
    # 'customer' sorts before 'line', and that before 'notes'.
    rows = conn.execute(
        f"""
        {details}
        UNION ALL
        SELECT q.number, q.revision, 'line' AS field, li.position,
               li.description AS text
        FROM quotes AS q JOIN line_items AS li ON li.quote_id = q.id
        WHERE q.number IN ({placeholders})
        UNION ALL
        SELECT number, revision, 'notes', 0, notes
        FROM quotes
        WHERE number IN ({placeholders}) AND notes != ''
        ORDER BY 1, 2 DESC, 3, 4
        """,
        numbers * (len(CUSTOMER_DETAILS) + 2),
    ).fetchall()
    texts: dict[str, list[SearchText]] = {}
    for row in rows:
        texts.setdefault(row["number"], []).append(
            SearchText(row["revision"], row["field"], row["position"], row["text"])
        )
    return texts


_SUMMARY_COLUMNS = """
    q.id, q.number, q.revision, q.status, q.updated_at, q.issued_on,
    q.valid_until, q.frozen_total_cents, q.tax_rate_id,
    nullif(q.customer_name, '') AS customer_name
"""


def _summaries(
    conn: sqlite3.Connection, rows: list[sqlite3.Row]
) -> list[QuoteSummary]:
    lines = _line_items_of(conn, [row["id"] for row in rows])
    rates = _rates_now(conn, [row["tax_rate_id"] for row in rows])
    summaries = []
    for row in rows:
        items = lines.get(row["id"], [])
        rate = rates.get(row["tax_rate_id"])
        tax_percent = rate.percent if rate else Decimal(0)
        summaries.append(
            QuoteSummary(
                number=row["number"],
                revision=row["revision"],
                status=Status(row["status"]),
                first_line=items[0].description if items else None,
                updated_at=datetime.fromisoformat(row["updated_at"]),
                total_cents=(
                    row["frozen_total_cents"]
                    if row["frozen_total_cents"] is not None
                    else quote_totals(items, tax_percent).total_cents
                ),
                issued_on=_date(row["issued_on"]),
                valid_until=_date(row["valid_until"]),
                customer_name=row["customer_name"],  # None without one
            )
        )
    return summaries


def _line_items_of(
    conn: sqlite3.Connection, quote_ids: list[int]
) -> dict[int, list[LineItem]]:
    """Each quote's line items, in order, by quote id.

    One query for all the quotes, rather than one per quote (the "N+1
    queries" problem).
    """
    if not quote_ids:
        return {}
    # A placeholder per id: values never go into the SQL text itself.
    placeholders = ", ".join("?" * len(quote_ids))
    rows = conn.execute(
        f"""
        SELECT quote_id, description, quantity, unit_price_cents, taxed,
               discount_cents, discount_percent, frozen_amount_cents,
               frozen_discount_cents, frozen_tax_cents
        FROM line_items
        WHERE quote_id IN ({placeholders})
        ORDER BY quote_id, position
        """,
        quote_ids,
    ).fetchall()
    lines: dict[int, list[LineItem]] = {}
    for row in rows:
        lines.setdefault(row["quote_id"], []).append(_line_item(row))
    return lines


def load_quote(
    conn: sqlite3.Connection, number: str, revision: int | None = None
) -> Quote | None:
    """The quote with this number and revision (its newest version if
    None), or None if there's none."""
    row = conn.execute(
        """
        SELECT id, business_id, number, revision, status, issued_on,
               valid_until, notes, tax_rate_id, frozen_items_cents,
               frozen_discount_cents, frozen_tax_cents, frozen_total_cents,
               frozen_tax_name, frozen_tax_percent, customer_name,
               customer_email, customer_phone, customer_address
        FROM quotes
        WHERE number = :number
          AND (:revision IS NULL OR revision = :revision)
        ORDER BY revision DESC
        LIMIT 1
        """,
        {"number": number, "revision": revision},
    ).fetchone()
    if row is None:
        return None
    customer = Customer(
        business_id=row["business_id"],
        name=row["customer_name"],
        email=row["customer_email"],
        phone=row["customer_phone"],
        address=row["customer_address"],
    )
    quote = Quote(
        business_id=row["business_id"],
        number=row["number"],
        revision=row["revision"],
        status=Status(row["status"]),
        issued_on=_date(row["issued_on"]),
        valid_until=_date(row["valid_until"]),
        notes=row["notes"],
        line_items=_line_items_of(conn, [row["id"]]).get(row["id"], []),
        tax_rate_id=row["tax_rate_id"],
        frozen=(
            None
            if row["frozen_total_cents"] is None
            else QuoteTotals(
                items_cents=row["frozen_items_cents"],
                discount_cents=row["frozen_discount_cents"],
                tax_cents=row["frozen_tax_cents"],
                total_cents=row["frozen_total_cents"],
            )
        ),
        extensions=_extensions_of(conn, row["id"]),
        customer=None if customer.is_blank else customer,
    )
    if row["frozen_tax_percent"] is None:
        # A draft: the rate as it is now.
        return _with_rate(quote, _rates_now(conn, [quote.tax_rate_id]))
    return replace(
        quote,
        tax_name=row["frozen_tax_name"],
        tax_percent=Decimal(row["frozen_tax_percent"]),
    )


def _extensions_of(conn: sqlite3.Connection, quote_id: int) -> list[Extension]:
    rows = conn.execute(
        """
        SELECT extended_on, old_valid_until, new_valid_until
        FROM quote_extensions
        WHERE quote_id = ?
        ORDER BY id
        """,
        (quote_id,),
    ).fetchall()
    return [
        Extension(
            extended_on=date.fromisoformat(row["extended_on"]),
            old_valid_until=date.fromisoformat(row["old_valid_until"]),
            new_valid_until=date.fromisoformat(row["new_valid_until"]),
        )
        for row in rows
    ]


def _insert_line_items(
    conn: sqlite3.Connection, quote_id: int, line_items: list[LineItem]
) -> None:
    conn.executemany(
        """
        INSERT INTO line_items
            (quote_id, position, description, quantity, unit_price_cents,
             taxed, discount_cents, discount_percent,
             frozen_amount_cents, frozen_discount_cents, frozen_tax_cents)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                quote_id,
                position,
                item.description,
                str(item.quantity),
                item.unit_price_cents,
                item.taxed,
                item.discount_cents,
                _text(item.discount_percent),
                item.frozen.amount_cents if item.frozen else None,
                item.frozen.discount_cents if item.frozen else None,
                item.frozen.tax_cents if item.frozen else None,
            )
            for position, item in enumerate(line_items)
        ],
    )


def _line_item(row: sqlite3.Row) -> LineItem:
    return LineItem(
        description=row["description"],
        quantity=Decimal(row["quantity"]),
        unit_price_cents=row["unit_price_cents"],
        taxed=bool(row["taxed"]),
        discount_cents=row["discount_cents"],
        discount_percent=_decimal(row["discount_percent"]),
        frozen=(
            None
            if row["frozen_amount_cents"] is None
            else LineTotals(
                amount_cents=row["frozen_amount_cents"],
                discount_cents=row["frozen_discount_cents"],
                tax_cents=row["frozen_tax_cents"],
            )
        ),
    )


# Conversions done by hand rather than with sqlite3.register_adapter,
# which would change every connection in the process.


def _timestamp(now: datetime | None) -> str:
    """`now` (the current time if None) in UTC, as ISO 8601 text.

    Always to the second and in UTC, so every value has the same shape
    and sorting the text sorts by time. (Plain isoformat() adds a
    fraction only when there is one, which would break that.)
    """
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    return moment.isoformat(timespec="seconds")


def _iso(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _date(value: str | None) -> date | None:
    return None if value is None else date.fromisoformat(value)


def _text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _decimal(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)
