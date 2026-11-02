from datetime import UTC, datetime

import pytest

from quote_builder.quotes import QuoteSummary, SearchText, Status
from quote_builder.search import (
    MARK_CLASS,
    HiddenMatch,
    excerpt,
    hidden_match,
    highlight,
    matches,
    row_text,
)

MARK = f'<mark class="{MARK_CLASS}">'


def test_highlight_wraps_each_match_in_any_case():
    assert highlight("Trim hedges, then HEDGES again", "hedges") == (
        f"Trim {MARK}hedges</mark>, then {MARK}HEDGES</mark> again"
    )


def test_highlight_escapes_the_text():
    assert highlight("<b>Deck</b> & rail", "deck") == (
        f"&lt;b&gt;{MARK}Deck</mark>&lt;/b&gt; &amp; rail"
    )


def test_highlight_matches_the_term_as_typed():
    # Not a regular expression: "." matches only a dot.
    assert highlight("$5.50 or 5x50", "5.5") == f"${MARK}5.5</mark>0 or 5x50"


@pytest.mark.parametrize("term", ["", "   "])
def test_highlight_with_no_term(term):
    assert highlight("a < b", term) == "a &lt; b"


def test_matches():
    assert matches("Trim hedges", " HEDGES ")
    assert not matches("Trim hedges", "lawn")
    assert not matches("Trim hedges", "")


def test_excerpt_cuts_around_the_match():
    text = "Front yard first, then the back hedges too, weather permitting."
    # Cut at whole words, about 20 characters each side.
    assert excerpt(text, "hedges") == "…then the back hedges too, weather…"


def test_excerpt_keeps_short_text_whole():
    assert excerpt("Back hedges", "hedges") == "Back hedges"


def test_excerpt_joins_lines():
    assert excerpt("Gate code 4411.\nBack\nhedges", "hedges") == (
        "…code 4411. Back hedges"
    )


def summary(revision=0, first_line="Mow lawn", customer_name=None):
    return QuoteSummary(
        number="Q-7KQ-M9XD",
        revision=revision,
        status=Status.DRAFT,
        first_line=first_line,
        updated_at=datetime(2026, 10, 19, tzinfo=UTC),
        total_cents=4500,
        customer_name=customer_name,
    )


def test_the_row_shows_the_customer_or_else_the_first_line():
    assert row_text(summary(customer_name="Jane Doe")) == "Jane Doe"
    assert row_text(summary()) == "Mow lawn"
    assert row_text(summary(first_line=None)) is None


def line(revision, position, text):
    return SearchText(revision, "line", position, text)


def notes(revision, text):
    return SearchText(revision, "notes", 0, text)


def test_no_hidden_match_when_the_row_shows_it():
    texts = [line(0, 0, "Mow lawn"), notes(0, "Mow first")]
    assert hidden_match(summary(), texts, "mow") is None
    assert hidden_match(summary(), texts, "7kq") is None  # in the number


def test_hidden_match_in_the_first_line_when_the_row_shows_the_customer():
    texts = [line(0, 0, "Mow lawn")]
    found = hidden_match(summary(customer_name="Jane Doe"), texts, "mow")
    assert found == HiddenMatch("Line Item 1", "Mow lawn", 0)
    assert hidden_match(summary(customer_name="Jane Doe"), texts, "jane") is None


def test_hidden_match_in_notes():
    texts = [line(0, 0, "Mow lawn"), notes(0, "Back hedges too")]
    found = hidden_match(summary(), texts, "hedges")
    assert found == HiddenMatch("Notes", "Back hedges too", 0)


def test_hidden_match_in_a_later_line():
    texts = [line(0, 0, "Mow lawn"), line(0, 2, "Trim hedges")]
    found = hidden_match(summary(), texts, "hedges")
    assert found == HiddenMatch("Line Item 3", "Trim hedges", 0)


def test_hidden_match_in_an_older_version():
    texts = [
        line(1, 0, "Mow lawn"),
        line(0, 0, "Trim hedges"),
        notes(0, "Old notes"),
    ]
    found = hidden_match(summary(revision=1), texts, "hedges")
    assert found == HiddenMatch("Original, Line Item 1", "Trim hedges", 0)
    texts = [line(2, 0, "Mow lawn"), notes(1, "Hedges next time")]
    found = hidden_match(summary(revision=2), texts, "hedges")
    assert found == HiddenMatch("R1, Notes", "Hedges next time", 1)


def test_hidden_match_is_the_newest_version_that_matched():
    texts = [
        line(2, 0, "Mow lawn"),
        notes(1, "Hedges, second pass"),
        line(0, 0, "Trim hedges"),
    ]
    found = hidden_match(summary(revision=2), texts, "hedges")
    assert found.revision == 1


def test_no_hidden_match_without_a_term():
    assert hidden_match(summary(), [notes(0, "Back hedges")], " ") is None
