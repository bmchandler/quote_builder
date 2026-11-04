from datetime import UTC, datetime

import pytest

from quote_builder.quotes import QuoteSummary, SearchText, Status
from quote_builder.search import (
    MARK_CLASS,
    HiddenMatch,
    excerpt,
    hidden_match,
    highlight,
    highlight_details,
    highlight_phone,
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


def test_highlight_phone_marks_the_matched_digit_run():
    # A run that spans separators is marked whole, separators included.
    assert highlight_phone("(123) 456-7890", "4567890") == (
        f"(123) {MARK}456-7890</mark>"
    )
    assert highlight_phone("(123) 456-7890", "456") == f"(123) {MARK}456</mark>-7890"
    # The run spans from the first matched digit to the last, so the
    # leading "(" stays outside the mark.
    assert highlight_phone("(123) 456-7890", "1234567890") == (
        f"({MARK}123) 456-7890</mark>"
    )


def test_highlight_phone_without_a_digit_match_is_plain():
    assert highlight_phone("(123) 456-7890", "999") == "(123) 456-7890"
    assert highlight_phone("(123) 456-7890", "jane") == "(123) 456-7890"


def test_highlight_details_marks_the_phone_by_digits_and_the_rest_as_typed():
    details = "12 Oak St · (123) 456-7890 · jane@example.com"
    # A digit run that spans separators marks the phone, nothing else.
    assert highlight_details(details, "4567890") == (
        f"12 Oak St · (123) {MARK}456-7890</mark> · jane@example.com"
    )
    # A non-phone term still marks its text.
    assert highlight_details(details, "oak") == (
        f"12 {MARK}Oak</mark> St · (123) 456-7890 · jane@example.com"
    )


def test_highlight_details_without_a_phone_falls_back_to_plain_highlight():
    assert highlight_details("jane@example.com", "jane") == f"{MARK}jane</mark>@example.com"


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


def customer(revision, position, text):
    return SearchText(revision, "customer", position, text)


def test_hidden_match_in_the_customers_details():
    texts = [customer(0, 0, "Jane Doe"), customer(0, 3, "12 Oak St")]
    found = hidden_match(summary(customer_name="Jane Doe"), texts, "oak")
    assert found == HiddenMatch("Customer", "12 Oak St", 0)


def test_hidden_match_in_a_phone_matches_by_digits_and_shows_formatted():
    # The phone is stored as digits (position 2); a search of its digits,
    # punctuated however, finds it, and the excerpt shows it formatted.
    texts = [customer(0, 2, "1234560134")]
    for term in ("0134", "(123) 456-0134", "1234560134"):
        found = hidden_match(summary(customer_name="Jane Doe"), texts, term)
        assert found == HiddenMatch("Customer", "(123) 456-0134", 0, is_phone=True)


def test_no_hidden_phone_match_for_a_text_search():
    texts = [customer(0, 2, "1234560134")]
    assert hidden_match(summary(customer_name="Jane Doe"), texts, "jane") is None


def test_hidden_match_in_an_older_versions_customer():
    texts = [customer(1, 0, "Jane Smith"), customer(0, 0, "Jane Doe")]
    found = hidden_match(summary(revision=1, customer_name="Jane Smith"), texts, "doe")
    assert found == HiddenMatch("Original, Customer", "Jane Doe", 0)


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
