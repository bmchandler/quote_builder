"""The printout HTML: render_quote_html, a pure function of a quote."""

from datetime import date
from decimal import Decimal

from quote_builder.business import Business, PrintedBusiness
from quote_builder.customers import Customer
from quote_builder.printout import render_quote_html
from quote_builder.quotes import LineItem, Quote, Status

BIZ = Business(
    id=1,
    name="John Doe's Lawn Service",
    address="12 Oak St\nSpringfield, IL 62704",
    phone="5551234567",
    ext="12",
    email="john@example.com",
    website="johnslawn.example.com",
    terms="Payment due within 30 days.",
)


def a_quote(**changes):
    base = dict(
        business_id=1,
        number="Q-9SK-D98H",
        status=Status.QUOTED,
        issued_on=date(2026, 11, 16),
        valid_until=date(2026, 12, 1),
        tax_rate_id=1,
        tax_name="Home county",
        tax_percent=Decimal("7.25"),
        line_items=[
            LineItem("Mow lawn", Decimal(1), 4500, taxed=True),
            LineItem("Trim hedges", Decimal("2.5"), 3000, taxed=True),
        ],
        notes="Front and back.",
        customer=Customer(business_id=1, name="Jane Doe", phone="5559876543"),
    )
    return Quote(**{**base, **changes})


def test_letterhead_shows_the_business_name_and_details():
    html = render_quote_html(a_quote(), BIZ)
    assert "John Doe's Lawn Service" in html
    assert "12 Oak St, Springfield, IL 62704" in html  # address on one line
    assert "(555) 123-4567 ext. 12" in html  # phone formatted
    assert "john@example.com" in html
    assert "johnslawn.example.com" in html


def test_shows_the_quote_heading_dates_and_customer():
    html = render_quote_html(a_quote(), BIZ)
    assert "Q-9SK-D98H" in html
    assert "Issued 11/16/2026" in html
    assert "Valid through 12/01/2026" in html
    assert "Prepared for" in html
    assert "Jane Doe" in html


def test_shows_lines_tax_and_the_total():
    html = render_quote_html(a_quote(), BIZ)
    assert "Mow lawn" in html
    assert "Trim hedges" in html
    assert "Tax rate: Home county 7.25%" in html
    assert "taxed $3.26" in html  # Mow lawn: $45.00 at 7.25%
    assert "taxed $5.44" in html  # Trim hedges: $75.00 at 7.25%
    assert "$128.70" in html  # 120.00 + 7.25% tax


def test_includes_terms_and_notes_when_present():
    html = render_quote_html(a_quote(), BIZ)
    assert "Payment due within 30 days." in html
    assert "Front and back." in html


def test_terms_sit_below_notes():
    # Terms are the bottom-most thing on the page.
    html = render_quote_html(a_quote(), BIZ)
    assert html.index("Notes") < html.index("Terms")


def test_omits_terms_and_notes_when_blank():
    html = render_quote_html(a_quote(notes=""), Business(id=1, name="Acme"))
    assert "Terms" not in html
    assert "Notes" not in html


def test_a_quote_without_a_customer_gets_a_handwrite_space():
    html = render_quote_html(a_quote(customer=None), BIZ)
    assert "Prepared for:" in html
    assert "writein" in html  # a ruled line to write a name on


def test_a_pilots_activity_name_is_the_from():
    # Decided 2026-11-16: a pilot's printout shows its activity name as
    # the From, like a business (no separate person name).
    html = render_quote_html(a_quote(), PrintedBusiness(name="Pressure washing"))
    assert "Pressure washing" in html


def test_an_untaxed_quote_says_so():
    html = render_quote_html(a_quote(tax_name="", tax_percent=Decimal(0)), BIZ)
    assert "Tax rate: Untaxed" in html


def test_user_text_is_escaped():
    html = render_quote_html(
        a_quote(line_items=[LineItem("A & B <tag>", Decimal(1), 100)]), BIZ
    )
    assert "A &amp; B &lt;tag&gt;" in html
    assert "<tag>" not in html


def test_the_page_asks_to_print_itself():
    html = render_quote_html(a_quote(), BIZ)
    assert "window.print()" in html
