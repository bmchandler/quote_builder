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
from quote_builder.quotes import (
    Extension,
    LineItem,
    LineTotals,
    Quote,
    QuoteSummary,
    QuoteTotals,
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
                     updated_at, frozen_items_cents, frozen_discount_cents,
                     frozen_tax_cents, frozen_total_cents)
                VALUES (:number, :revision, :status, :issued_on, :valid_until,
                        :notes, :updated_at, :items_cents, :discount_cents,
                        :tax_cents, :total_cents)
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
    quoted = freeze(
        replace(
            quote, status=Status.QUOTED, issued_on=issued_on, valid_until=valid_until
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
              AND status IN ('Quoted', 'Declined', 'Expired')
            """,
            (quoted.number, quoted.revision),
        )
    return quoted


def _insert_revision(
    conn: sqlite3.Connection, quote: Quote, now: datetime | None
) -> None:
    """Insert a revision not yet saved, inside the caller's transaction."""
    row = conn.execute(
        """
        INSERT INTO quotes
            (number, revision, status, issued_on, valid_until, notes,
             updated_at, frozen_items_cents, frozen_discount_cents,
             frozen_tax_cents, frozen_total_cents)
        VALUES (:number, :revision, :status, :issued_on, :valid_until,
                :notes, :updated_at, :items_cents, :discount_cents,
                :tax_cents, :total_cents)
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
            updated_at = :updated_at, frozen_items_cents = :items_cents,
            frozen_discount_cents = :discount_cents,
            frozen_tax_cents = :tax_cents, frozen_total_cents = :total_cents
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


def _quote_values(quote: Quote, number: str | None, updated_at: str) -> dict:
    """The quote's columns, by name, for INSERT and UPDATE."""
    frozen = quote.frozen
    return {
        "number": number,
        "revision": quote.revision,
        "status": quote.status,
        "issued_on": _iso(quote.issued_on),
        "valid_until": _iso(quote.valid_until),
        "notes": quote.notes,
        "updated_at": updated_at,
        "items_cents": frozen.items_cents if frozen else None,
        "discount_cents": frozen.discount_cents if frozen else None,
        "tax_cents": frozen.tax_cents if frozen else None,
        "total_cents": frozen.total_cents if frozen else None,
    }


def list_quotes(conn: sqlite3.Connection, search: str = "") -> list[QuoteSummary]:
    """Each quote's newest version, last changed first, matching `search`
    if given.

    A quote matches if any version's number, notes, or line description
    holds the search text, in any case.
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
        WHERE q.revision = (SELECT max(revision) FROM quotes
                            WHERE number = q.number)
          AND EXISTS (
              SELECT 1 FROM quotes AS v
              WHERE v.number = q.number
                AND (v.number LIKE :pattern ESCAPE '\'
                     OR v.notes LIKE :pattern ESCAPE '\'
                     OR EXISTS (SELECT 1 FROM line_items
                                WHERE quote_id = v.id
                                  AND description LIKE :pattern ESCAPE '\')))
        ORDER BY q.updated_at DESC, q.id DESC
        """,
        {"pattern": pattern},
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


_SUMMARY_COLUMNS = """
    q.id, q.number, q.revision, q.status, q.updated_at, q.issued_on,
    q.valid_until, q.frozen_total_cents
"""


def _summaries(
    conn: sqlite3.Connection, rows: list[sqlite3.Row]
) -> list[QuoteSummary]:
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
                total_cents=(
                    row["frozen_total_cents"]
                    if row["frozen_total_cents"] is not None
                    else quote_totals(items).total_cents
                ),
                issued_on=_date(row["issued_on"]),
                valid_until=_date(row["valid_until"]),
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
        SELECT id, number, revision, status, issued_on, valid_until, notes,
               frozen_items_cents, frozen_discount_cents, frozen_tax_cents,
               frozen_total_cents
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
    return Quote(
        number=row["number"],
        revision=row["revision"],
        status=Status(row["status"]),
        issued_on=_date(row["issued_on"]),
        valid_until=_date(row["valid_until"]),
        notes=row["notes"],
        line_items=_line_items_of(conn, [row["id"]]).get(row["id"], []),
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
             tax_percent, discount_cents, discount_percent,
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
                str(item.tax_percent),
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
        tax_percent=Decimal(row["tax_percent"]),
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
