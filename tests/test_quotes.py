from datetime import date
from decimal import Decimal

from quote_builder.business import TaxPart, TaxRate
from quote_builder.customers import Customer
from quote_builder.quotes import (
    Extension,
    LineItem,
    LineTotals,
    Quote,
    QuoteTotals,
    Status,
    duplicate_draft,
    extend_tax_note,
    rate_changed_note,
    tax_change_note,
)

HOME = {"tax_rate_id": 1, "tax_name": "Home county"}


def home_at(percent):
    return TaxRate(1, "Home county", [TaxPart("", Decimal(percent))], id=1)


def before(revision=1, **tax):
    return Quote(business_id=1, number="Q-7KQ-M9XD", revision=revision, **tax)


def draft(**tax):
    return Quote(business_id=1, number="Q-7KQ-M9XD", revision=2, **tax)


def test_same_rate_same_percent_says_nothing():
    quoted = before(**HOME, tax_percent=Decimal("7.5"))
    assert tax_change_note(quoted, draft(**HOME, tax_percent=Decimal("7.50"))) is None


def test_both_untaxed_says_nothing():
    assert tax_change_note(before(), draft()) is None


def test_a_renamed_rate_at_the_same_percent_says_nothing():
    quoted = before(**HOME, tax_percent=Decimal("7.25"))
    renamed = draft(tax_rate_id=1, tax_name="Lake", tax_percent=Decimal("7.25"))
    assert tax_change_note(quoted, renamed) is None


def test_another_rate_at_the_same_percent_says_nothing():
    quoted = before(**HOME, tax_percent=Decimal("7.25"))
    other = draft(tax_rate_id=2, tax_name="Lake", tax_percent=Decimal("7.25"))
    assert tax_change_note(quoted, other) is None


def test_the_same_rate_at_a_new_percent():
    quoted = before(**HOME, tax_percent=Decimal("7.25"))
    assert (
        tax_change_note(quoted, draft(**HOME, tax_percent=Decimal("7.5")))
        == "Home county's rate changed since R1 was quoted: 7.25% to 7.5%"
    )


def test_the_first_version_goes_by_its_number():
    quoted = before(revision=0, **HOME, tax_percent=Decimal("7.25"))
    assert (
        tax_change_note(quoted, draft(**HOME, tax_percent=Decimal("7.5")))
        == "Home county's rate changed since Q-7KQ-M9XD was quoted: 7.25% to 7.5%"
    )


def test_another_rate_picked():
    quoted = before(**HOME, tax_percent=Decimal("7.25"))
    other = draft(tax_rate_id=2, tax_name="Other county", tax_percent=Decimal("6"))
    assert (
        tax_change_note(quoted, other)
        == "Tax changed since R1 was quoted: Home county 7.25% to Other county 6%"
    )


def test_untaxed_picked():
    quoted = before(**HOME, tax_percent=Decimal("7.25"))
    assert (
        tax_change_note(quoted, draft())
        == "Tax changed since R1 was quoted: Home county 7.25% to Untaxed"
    )


def test_a_rate_picked_on_an_untaxed_quote():
    assert (
        tax_change_note(before(), draft(**HOME, tax_percent=Decimal("7.25")))
        == "Tax changed since R1 was quoted: Untaxed to Home county 7.25%"
    )


def test_a_deleted_rate_on_a_draft_left_untaxed():
    gone = before(tax_name="Home county", tax_percent=Decimal("7.25"))
    assert (
        tax_change_note(gone, draft())
        == "Home county, which R1 was quoted at (7.25%), is no longer a tax rate."
    )


def test_a_deleted_rate_with_another_picked():
    gone = before(tax_name="Home county", tax_percent=Decimal("7.25"))
    other = draft(tax_rate_id=2, tax_name="Other county", tax_percent=Decimal("6"))
    assert (
        tax_change_note(gone, other)
        == "Tax changed since R1 was quoted: Home county 7.25% to Other county 6%"
    )


def test_a_quoted_quote_at_its_rate_says_nothing():
    quoted = before(**HOME, tax_percent=Decimal("7.5"))
    assert rate_changed_note(quoted, home_at("7.50")) is None
    assert extend_tax_note(quoted, home_at("7.50")) is None


def test_an_untaxed_quoted_quote_says_nothing():
    assert rate_changed_note(before(), None) is None
    assert extend_tax_note(before(), None) is None


def test_a_quoted_quotes_rate_changed():
    quoted = before(**HOME, tax_percent=Decimal("7.25"))
    assert (
        rate_changed_note(quoted, home_at("7.5"))
        == "Home county's rate changed since this was quoted: 7.25% to 7.5%"
    )
    assert extend_tax_note(quoted, home_at("7.5")) == (
        "Home county's rate changed since this was quoted: 7.25% to 7.5%. "
        "Extending keeps 7.25%. To use the new rate, revise instead."
    )


def test_extending_an_older_version_points_to_its_draft():
    quoted = before(revision=0, **HOME, tax_percent=Decimal("7.25"))
    newer = before(revision=1, **HOME, tax_percent=Decimal("7.5"))
    assert extend_tax_note(quoted, home_at("7.5"), newer) == (
        "Home county's rate changed since this was quoted: 7.25% to 7.5%. "
        "Extending keeps 7.25%. Draft R1 uses the new rate."
    )


def test_a_draft_on_another_rate_isnt_said_to_use_the_new_one():
    quoted = before(revision=0, **HOME, tax_percent=Decimal("7.25"))
    newer = before(
        revision=1, tax_rate_id=2, tax_name="Lake", tax_percent=Decimal("6")
    )
    assert extend_tax_note(quoted, home_at("7.5"), newer) == (
        "Home county's rate changed since this was quoted: 7.25% to 7.5%. "
        "Extending keeps 7.25%."
    )


def test_extending_an_older_version_with_its_rate_deleted():
    gone = before(revision=0, tax_name="Home county", tax_percent=Decimal("7.25"))
    assert extend_tax_note(gone, None, before(revision=1)) == (
        "Home county, which this was quoted at (7.25%), is no longer a tax rate. "
        "Extending keeps 7.25%."
    )


def test_a_quoted_quotes_rate_deleted():
    gone = before(tax_name="Home county", tax_percent=Decimal("7.25"))
    assert (
        rate_changed_note(gone, None)
        == "Home county, which this was quoted at (7.25%), is no longer a tax rate."
    )
    assert extend_tax_note(gone, None) == (
        "Home county, which this was quoted at (7.25%), is no longer a tax rate. "
        "Extending keeps 7.25%."
    )


def test_duplicate_draft_is_a_fresh_quote_keeping_the_changeable_parts():
    customer = Customer(business_id=1, name="Jane Doe")
    finalized = Quote(
        business_id=1,
        number="Q-7KQ-M9XD",
        revision=2,
        status=Status.QUOTED,
        issued_on=date(2026, 9, 1),
        valid_until=date(2026, 10, 1),
        notes="Front and back.",
        line_items=[
            LineItem("Mow lawn", Decimal(1), 4500, frozen=LineTotals(4500, 0, 326))
        ],
        tax_rate_id=1,
        tax_name="Home county",
        tax_percent=Decimal("7.25"),
        frozen=QuoteTotals(4500, 0, 326, 4826),
        extensions=[Extension(date(2026, 9, 15), date(2026, 10, 1), date(2026, 10, 31))],
        customer=customer,
    )
    copy = duplicate_draft(finalized)
    # A brand-new quote, not a revision, with nothing the finalized
    # version was given.
    assert copy.number is None
    assert copy.revision == 0
    assert copy.status is Status.DRAFT
    assert copy.issued_on is None and copy.valid_until is None
    assert copy.frozen is None
    assert copy.extensions == []
    assert copy.tax_name == "" and copy.tax_percent == Decimal(0)
    # Carried over, as changeable; the lines lose their frozen figures.
    assert copy.business_id == 1
    assert copy.notes == "Front and back."
    assert copy.tax_rate_id == 1
    assert copy.customer == customer
    assert copy.line_items == [LineItem("Mow lawn", Decimal(1), 4500)]
