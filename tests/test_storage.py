import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from quote_builder.business import Business, PrintedBusiness, TaxPart, TaxRate
from quote_builder.catalog import CatalogItem
from quote_builder.customers import Customer
from quote_builder.quotes import (
    Extension,
    LineItem,
    LineTotals,
    Quote,
    QuoteSummary,
    QuoteTotals,
    SearchText,
    Status,
    revision_draft,
)
from quote_builder.storage import (
    MAX_NUMBER_TRIES,
    SCHEMA,
    SCHEMA_VERSION,
    DatabaseTooNew,
    NameNeeded,
    NoFreeQuoteNumber,
    NotADraft,
    NotExtendable,
    RateInUse,
    add_business,
    add_customer,
    connect,
    current_business,
    delete_catalog_item,
    delete_customer,
    list_catalog_items,
    save_catalog_item,
    delete_tax_rate,
    expire_overdue,
    extend_quote,
    list_businesses,
    list_customers,
    list_quotes,
    list_tax_rates,
    list_versions,
    load_quote,
    mark_quoted,
    pick_business,
    save_business,
    save_draft,
    save_new_quote,
    save_revision,
    save_tax_rate,
    search_texts,
    update_customer,
)


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "quotes.db")
    current_business(conn)  # made first, so its id is BUSINESS
    yield conn
    conn.close()


BUSINESS = 1  # the business made on first start, whose quotes tests make


def make_quote(**fields):
    """A Quote of BUSINESS, as each needs a business to be saved."""
    return Quote(business_id=BUSINESS, **fields)


def numbers(*drawn):
    """A stand-in for new_quote_number, drawing these numbers in turn."""
    return iter(drawn).__next__


def lawn_quote(tax_rate_id=None):
    """The blade is taxed: at 7.25% given the id of a lawn_rate."""
    return make_quote(
        tax_rate_id=tax_rate_id,
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
                taxed=True,
                discount_cents=200,
            ),
        ],
    )


def lawn_rate(conn):
    """A 7.25% rate for lawn_quote; its id."""
    rate = TaxRate(BUSINESS, "Home county", [TaxPart("", Decimal("7.25"))])
    return save_tax_rate(conn, rate).id


def test_connect_twice_to_the_same_file(tmp_path):
    connect(tmp_path / "quotes.db").close()
    connect(tmp_path / "quotes.db").close()


def _columns(conn, table):
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def _schema(conn):
    """The effective schema: each table's columns, by name, type, nullability
    and default -- robust to how the text was written (inline vs ALTER)."""
    tables = sorted(
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    )
    return {
        table: [tuple(row) for row in conn.execute(f"PRAGMA table_info({table})")]
        for table in tables
    }


def _first_release_db(path):
    """Create a database in the first release's state, at version 0. Migration
    1 then 2 add the probe column and drop it again, so the first release's
    schema is the current one; build it from schema.sql and stamp version 0."""
    conn = sqlite3.connect(path, autocommit=True)
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA user_version = 0")
    return conn


def _version_1_db(path):
    """Create a database at version 1: the current schema plus migration 1's
    probe column, which migration 2 removes."""
    conn = sqlite3.connect(path, autocommit=True)
    conn.executescript(SCHEMA)
    conn.execute("ALTER TABLE businesses ADD COLUMN probe TEXT NOT NULL DEFAULT ''")
    conn.execute("PRAGMA user_version = 1")
    return conn


def test_fresh_database_is_stamped_at_current_version(tmp_path):
    conn = connect(tmp_path / "quotes.db")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert "probe" not in _columns(conn, "businesses")


def test_existing_database_is_migrated_keeping_its_data(tmp_path):
    path = tmp_path / "quotes.db"
    old = _first_release_db(path)
    old.execute(
        "INSERT INTO businesses (name, valid_days) VALUES (?, ?)", ("Acme", 45)
    )
    old.close()

    conn = connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert "probe" not in _columns(conn, "businesses")
    row = conn.execute("SELECT name, valid_days FROM businesses").fetchone()
    assert (row["name"], row["valid_days"]) == ("Acme", 45)


def test_dropping_probe_rebuilds_keeping_data_and_foreign_keys(tmp_path):
    # Migration 2 rebuilds businesses (drop/recreate), which it must do with
    # the parent's rows and its children's foreign keys intact.
    path = tmp_path / "quotes.db"
    old = _version_1_db(path)
    old.execute("INSERT INTO businesses (id, name) VALUES (1, 'Acme')")
    old.execute(
        "INSERT INTO tax_rates (id, business_id, name) VALUES (1, 1, 'Home county')"
    )
    old.close()

    conn = connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert "probe" not in _columns(conn, "businesses")
    assert conn.execute("SELECT name FROM businesses WHERE id = 1").fetchone()[0] == "Acme"
    # The child still points at the rebuilt parent, and nothing dangles.
    assert (
        conn.execute("SELECT business_id FROM tax_rates WHERE id = 1").fetchone()[0] == 1
    )
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_migrated_database_matches_a_fresh_one(tmp_path):
    # Guards schema.sql and the migrations against drift: a database brought
    # up from version 0 must end with exactly a fresh one's schema.
    fresh = connect(tmp_path / "fresh.db")

    _first_release_db(tmp_path / "old.db").close()
    migrated = connect(tmp_path / "old.db")

    assert _schema(migrated) == _schema(fresh)


def test_database_from_a_newer_version_is_refused(tmp_path):
    path = tmp_path / "quotes.db"
    connect(path).close()
    ahead = sqlite3.connect(path, autocommit=True)
    ahead.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    ahead.close()
    with pytest.raises(DatabaseTooNew):
        connect(path)


def test_foreign_keys_are_enforced(conn):
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_new_quote_gets_a_number(conn):
    saved = save_new_quote(conn, make_quote(), numbers("Q-7KQ-M9XD"))
    assert saved.number == "Q-7KQ-M9XD"
    assert saved.revision == 0
    assert saved.status is Status.DRAFT


def test_saved_quote_loads_the_same(conn):
    saved = save_new_quote(conn, lawn_quote(), numbers("Q-7KQ-M9XD"))
    assert load_quote(conn, "Q-7KQ-M9XD") == saved


def test_a_lines_unit_is_saved_and_loaded(conn):
    quote = make_quote(
        line_items=[
            LineItem("Labor", Decimal("2.5"), 4500, unit="hour"),
            LineItem("Filter", Decimal(1), 1200),  # unit defaults to each
        ]
    )
    save_new_quote(conn, quote, numbers("Q-7KQ-M9XD"))
    loaded = load_quote(conn, "Q-7KQ-M9XD")
    assert [line.unit for line in loaded.line_items] == ["hour", "each"]


def test_a_quote_discount_is_saved_and_loaded(conn):
    quote = make_quote(
        line_items=[LineItem("Labor", Decimal(2), 4500)],
        quote_discount_percent=Decimal("10"),
    )
    save_new_quote(conn, quote, numbers("Q-7KQ-M9XD"))
    loaded = load_quote(conn, "Q-7KQ-M9XD")
    assert loaded.quote_discount_percent == Decimal("10")
    assert loaded.quote_discount_cents is None


def test_a_quote_discount_is_frozen_when_quoted(conn):
    quote = make_quote(
        tax_rate_id=lawn_rate(conn),
        line_items=[LineItem("Widget", Decimal(1), 10000, taxed=True)],
        quote_discount_cents=2000,
    )
    quoted = mark_quoted(conn, quote, ISSUED, VALID_UNTIL, numbers("Q-7KQ-M9XD"))
    loaded = load_quote(conn, "Q-7KQ-M9XD")
    assert loaded == quoted
    # $100 − $20 = $80 taxable; 7.25% = $5.80; total $85.80.
    assert loaded.frozen.quote_discount_cents == 2000
    assert loaded.frozen.tax_cents == 580
    assert loaded.frozen.total_cents == 8580


def test_saving_leaves_the_given_quote_alone(conn):
    quote = lawn_quote()
    save_new_quote(conn, quote, numbers("Q-7KQ-M9XD"))
    assert quote.number is None


def test_saved_quote_survives_reconnecting(tmp_path):
    path = tmp_path / "quotes.db"
    conn = connect(path)
    current_business(conn)  # BUSINESS, as the conn fixture makes
    saved = save_new_quote(conn, lawn_quote(), numbers("Q-7KQ-M9XD"))
    conn.close()
    conn = connect(path)
    assert load_quote(conn, "Q-7KQ-M9XD") == saved
    conn.close()


def test_missing_quote_loads_as_none(conn):
    assert load_quote(conn, "Q-000-0000") is None


def test_number_already_used_is_drawn_again(conn):
    save_new_quote(conn, make_quote(), numbers("Q-7KQ-M9XD"))
    saved = save_new_quote(conn, make_quote(), numbers("Q-7KQ-M9XD", "Q-AB1-2CD3"))
    assert saved.number == "Q-AB1-2CD3"


def test_gives_up_when_every_number_is_used(conn):
    save_new_quote(conn, make_quote(), numbers("Q-7KQ-M9XD"))
    with pytest.raises(NoFreeQuoteNumber):
        save_new_quote(conn, lawn_quote(), numbers(*["Q-7KQ-M9XD"] * MAX_NUMBER_TRIES))
    count = conn.execute("SELECT count(*) FROM line_items").fetchone()[0]
    assert count == 0


def test_line_with_both_discounts_is_refused(conn):
    both = make_quote(
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
    first = save_new_quote(
        conn, lawn_quote(lawn_rate(conn)), numbers("Q-111-1111"), now=at(0)
    )
    save_new_quote(conn, make_quote(), numbers("Q-222-2222"), now=at(1))
    save_draft(conn, replace(first, notes="Changed"), now=at(2))

    summaries = list_quotes(conn, BUSINESS)
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
        make_quote(),
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
    save_new_quote(conn, make_quote(notes="Gutters"), numbers("Q-222-2222"), now=at(1))
    assert [s.number for s in list_quotes(conn, BUSINESS,search)] == ["Q-111-1111"]


def test_search_finds_nothing(conn):
    save_new_quote(conn, lawn_quote(), numbers("Q-111-1111"))
    assert list_quotes(conn, BUSINESS,"snow") == []


@pytest.mark.parametrize("search", ["%", "_", "\\"])
def test_search_wildcards_match_only_themselves(conn, search):
    save_new_quote(conn, lawn_quote(), numbers("Q-111-1111"), now=at(0))
    save_new_quote(
        conn, make_quote(notes="10% off, path_1\\2"), numbers("Q-222-2222"), now=at(1)
    )
    assert [s.number for s in list_quotes(conn, BUSINESS,search)] == ["Q-222-2222"]


# $45 + ($75 - 10%) + ($18.99 - $2 + 7.25% tax), as in lawn_quote.
LAWN_TOTALS = QuoteTotals(
    items_cents=4500 + 7500 + 1899,
    discount_cents=750 + 200,
    quote_discount_cents=0,
    tax_cents=123,
    total_cents=4500 + 6750 + 1699 + 123,
)


def test_mark_a_new_draft_quoted(conn):
    quoted = mark_quoted(
        conn, lawn_quote(lawn_rate(conn)), ISSUED, VALID_UNTIL, numbers("Q-7KQ-M9XD")
    )
    assert quoted.number == "Q-7KQ-M9XD"
    assert (quoted.tax_name, quoted.tax_percent) == ("Home county", Decimal("7.25"))
    assert quoted.status is Status.QUOTED
    assert (quoted.issued_on, quoted.valid_until) == (ISSUED, VALID_UNTIL)
    assert quoted.frozen == LAWN_TOTALS
    # Tax is pooled at the foot now, so the frozen line carries none.
    assert quoted.line_items[2].frozen == LineTotals(1899, 200, 0)
    assert load_quote(conn, "Q-7KQ-M9XD") == quoted


def test_mark_a_saved_draft_quoted_with_its_changes(conn):
    saved = save_new_quote(conn, lawn_quote(), numbers("Q-7KQ-M9XD"))
    changed = replace(saved, notes="Back yard only.")
    quoted = mark_quoted(conn, changed, ISSUED, VALID_UNTIL)
    assert quoted.notes == "Back yard only."
    assert load_quote(conn, "Q-7KQ-M9XD") == quoted
    assert [s.number for s in list_quotes(conn, BUSINESS)] == ["Q-7KQ-M9XD"]


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
    assert list_quotes(conn, BUSINESS)[0].total_cents == 1


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


@pytest.mark.parametrize("status", ["Accepted", "Declined"])
def test_a_quotes_outcome_isnt_a_status(conn, status):
    # Out of scope: the app doesn't follow a quote to its outcome.
    quoted = quoted_lawn(conn)
    with pytest.raises(sqlite3.IntegrityError), conn:
        conn.execute(
            "UPDATE quotes SET status = ? WHERE number = ?", (status, quoted.number)
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
    before = list_quotes(conn, BUSINESS)
    expire_overdue(conn, date(2027, 1, 1))
    assert status_of(conn, draft.number) is Status.DRAFT
    assert [s.updated_at for s in list_quotes(conn, BUSINESS)] == [
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
    [summary] = list_quotes(conn, BUSINESS)
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
    [summary] = list_quotes(conn, BUSINESS,"hedges")
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


def test_search_texts_of_every_version_newest_first(conn):
    quoted = quoted_lawn(conn)
    save_revision(
        conn,
        replace(
            revision_draft(quoted, 1),
            notes="",
            line_items=[LineItem("Edge", Decimal(1), 1500)],
        ),
    )
    save_new_quote(conn, make_quote(notes="Gutters"), numbers("Q-222-2222"))

    texts = search_texts(conn, ["Q-7KQ-M9XD"])
    assert texts == {
        "Q-7KQ-M9XD": [
            SearchText(1, "line", 0, "Edge"),  # R1 has no notes
            SearchText(0, "line", 0, "Mow lawn"),
            SearchText(0, "line", 1, "Trim hedges"),
            SearchText(0, "line", 2, "Hedge trimmer blade"),
            SearchText(0, "notes", 0, "Front and back yard."),
        ]
    }


def test_search_texts_of_no_quotes(conn):
    assert search_texts(conn, []) == {}


def test_a_business_is_made_the_first_time(conn):
    business = current_business(conn)
    assert business.id is not None
    assert business.valid_days == 30
    assert business.name == ""
    assert business.pilot is False
    assert current_business(conn) == business  # not a second one


def test_save_business(conn):
    business = replace(
        current_business(conn),
        name="Pressure washing",
        pilot=True,
        valid_days=14,
        extend_days=7,
    )
    save_business(conn, business)
    assert current_business(conn) == business
    assert current_business(conn).pilot is True  # a bool, not the stored 1
    save_business(conn, replace(business, extend_days=None))  # unset again
    assert current_business(conn).extend_days is None


def test_business_extend_days_must_be_above_zero(conn):
    business = replace(current_business(conn), extend_days=0)
    with pytest.raises(sqlite3.IntegrityError):
        save_business(conn, business)


def test_business_valid_days_must_be_above_zero(conn):
    business = replace(current_business(conn), valid_days=0)
    with pytest.raises(sqlite3.IntegrityError):
        save_business(conn, business)


def test_add_a_business(conn):
    added = add_business(conn, Business(name="Acme", valid_days=14))
    assert added.id is not None
    assert list_businesses(conn)[1] == added  # after the unnamed one


def test_mark_quoted_freezes_the_business_details(conn):
    detailed = replace(
        current_business(conn),
        name="John Doe's Lawn Service",
        address="12 Oak St",
        phone="5551234567",
        ext="12",
        email="john@example.com",
        website="johnslawn.example.com",
        terms="Net 30.",
    )
    save_business(conn, detailed)
    quoted = mark_quoted(
        conn,
        make_quote(line_items=[LineItem("Mow", Decimal(1), 4500)]),
        date(2026, 9, 1),
        date(2026, 12, 1),
        numbers("Q-7KQ-M9XD"),
    )
    # Change the business afterward: the quote keeps the snapshot.
    save_business(conn, replace(detailed, name="New Name", terms="Net 15."))

    frozen = load_quote(conn, quoted.number).printed_business
    assert frozen == PrintedBusiness(
        name="John Doe's Lawn Service",
        address="12 Oak St",
        phone="5551234567",
        ext="12",
        email="john@example.com",
        website="johnslawn.example.com",
        terms="Net 30.",
    )


def test_a_draft_has_no_frozen_business(conn):
    saved = save_new_quote(
        conn, make_quote(line_items=[LineItem("Mow", Decimal(1), 4500)]), numbers("Q-1")
    )
    assert load_quote(conn, saved.number).printed_business is None


def test_business_details_round_trip(conn):
    # Added with details, and changed again: both carry every field.
    added = add_business(
        conn,
        Business(
            name="Acme",
            address="12 Oak St\nSpringfield, IL 62704",
            phone="1234567890",
            ext="12",
            email="hello@acme.example.com",
            website="acme.example.com",
            terms="Payment due within 30 days.",
        ),
    )
    assert list_businesses(conn)[1] == added
    changed = replace(added, phone="5559876543", terms="50% deposit to schedule.")
    save_business(conn, changed)
    assert list_businesses(conn)[1] == changed


def test_a_new_business_needs_a_name(conn):
    with pytest.raises(NameNeeded):
        add_business(conn, Business())
    assert len(list_businesses(conn)) == 1


def test_a_lone_business_can_go_unnamed(conn):
    business = replace(current_business(conn), name="Acme")
    save_business(conn, business)
    save_business(conn, replace(business, name=""))
    assert current_business(conn).name == ""


def test_a_name_cant_be_cleared_once_there_are_two(conn):
    business = replace(current_business(conn), name="Acme")
    save_business(conn, business)
    add_business(conn, Business(name="Pressure washing", pilot=True))
    with pytest.raises(NameNeeded):
        save_business(conn, replace(business, name="", valid_days=14))
    assert current_business(conn) == business  # nothing changed


def test_businesses_list_before_pilots_by_name_in_any_case(conn):
    save_business(conn, replace(current_business(conn), name="lawn care"))
    for name, pilot in [("Gift baskets", True), ("decks", True), ("Acme", False)]:
        add_business(conn, Business(name=name, pilot=pilot))
    names = [b.name for b in list_businesses(conn)]
    assert names == ["Acme", "lawn care", "decks", "Gift baskets"]


def test_the_first_business_is_current_until_another_is_picked(conn):
    acme = add_business(conn, Business(name="Acme"))
    assert current_business(conn).id == BUSINESS
    pick_business(conn, acme.id)
    assert current_business(conn) == acme
    pick_business(conn, BUSINESS)  # picked again: the one row changes
    assert current_business(conn).id == BUSINESS


def test_the_picked_business_survives_reconnecting(tmp_path):
    path = tmp_path / "quotes.db"
    conn = connect(path)
    current_business(conn)
    acme = add_business(conn, Business(name="Acme"))
    pick_business(conn, acme.id)
    conn.close()
    conn = connect(path)
    assert current_business(conn) == acme
    conn.close()


def test_list_quotes_only_of_the_business(conn):
    acme = add_business(conn, Business(name="Acme"))
    save_new_quote(conn, make_quote(notes="Ours"), numbers("Q-111-1111"))
    save_new_quote(
        conn, Quote(business_id=acme.id, notes="Theirs"), numbers("Q-222-2222")
    )
    assert [s.number for s in list_quotes(conn, BUSINESS)] == ["Q-111-1111"]
    assert [s.number for s in list_quotes(conn, acme.id, "theirs")] == ["Q-222-2222"]
    assert list_quotes(conn, BUSINESS, "theirs") == []


def home_county(**changes):
    rate = TaxRate(
        BUSINESS,
        "Home county",
        [TaxPart("State", Decimal("4.75")), TaxPart("County", Decimal("1.5"))],
    )
    return replace(rate, **changes)


def test_saved_tax_rate_loads_the_same(conn):
    saved = save_tax_rate(conn, home_county(is_default=True))
    assert saved.id is not None
    assert list_tax_rates(conn, BUSINESS) == [saved]


def test_tax_rates_list_by_name_in_any_case(conn):
    save_tax_rate(conn, home_county(name="out of town"))
    save_tax_rate(conn, home_county(name="Home county"))
    names = [r.name for r in list_tax_rates(conn, BUSINESS)]
    assert names == ["Home county", "out of town"]


def test_tax_rates_are_the_businesss_own(conn):
    acme = add_business(conn, Business(name="Acme"))
    save_tax_rate(conn, home_county())
    assert list_tax_rates(conn, acme.id) == []


def test_changing_a_tax_rate_replaces_its_parts(conn):
    saved = save_tax_rate(conn, home_county())
    changed = replace(saved, name="Home", parts=[TaxPart("", Decimal("7"))])
    save_tax_rate(conn, changed)
    assert list_tax_rates(conn, BUSINESS) == [changed]


def test_a_new_default_takes_over(conn):
    old = save_tax_rate(conn, home_county(is_default=True))
    new = save_tax_rate(conn, home_county(name="Lake county", is_default=True))
    defaults = [r.id for r in list_tax_rates(conn, BUSINESS) if r.is_default]
    assert defaults == [new.id]
    save_tax_rate(conn, old)  # saved again as the default
    defaults = [r.id for r in list_tax_rates(conn, BUSINESS) if r.is_default]
    assert defaults == [old.id]


def test_each_business_has_its_own_default(conn):
    acme = add_business(conn, Business(name="Acme"))
    save_tax_rate(conn, home_county(is_default=True))
    save_tax_rate(conn, home_county(business_id=acme.id, is_default=True))
    assert list_tax_rates(conn, BUSINESS)[0].is_default


def test_delete_a_tax_rate_and_its_parts(conn):
    saved = save_tax_rate(conn, home_county())
    delete_tax_rate(conn, saved.id)
    assert list_tax_rates(conn, BUSINESS) == []
    assert conn.execute("SELECT count(*) FROM tax_rate_parts").fetchone()[0] == 0


def test_a_tax_rate_needs_a_name_in_the_database(conn):
    with pytest.raises(sqlite3.IntegrityError):
        save_tax_rate(conn, home_county(name=""))


def test_a_draft_follows_its_rate_as_it_changes(conn):
    rate_id = lawn_rate(conn)
    save_new_quote(conn, lawn_quote(rate_id), numbers("Q-7KQ-M9XD"))
    [rate] = list_tax_rates(conn, BUSINESS)
    save_tax_rate(conn, replace(rate, name="Home", parts=[TaxPart("", Decimal("10"))]))

    draft = load_quote(conn, "Q-7KQ-M9XD")
    assert (draft.tax_name, draft.tax_percent) == ("Home", Decimal("10"))
    # The blade: $16.99 at 10% = $1.70 ($1.699).
    assert list_quotes(conn, BUSINESS)[0].total_cents == 4500 + 6750 + 1699 + 170


def test_a_quoted_quote_keeps_its_rate_as_it_was(conn):
    rate_id = lawn_rate(conn)
    mark_quoted(conn, lawn_quote(rate_id), ISSUED, VALID_UNTIL, numbers("Q-7KQ-M9XD"))
    [rate] = list_tax_rates(conn, BUSINESS)
    save_tax_rate(conn, replace(rate, parts=[TaxPart("", Decimal("10"))]))

    quoted = load_quote(conn, "Q-7KQ-M9XD")
    assert quoted.tax_percent == Decimal("7.25")
    assert quoted.frozen == LAWN_TOTALS


def test_an_untaxed_quote_is_quoted_untaxed(conn):
    quoted = mark_quoted(conn, lawn_quote(), ISSUED, VALID_UNTIL, numbers("Q-7KQ-M9XD"))
    loaded = load_quote(conn, "Q-7KQ-M9XD")
    assert (loaded.tax_rate_id, loaded.tax_name, loaded.tax_percent) == (None, "", 0)
    assert loaded.frozen.tax_cents == 0
    assert loaded == quoted


def test_a_rate_a_draft_uses_cant_be_deleted(conn):
    rate_id = lawn_rate(conn)
    save_new_quote(conn, lawn_quote(rate_id), numbers("Q-111-1111"))
    save_new_quote(conn, lawn_quote(rate_id), numbers("Q-222-2222"))
    with pytest.raises(RateInUse) as refused:
        delete_tax_rate(conn, rate_id)
    assert refused.value.drafts == 2
    assert len(list_tax_rates(conn, BUSINESS)) == 1


def test_a_rate_only_quoted_quotes_used_can_be_deleted(conn):
    rate_id = lawn_rate(conn)
    mark_quoted(conn, lawn_quote(rate_id), ISSUED, VALID_UNTIL, numbers("Q-7KQ-M9XD"))
    delete_tax_rate(conn, rate_id)

    quoted = load_quote(conn, "Q-7KQ-M9XD")
    assert quoted.tax_rate_id is None
    assert (quoted.tax_name, quoted.tax_percent) == ("Home county", Decimal("7.25"))


def test_a_revision_follows_the_rate_as_it_is_now(conn):
    rate_id = lawn_rate(conn)
    quoted = mark_quoted(
        conn, lawn_quote(rate_id), ISSUED, VALID_UNTIL, numbers("Q-7KQ-M9XD")
    )
    [rate] = list_tax_rates(conn, BUSINESS)
    save_tax_rate(conn, replace(rate, parts=[TaxPart("", Decimal("10"))]))
    save_revision(conn, revision_draft(quoted, 1))

    revision = load_quote(conn, "Q-7KQ-M9XD")
    assert (revision.tax_rate_id, revision.tax_percent) == (rate_id, Decimal("10"))


def test_a_quote_needs_a_business(conn):
    with pytest.raises(sqlite3.IntegrityError):
        save_new_quote(conn, Quote(), numbers("Q-111-1111"))


def test_a_revision_keeps_the_quotes_business(conn):
    acme = add_business(conn, Business(name="Acme"))
    quoted = mark_quoted(
        conn,
        replace(lawn_quote(), business_id=acme.id),
        ISSUED,
        VALID_UNTIL,
        numbers("Q-7KQ-M9XD"),
    )
    save_revision(conn, revision_draft(quoted, 1))
    assert load_quote(conn, "Q-7KQ-M9XD").business_id == acme.id
    assert [s.revision for s in list_quotes(conn, acme.id)] == [1]


def jane(conn, **changes):
    customer = Customer(
        BUSINESS, "Jane Doe", "jane@example.com", "1234560134", address="12 Oak St"
    )
    return add_customer(conn, replace(customer, **changes))


def on_quote(customer):
    """A customer as a quote holds them: its own copy, with no id."""
    return replace(customer, id=None)


def test_customers_listed_by_name_per_business(conn):
    sam = add_customer(conn, Customer(BUSINESS, "sam Example"))
    doe = jane(conn)
    acme = add_business(conn, Business(name="Acme"))
    add_customer(conn, Customer(acme.id, "Acme's customer"))
    assert list_customers(conn, BUSINESS) == [doe, sam]


def test_update_a_customer(conn):
    doe = jane(conn)
    other = add_customer(conn, Customer(BUSINESS, "Sam Example"))
    changed = replace(doe, name="Jane Smith", phone="1234560199")
    update_customer(conn, changed)
    assert list_customers(conn, BUSINESS) == [changed, other]


def test_delete_a_customer(conn):
    doe = jane(conn)
    delete_customer(conn, doe.id)
    assert list_customers(conn, BUSINESS) == []


def test_a_quote_keeps_its_copy_when_a_customer_is_deleted(conn):
    doe = jane(conn)
    saved = save_new_quote(conn, make_quote(customer=doe), numbers("Q-7KQ-M9XD"))
    delete_customer(conn, doe.id)
    assert load_quote(conn, saved.number).customer == on_quote(doe)


def test_catalog_listed_by_description_per_business(conn):
    mulch = save_catalog_item(conn, CatalogItem(BUSINESS, "mulch", 650, "each", True))
    edging = save_catalog_item(conn, CatalogItem(BUSINESS, "Edging"))
    acme = add_business(conn, Business(name="Acme"))
    save_catalog_item(conn, CatalogItem(acme.id, "Acme's item"))
    assert list_catalog_items(conn, BUSINESS) == [edging, mulch]


def test_change_a_catalog_item(conn):
    item = save_catalog_item(conn, CatalogItem(BUSINESS, "Mow", 4500, "hour"))
    changed = replace(item, description="Mow lawn", price_cents=None, taxable=True)
    assert save_catalog_item(conn, changed) == changed
    assert list_catalog_items(conn, BUSINESS) == [changed]


def test_delete_a_catalog_item(conn):
    item = save_catalog_item(conn, CatalogItem(BUSINESS, "Mow"))
    delete_catalog_item(conn, item.id)
    assert list_catalog_items(conn, BUSINESS) == []


def test_a_catalog_item_needs_a_description(conn):
    with pytest.raises(sqlite3.IntegrityError):
        save_catalog_item(conn, CatalogItem(BUSINESS))


def test_a_catalog_price_cant_be_negative(conn):
    with pytest.raises(sqlite3.IntegrityError):
        save_catalog_item(conn, CatalogItem(BUSINESS, "Mow", -1))


def test_a_customer_needs_a_name(conn):
    with pytest.raises(sqlite3.IntegrityError):
        add_customer(conn, Customer(BUSINESS))


def test_a_draft_keeps_its_own_copy_of_the_customer(conn):
    doe = jane(conn)
    saved = save_new_quote(conn, make_quote(customer=doe), numbers("Q-7KQ-M9XD"))
    assert load_quote(conn, saved.number).customer == on_quote(doe)

    update_customer(conn, replace(doe, phone="1234560199"))
    assert load_quote(conn, saved.number).customer == on_quote(doe)
    [summary] = list_quotes(conn, BUSINESS)
    assert summary.customer_name == "Jane Doe"


def test_a_saved_draft_can_change_its_copy(conn):
    doe = jane(conn)
    saved = save_new_quote(conn, make_quote(customer=doe), numbers("Q-7KQ-M9XD"))
    changed = replace(on_quote(doe), address="48 Elm Rd")
    save_draft(conn, replace(saved, customer=changed))
    assert load_quote(conn, saved.number).customer == changed


def test_quoted_keeps_its_copy_of_the_customer(conn):
    doe = jane(conn)
    mark_quoted(
        conn, lawn_quote(), ISSUED, VALID_UNTIL, numbers("Q-7KQ-M9XD")
    )  # without one, for contrast
    quoted = mark_quoted(
        conn,
        replace(lawn_quote(), customer=doe),
        ISSUED,
        VALID_UNTIL,
        numbers("Q-8AB-C2DE"),
    )

    update_customer(conn, replace(doe, name="Jane Smith", address="48 Elm Rd"))
    assert load_quote(conn, quoted.number).customer == on_quote(doe)
    assert sorted(
        (s.customer_name or "" for s in list_quotes(conn, BUSINESS))
    ) == ["", "Jane Doe"]
    assert load_quote(conn, "Q-7KQ-M9XD").customer is None


def test_mark_quoted_keeps_the_copy_the_form_had(conn):
    doe = jane(conn)
    saved = save_new_quote(conn, replace(lawn_quote(), customer=doe))
    update_customer(conn, replace(doe, phone="1234560199"))
    mark_quoted(conn, saved, ISSUED, VALID_UNTIL)
    assert load_quote(conn, saved.number).customer.phone == "1234560134"


def test_a_revision_keeps_the_copy_of_the_version_before(conn):
    doe = jane(conn)
    quoted = mark_quoted(
        conn,
        replace(lawn_quote(), customer=doe),
        ISSUED,
        VALID_UNTIL,
        numbers("Q-7KQ-M9XD"),
    )
    update_customer(conn, replace(doe, name="Jane Smith"))
    save_revision(conn, revision_draft(quoted, 1))

    assert load_quote(conn, "Q-7KQ-M9XD").customer.name == "Jane Doe"


def test_a_customer_without_a_name_can_be_on_a_quote(conn):
    saved = save_new_quote(
        conn, make_quote(customer=Customer(BUSINESS, phone="1234560134"))
    )
    assert load_quote(conn, saved.number).customer.phone == "1234560134"
    [summary] = list_quotes(conn, BUSINESS)
    assert summary.customer_name is None  # so the row shows its first line


def test_a_quote_without_a_customer_loads_without_one(conn):
    saved = save_new_quote(conn, make_quote())
    assert load_quote(conn, saved.number).customer is None


@pytest.mark.parametrize("search", ["JANE", "example.com", "0134", "oak st"])
def test_search_matches_the_customers_details(conn, search):
    save_new_quote(conn, make_quote(customer=jane(conn)))
    save_new_quote(conn, make_quote(notes="No customer"))
    [found] = list_quotes(conn, BUSINESS, search)
    assert found.customer_name == "Jane Doe"


def test_search_matches_a_quotes_own_copy(conn):
    doe = jane(conn)
    mark_quoted(
        conn, replace(lawn_quote(), customer=doe), ISSUED, VALID_UNTIL, numbers("Q-7KQ-M9XD")
    )
    update_customer(conn, replace(doe, phone="1234560199"))

    assert [s.number for s in list_quotes(conn, BUSINESS, "0134")] == ["Q-7KQ-M9XD"]
    assert list_quotes(conn, BUSINESS, "0199") == []


def test_search_texts_hold_the_customers_details(conn):
    saved = save_new_quote(
        conn,
        make_quote(
            customer=jane(conn, email=""),
            notes="Gate code 4411",
            line_items=[LineItem("Mow lawn", Decimal(1), 4500)],
        ),
        numbers("Q-7KQ-M9XD"),
    )
    assert search_texts(conn, [saved.number])[saved.number] == [
        SearchText(0, "customer", 0, "Jane Doe"),
        SearchText(0, "customer", 2, "1234560134"),  # no email: left out
        SearchText(0, "customer", 3, "12 Oak St"),
        SearchText(0, "line", 0, "Mow lawn"),
        SearchText(0, "notes", 0, "Gate code 4411"),
    ]
