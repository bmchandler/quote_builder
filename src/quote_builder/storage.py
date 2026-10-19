"""SQLite storage for quotes, with plain sqlite3.

All SQL lives here and in schema.sql; the rest of the app works with
the dataclasses in quotes.py.
"""

import sqlite3
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from importlib.resources import files
from pathlib import Path

from quote_builder.quote_numbers import new_quote_number
from quote_builder.quotes import LineItem, Quote, QuoteSummary, Status
from quote_builder.totals import quote_totals

SCHEMA = files("quote_builder").joinpath("schema.sql").read_text()

# With 34 billion codes, a second clash in a row means something's wrong.
MAX_NUMBER_TRIES = 5


class NoFreeQuoteNumber(Exception):
    """Every quote number drawn was already used."""


class NotADraft(Exception):
    """The quote to change isn't a draft in the database."""


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
                """
                INSERT INTO quotes
                    (number, revision, status, issued_on, valid_until, notes,
                     updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (number, revision) DO NOTHING
                RETURNING id
                """,
                (
                    number,
                    quote.revision,
                    quote.status,
                    _iso(quote.issued_on),
                    _iso(quote.valid_until),
                    quote.notes,
                    updated_at,
                ),
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
        # The status check is in the WHERE clause, so checking and changing
        # are one step: no window for the status to change in between.
        row = conn.execute(
            """
            UPDATE quotes
            SET issued_on = ?, valid_until = ?, notes = ?, updated_at = ?
            WHERE number = ? AND revision = ? AND status = 'Draft'
            RETURNING id
            """,
            (
                _iso(quote.issued_on),
                _iso(quote.valid_until),
                quote.notes,
                _timestamp(now),
                quote.number,
                quote.revision,
            ),
        ).fetchone()
        if row is None:
            raise NotADraft(f"{quote.number} isn't a draft")
        # Replace the lines rather than matching old to new: simpler, and
        # nothing refers to a line's id.
        conn.execute("DELETE FROM line_items WHERE quote_id = ?", (row["id"],))
        _insert_line_items(conn, row["id"], quote.line_items)


def list_quotes(conn: sqlite3.Connection, search: str = "") -> list[QuoteSummary]:
    """Quotes, last changed first, matching `search` if given.

    A quote matches if its number, its notes, or any line's description
    holds the search text, in any case.
    """
    # In LIKE, % and _ are wildcards: escape them (and the escape
    # character itself) so they match only themselves.
    escaped = (
        search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    pattern = f"%{escaped}%"
    rows = conn.execute(
        r"""
        SELECT id, number, revision, status, updated_at
        FROM quotes
        WHERE number LIKE :pattern ESCAPE '\'
           OR notes LIKE :pattern ESCAPE '\'
           OR EXISTS (SELECT 1 FROM line_items
                      WHERE quote_id = quotes.id
                        AND description LIKE :pattern ESCAPE '\')
        ORDER BY updated_at DESC, id DESC
        """,
        {"pattern": pattern},
    ).fetchall()
    lines = _line_items_of(conn, [row["id"] for row in rows])
    summaries = []
    for row in rows:
        items = lines.get(row["id"], [])
        summaries.append(
            QuoteSummary(
                number=row["number"],
                revision=row["revision"],
                status=Status(row["status"]),
                first_line=items[0].description if items else None,
                updated_at=datetime.fromisoformat(row["updated_at"]),
                total_cents=quote_totals(items).total_cents,
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
        SELECT quote_id, description, quantity, unit_price_cents, tax_percent,
               discount_cents, discount_percent
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
    conn: sqlite3.Connection, number: str, revision: int = 0
) -> Quote | None:
    """The quote with this number and revision, or None if there's none."""
    row = conn.execute(
        """
        SELECT id, number, revision, status, issued_on, valid_until, notes
        FROM quotes
        WHERE number = ? AND revision = ?
        """,
        (number, revision),
    ).fetchone()
    if row is None:
        return None
    return Quote(
        number=row["number"],
        revision=row["revision"],
        status=Status(row["status"]),
        issued_on=_date(row["issued_on"]),
        valid_until=_date(row["valid_until"]),
        notes=row["notes"],
        line_items=_line_items_of(conn, [row["id"]]).get(row["id"], []),
    )


def _insert_line_items(
    conn: sqlite3.Connection, quote_id: int, line_items: list[LineItem]
) -> None:
    conn.executemany(
        """
        INSERT INTO line_items
            (quote_id, position, description, quantity, unit_price_cents,
             tax_percent, discount_cents, discount_percent)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                quote_id,
                position,
                item.description,
                str(item.quantity),
                item.unit_price_cents,
                str(item.tax_percent),
                item.discount_cents,
                _text(item.discount_percent),
            )
            for position, item in enumerate(line_items)
        ],
    )


def _line_item(row: sqlite3.Row) -> LineItem:
    return LineItem(
        description=row["description"],
        quantity=Decimal(row["quantity"]),
        unit_price_cents=row["unit_price_cents"],
        tax_percent=Decimal(row["tax_percent"]),
        discount_cents=row["discount_cents"],
        discount_percent=_decimal(row["discount_percent"]),
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
