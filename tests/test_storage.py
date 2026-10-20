import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from quote_builder.quotes import (
    Extension,
    LineItem,
    LineTotals,
    Quote,
    QuoteSummary,
    QuoteTotals,
    Status,
    revision_draft,
)
from quote_builder.storage import (
    MAX_NUMBER_TRIES,
    NoFreeQuoteNumber,
    NotADraft,
    NotExtendable,
    connect,
    expire_overdue,
    extend_quote,
    list_quotes,
    list_versions,
    load_quote,
    mark_quoted,
    save_draft,
    save_new_quote,
    save_revision,
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


ISSUED = date(2026, 10, 19)
VALID_UNTIL = date(2026, 11, 18)


def test_save_draft_refuses_a_quote_no_longer_a_draft(conn):
    saved = mark_quoted(
        conn, lawn_quote(), ISSUED, VALID_UNTIL, numbers("Q-7KQ-M9XD")
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
        issued_on=date(2026, 10, 18),
        valid_until=date(2026, 11, 17),
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


# $45 + ($75 - 10%) + ($18.99 - $2 + 7.25% tax), as in lawn_quote.
LAWN_TOTALS = QuoteTotals(
    items_cents=4500 + 7500 + 1899,
    discount_cents=750 + 200,
    tax_cents=123,
    total_cents=4500 + 6750 + 1699 + 123,
)


def test_mark_a_new_draft_quoted(conn):
    quoted = mark_quoted(
        conn, lawn_quote(), ISSUED, VALID_UNTIL, numbers("Q-7KQ-M9XD")
    )
    assert quoted.number == "Q-7KQ-M9XD"
    assert quoted.status is Status.QUOTED
    assert (quoted.issued_on, quoted.valid_until) == (ISSUED, VALID_UNTIL)
    assert quoted.frozen == LAWN_TOTALS
    assert quoted.line_items[2].frozen == LineTotals(1899, 200, 123)
    assert load_quote(conn, "Q-7KQ-M9XD") == quoted


def test_mark_a_saved_draft_quoted_with_its_changes(conn):
    saved = save_new_quote(conn, lawn_quote(), numbers("Q-7KQ-M9XD"))
    changed = replace(saved, notes="Back yard only.")
    quoted = mark_quoted(conn, changed, ISSUED, VALID_UNTIL)
    assert quoted.notes == "Back yard only."
    assert load_quote(conn, "Q-7KQ-M9XD") == quoted
    assert [s.number for s in list_quotes(conn)] == ["Q-7KQ-M9XD"]


def test_mark_quoted_leaves_the_given_quote_alone(conn):
    quote = lawn_quote()
    mark_quoted(conn, quote, ISSUED, VALID_UNTIL, numbers("Q-7KQ-M9XD"))
    assert (quote.number, quote.status, quote.frozen) == (None, Status.DRAFT, None)


def test_quoted_quote_cant_be_marked_quoted_again(conn):
    quoted = mark_quoted(
        conn, lawn_quote(), ISSUED, VALID_UNTIL, numbers("Q-7KQ-M9XD")
    )
    with pytest.raises(NotADraft):
        mark_quoted(conn, quoted, date(2026, 12, 1), date(2026, 12, 31))
    assert load_quote(conn, "Q-7KQ-M9XD") == quoted


def test_frozen_figures_are_shown_not_worked_out_again(conn):
    mark_quoted(conn, lawn_quote(), ISSUED, VALID_UNTIL, numbers("Q-7KQ-M9XD"))
    # As if the rules for working out totals had changed since.
    conn.execute("UPDATE quotes SET frozen_total_cents = 1")
    conn.execute("UPDATE line_items SET frozen_tax_cents = 2")
    conn.commit()
    quote = load_quote(conn, "Q-7KQ-M9XD")
    assert quote.frozen.total_cents == 1
    assert {item.frozen.tax_cents for item in quote.line_items} == {2}
    assert list_quotes(conn)[0].total_cents == 1


def test_quoted_needs_its_frozen_totals(conn):
    # The database itself refuses a quoted quote without them.
    with pytest.raises(sqlite3.IntegrityError):
        save_new_quote(
            conn,
            replace(
                lawn_quote(), status=Status.QUOTED, issued_on=ISSUED
            ),
            numbers("Q-7KQ-M9XD"),
        )


def test_draft_has_no_frozen_totals(conn):
    saved = save_new_quote(conn, lawn_quote(), numbers("Q-7KQ-M9XD"))
    loaded = load_quote(conn, saved.number)
    assert loaded.frozen is None
    assert {item.frozen for item in loaded.line_items} == {None}


def quoted_lawn(conn):
    """lawn_quote, quoted 10/19/2026 and valid through 11/18/2026."""
    return mark_quoted(conn, lawn_quote(), ISSUED, VALID_UNTIL, numbers("Q-7KQ-M9XD"))


def status_of(conn, number):
    return load_quote(conn, number).status


def test_quote_is_good_through_its_last_day(conn):
    quoted = quoted_lawn(conn)
    expire_overdue(conn, VALID_UNTIL)
    assert status_of(conn, quoted.number) is Status.QUOTED


def test_quote_expires_the_day_after(conn):
    quoted = quoted_lawn(conn)
    expire_overdue(conn, VALID_UNTIL + timedelta(days=1))
    assert status_of(conn, quoted.number) is Status.EXPIRED


def test_expiry_leaves_drafts_and_the_time_saved_alone(conn):
    quoted = quoted_lawn(conn)
    draft = save_new_quote(
        conn, replace(lawn_quote(), valid_until=date(2026, 1, 1)), numbers("Q-222-2222")
    )
    before = list_quotes(conn)
    expire_overdue(conn, date(2027, 1, 1))
    assert status_of(conn, draft.number) is Status.DRAFT
    assert [s.updated_at for s in list_quotes(conn)] == [
        s.updated_at for s in before
    ]
    assert status_of(conn, quoted.number) is Status.EXPIRED


def test_extend_a_quoted_quote(conn):
    quoted = quoted_lawn(conn)
    today = date(2026, 11, 10)
    extended = extend_quote(conn, quoted, date(2026, 11, 25), today)
    assert extended.valid_until == date(2026, 11, 25)
    assert extended.status is Status.QUOTED
    assert extended.extensions == [
        Extension(today, VALID_UNTIL, date(2026, 11, 25))
    ]
    assert load_quote(conn, quoted.number) == extended


def test_extend_an_expired_quote_quotes_it_again(conn):
    quoted = quoted_lawn(conn)
    today = date(2026, 11, 20)
    expire_overdue(conn, today)
    expired = load_quote(conn, quoted.number)
    extended = extend_quote(conn, expired, date(2026, 12, 20), today)
    assert extended.status is Status.QUOTED
    assert load_quote(conn, quoted.number) == extended


def test_extensions_are_kept_oldest_first(conn):
    quoted = quoted_lawn(conn)
    once = extend_quote(conn, quoted, date(2026, 11, 25), date(2026, 11, 10))
    twice = extend_quote(conn, once, date(2026, 12, 2), date(2026, 11, 24))
    assert [e.old_valid_until for e in load_quote(conn, quoted.number).extensions] == [
        VALID_UNTIL,
        date(2026, 11, 25),
    ]
    assert twice.valid_until == date(2026, 12, 2)


@pytest.mark.parametrize(
    ("new", "message"),
    [
        (VALID_UNTIL, "must be later than the current one"),
        (date(2026, 11, 1), "must be later than the current one"),
        (date(2026, 11, 19), "can't be in the past"),
    ],
)
def test_extend_refuses_a_date_not_later_or_past(conn, new, message):
    quoted = quoted_lawn(conn)
    with pytest.raises(ValueError, match=message):
        extend_quote(conn, quoted, new, today=date(2026, 11, 20))
    assert load_quote(conn, quoted.number) == quoted


def test_draft_cant_be_extended(conn):
    saved = save_new_quote(conn, lawn_quote(), numbers("Q-7KQ-M9XD"))
    with pytest.raises(NotExtendable):
        extend_quote(conn, saved, date(2026, 12, 31), date(2026, 11, 1))
    assert load_quote(conn, saved.number).extensions == []


def test_extend_refuses_a_quote_changed_since_loaded(conn):
    quoted = quoted_lawn(conn)
    extend_quote(conn, quoted, date(2026, 11, 25), date(2026, 11, 10))
    # The stale copy still says valid through 11/18.
    with pytest.raises(NotExtendable):
        extend_quote(conn, quoted, date(2026, 11, 30), date(2026, 11, 10))
    assert len(load_quote(conn, quoted.number).extensions) == 1


def test_revision_draft_keeps_lines_and_notes_only(conn):
    quoted = quoted_lawn(conn)
    extended = extend_quote(conn, quoted, date(2026, 11, 25), date(2026, 11, 10))
    draft = revision_draft(extended, 1)
    assert (draft.number, draft.revision, draft.status) == (
        "Q-7KQ-M9XD",
        1,
        Status.DRAFT,
    )
    assert draft.notes == quoted.notes
    assert draft.line_items == lawn_quote().line_items  # no frozen figures
    assert (draft.issued_on, draft.valid_until, draft.frozen) == (None, None, None)
    assert draft.extensions == []


def test_save_a_revision(conn):
    quoted = quoted_lawn(conn)
    draft = replace(revision_draft(quoted, 1), notes="Back yard only.")
    save_revision(conn, draft)
    assert load_quote(conn, "Q-7KQ-M9XD", 1) == draft
    assert load_quote(conn, "Q-7KQ-M9XD") == draft  # the newest
    assert load_quote(conn, "Q-7KQ-M9XD", 0) == quoted  # still Quoted


def test_one_draft_per_quote(conn):
    quoted = quoted_lawn(conn)
    save_revision(conn, revision_draft(quoted, 1))
    with pytest.raises(sqlite3.IntegrityError):
        save_revision(conn, revision_draft(quoted, 2))


def test_quoting_a_revision_supersedes_the_one_before(conn):
    quoted = quoted_lawn(conn)
    draft = revision_draft(quoted, 1)
    revised = mark_quoted(
        conn, draft, date(2026, 11, 1), date(2026, 12, 1), new_revision=True
    )
    assert load_quote(conn, "Q-7KQ-M9XD", 1) == revised
    assert status_of_version(conn, 0) is Status.SUPERSEDED


def test_quoting_a_saved_revision_supersedes_too(conn):
    quoted = quoted_lawn(conn)
    expire_overdue(conn, date(2026, 12, 1))  # Expired versions are too
    save_revision(conn, revision_draft(quoted, 1))
    mark_quoted(
        conn, load_quote(conn, "Q-7KQ-M9XD"), date(2026, 12, 1), date(2026, 12, 31)
    )
    assert status_of_version(conn, 0) is Status.SUPERSEDED
    assert status_of_version(conn, 1) is Status.QUOTED


def status_of_version(conn, revision):
    return load_quote(conn, "Q-7KQ-M9XD", revision).status


def test_list_shows_each_quotes_newest_version(conn):
    quoted = quoted_lawn(conn)
    save_revision(
        conn,
        replace(revision_draft(quoted, 1), line_items=[LineItem("Edge", Decimal(1), 1500)]),
    )
    [summary] = list_quotes(conn)
    assert (summary.number, summary.revision, summary.status) == (
        "Q-7KQ-M9XD",
        1,
        Status.DRAFT,
    )
    assert summary.first_line == "Edge"


def test_search_matches_any_version(conn):
    quoted = quoted_lawn(conn)  # has a "Trim hedges" line
    save_revision(
        conn,
        replace(revision_draft(quoted, 1), line_items=[LineItem("Edge", Decimal(1), 1500)]),
    )
    [summary] = list_quotes(conn, "hedges")
    assert summary.revision == 1  # the row still shows the newest


def test_list_versions_newest_first(conn):
    quoted = quoted_lawn(conn)
    save_revision(conn, revision_draft(quoted, 1))
    versions = list_versions(conn, "Q-7KQ-M9XD")
    assert [(v.revision, v.status) for v in versions] == [
        (1, Status.DRAFT),
        (0, Status.QUOTED),
    ]
    assert (versions[1].issued_on, versions[1].valid_until) == (ISSUED, VALID_UNTIL)
