import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from quote_builder.quotes import LineItem, Quote, QuoteSummary, Status
from quote_builder.storage import (
    MAX_NUMBER_TRIES,
    NoFreeQuoteNumber,
    NotADraft,
    connect,
    list_quotes,
    load_quote,
    save_draft,
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


def test_save_draft_replaces_its_fields_and_lines(conn):
    saved = save_new_quote(conn, lawn_quote(), numbers("Q-7KQ-M9XD"))
    changed = replace(
        saved,
        notes="Back yard only.",
        valid_until=date(2026, 12, 1),
        line_items=[LineItem("Mow back lawn", Decimal("1"), 3000)],
    )
    save_draft(conn, changed)
    assert load_quote(conn, "Q-7KQ-M9XD") == changed
    count = conn.execute("SELECT count(*) FROM line_items").fetchone()[0]
    assert count == 1


def test_save_draft_refuses_a_quote_no_longer_a_draft(conn):
    saved = save_new_quote(
        conn, replace(lawn_quote(), status=Status.QUOTED), numbers("Q-7KQ-M9XD")
    )
    with pytest.raises(NotADraft):
        save_draft(conn, replace(saved, notes="Changed"))
    assert load_quote(conn, "Q-7KQ-M9XD") == saved


def test_save_draft_refuses_a_missing_quote(conn):
    with pytest.raises(NotADraft):
        save_draft(conn, replace(lawn_quote(), number="Q-000-0000"))


def test_failed_save_draft_keeps_the_old_lines(conn):
    saved = save_new_quote(conn, lawn_quote(), numbers("Q-7KQ-M9XD"))
    both = LineItem(
        "Mow lawn",
        Decimal("1"),
        4500,
        discount_cents=500,
        discount_percent=Decimal("10"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        save_draft(conn, replace(saved, notes="Changed", line_items=[both]))
    assert load_quote(conn, "Q-7KQ-M9XD") == saved


def at(minute):
    """A moment on 2026-10-19, `minute` minutes after 10:00 UTC."""
    return datetime(2026, 10, 19, 10, minute, tzinfo=UTC)


def test_list_quotes_last_changed_first(conn):
    first = save_new_quote(conn, lawn_quote(), numbers("Q-111-1111"), now=at(0))
    save_new_quote(conn, Quote(), numbers("Q-222-2222"), now=at(1))
    save_draft(conn, replace(first, notes="Changed"), now=at(2))

    summaries = list_quotes(conn)
    assert [s.number for s in summaries] == ["Q-111-1111", "Q-222-2222"]
    assert summaries[0] == QuoteSummary(
        number="Q-111-1111",
        revision=0,
        status=Status.DRAFT,
        first_line="Mow lawn",
        updated_at=at(2),
        # $45 + ($75 - 10%) + ($18.99 - $2 + 7.25% tax).
        total_cents=4500 + 6750 + 1699 + 123,
    )
    assert summaries[1].first_line is None
    assert summaries[1].total_cents == 0


def test_updated_at_is_kept_in_utc_to_the_second(conn):
    eastern = timezone(timedelta(hours=-4))
    save_new_quote(
        conn,
        Quote(),
        numbers("Q-111-1111"),
        now=datetime(2026, 10, 19, 6, 0, 0, 750000, tzinfo=eastern),
    )
    stored = conn.execute("SELECT updated_at FROM quotes").fetchone()[0]
    assert stored == "2026-10-19T10:00:00+00:00"


@pytest.mark.parametrize(
    "search", ["q-111", "HEDGE", "  trimmer  ", "front and back"]
)
def test_search_matches_number_lines_and_notes(conn, search):
    save_new_quote(conn, lawn_quote(), numbers("Q-111-1111"), now=at(0))
    save_new_quote(conn, Quote(notes="Gutters"), numbers("Q-222-2222"), now=at(1))
    assert [s.number for s in list_quotes(conn, search)] == ["Q-111-1111"]


def test_search_finds_nothing(conn):
    save_new_quote(conn, lawn_quote(), numbers("Q-111-1111"))
    assert list_quotes(conn, "snow") == []


@pytest.mark.parametrize("search", ["%", "_", "\\"])
def test_search_wildcards_match_only_themselves(conn, search):
    save_new_quote(conn, lawn_quote(), numbers("Q-111-1111"), now=at(0))
    save_new_quote(
        conn, Quote(notes="10% off, path_1\\2"), numbers("Q-222-2222"), now=at(1)
    )
    assert [s.number for s in list_quotes(conn, search)] == ["Q-222-2222"]
