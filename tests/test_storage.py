import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from quote_builder.quotes import LineItem, Quote, Status
from quote_builder.storage import (
    MAX_NUMBER_TRIES,
    NoFreeQuoteNumber,
    connect,
    load_quote,
    save_new_quote,
)


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "quotes.db")
    yield conn
    conn.close()


def numbers(*drawn):
    """A stand-in for new_quote_number, drawing these numbers in turn."""
    return iter(drawn).__next__


def lawn_quote():
    return Quote(
        issued_on=date(2026, 10, 18),
        valid_until=date(2026, 11, 17),
        notes="Front and back yard.",
        line_items=[
            LineItem("Mow lawn", Decimal("1"), 4500),
            LineItem(
                "Trim hedges",
                Decimal("2.5"),
                3000,
                discount_percent=Decimal("10"),
            ),
            LineItem(
                "Hedge trimmer blade",
                Decimal("1"),
                1899,
                tax_percent=Decimal("7.25"),
                discount_cents=200,
            ),
        ],
    )


def test_connect_twice_to_the_same_file(tmp_path):
    connect(tmp_path / "quotes.db").close()
    connect(tmp_path / "quotes.db").close()


def test_foreign_keys_are_enforced(conn):
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_new_quote_gets_a_number(conn):
    saved = save_new_quote(conn, Quote(), numbers("Q-7KQ-M9XD"))
    assert saved.number == "Q-7KQ-M9XD"
    assert saved.revision == 0
    assert saved.status is Status.DRAFT


def test_saved_quote_loads_the_same(conn):
    saved = save_new_quote(conn, lawn_quote(), numbers("Q-7KQ-M9XD"))
    assert load_quote(conn, "Q-7KQ-M9XD") == saved


def test_saving_leaves_the_given_quote_alone(conn):
    quote = lawn_quote()
    save_new_quote(conn, quote, numbers("Q-7KQ-M9XD"))
    assert quote.number is None


def test_saved_quote_survives_reconnecting(tmp_path):
    path = tmp_path / "quotes.db"
    conn = connect(path)
    saved = save_new_quote(conn, lawn_quote(), numbers("Q-7KQ-M9XD"))
    conn.close()
    conn = connect(path)
    assert load_quote(conn, "Q-7KQ-M9XD") == saved
    conn.close()


def test_missing_quote_loads_as_none(conn):
    assert load_quote(conn, "Q-000-0000") is None


def test_number_already_used_is_drawn_again(conn):
    save_new_quote(conn, Quote(), numbers("Q-7KQ-M9XD"))
    saved = save_new_quote(conn, Quote(), numbers("Q-7KQ-M9XD", "Q-AB1-2CD3"))
    assert saved.number == "Q-AB1-2CD3"


def test_gives_up_when_every_number_is_used(conn):
    save_new_quote(conn, Quote(), numbers("Q-7KQ-M9XD"))
    with pytest.raises(NoFreeQuoteNumber):
        save_new_quote(conn, lawn_quote(), numbers(*["Q-7KQ-M9XD"] * MAX_NUMBER_TRIES))
    count = conn.execute("SELECT count(*) FROM line_items").fetchone()[0]
    assert count == 0


def test_line_with_both_discounts_is_refused(conn):
    both = Quote(
        line_items=[
            LineItem(
                "Mow lawn",
                Decimal("1"),
                4500,
                discount_cents=500,
                discount_percent=Decimal("10"),
            )
        ]
    )
    with pytest.raises(sqlite3.IntegrityError):
        save_new_quote(conn, both, numbers("Q-7KQ-M9XD"))
    # The whole save is rolled back, quote row included.
    assert load_quote(conn, "Q-7KQ-M9XD") is None
