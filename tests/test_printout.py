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


def test_shows_the_taxable_base_and_the_total():
    html = render_quote_html(a_quote(), BIZ)
    assert "Mow lawn" in html
    assert "Trim hedges" in html
    assert "Tax rate: Home county 7.25%" in html
    assert "Line Items" in html  # foot label, not bare "Items"
    assert "Taxes" in html  # foot total label, plural like the rest
    assert ", taxed" not in html  # tax is pooled at the foot, not per line
    assert "Taxable" in html and "$120.00" in html  # × 7.25% = Taxes
    assert "$128.70" in html  # 120.00 + 7.25% tax


def test_line_discounts_show_the_discounted_subtotal_and_taxable():
    # With line discounts, the foot carries Discounted Subtotal and the
    # Taxable base (× rate = Taxes); lines read plainly, no per-line tax.
    quote = a_quote(
        line_items=[
            LineItem("Widget A", Decimal(2), 4500, taxed=True,
                     discount_percent=Decimal("10")),  # $90 − $9 = $81
            LineItem("Widget B", Decimal(1), 4000, taxed=True,
                     discount_cents=500),  # $40 − $5 = $35
            LineItem("Consultation", Decimal(1), 5000,
                     discount_percent=Decimal("10")),  # $50 − $5 = $45
        ],
    )
    html = render_quote_html(quote, BIZ)
    assert ", taxed" not in html  # tax is pooled at the foot
    assert "Discounted Subtotal" in html and "$161.00" in html  # $180 − $19
    assert "Taxable" in html and "$116.00" in html  # taxed nets $81 + $35
    assert "$8.41" in html  # $116.00 × 7.25%
    assert "$169.41" in html  # $161.00 + $8.41


def test_shows_each_lines_quantity_with_its_unit():
    quote = a_quote(
        line_items=[
            LineItem("Labor", Decimal(2), 4500, unit="hour", taxed=True),
            LineItem("Trip fee", Decimal(1), 2000, unit="hour", taxed=True),
            LineItem("Filter", Decimal(3), 1200, unit="each", taxed=True),
        ],
    )
    html = render_quote_html(quote, BIZ)
    assert "2 hrs. × $45.00" in html  # plural
    assert "1 hr. × $20.00" in html  # singular
    assert "3 ea. × $12.00" in html


def test_a_percent_discount_shows_its_dollars_in_parentheses():
    # So a customer can check the discount without doing the math.
    quote = a_quote(
        line_items=[LineItem("Mow lawn", Decimal(2), 4500, discount_percent=Decimal(5))]
    )
    html = render_quote_html(quote, BIZ)
    assert "less 5% ($4.50)" in html  # 5% of $90.00


def test_a_flat_discount_stays_as_dollars():
    quote = a_quote(
        line_items=[LineItem("Mow lawn", Decimal(1), 4500, discount_cents=500)]
    )
    html = render_quote_html(quote, BIZ)
    assert "less $5.00" in html


def test_a_quote_discount_shows_once_in_the_foot_with_plain_lines():
    quote = a_quote(
        quote_discount_cents=2000,
        line_items=[
            LineItem("Widget A", Decimal(2), 4500, taxed=True),  # $90.00
            LineItem("Widget B", Decimal(3), 3700, taxed=True),  # $111.00
            LineItem("Consultation", Decimal(1), 5000),  # $50.00, untaxed
        ],
    )
    html = render_quote_html(quote, BIZ)
    assert "Quote Discount" in html
    assert "Discounts" not in html  # the line-discount row is gone
    # Lines read plainly: no per-line "taxed" or "less", just qty × price.
    assert "2 ea. × $45.00" in html
    assert ", taxed" not in html  # the per-line tax annotation is gone
    assert "$244.41" in html  # ($251 − $20) + $13.41 tax


def test_a_quote_discount_breaks_the_subtotal_down_in_the_foot():
    # The foot shows the discounted subtotal and its taxable/non-taxable
    # parts, so a customer can check the tax: taxable × rate = Taxes.
    quote = a_quote(
        quote_discount_cents=2000,
        line_items=[
            LineItem("Widget A", Decimal(2), 4500, taxed=True),  # $90.00
            LineItem("Widget B", Decimal(3), 3700, taxed=True),  # $111.00
            LineItem("Consultation", Decimal(1), 5000),  # $50.00, untaxed
        ],
    )
    html = render_quote_html(quote, BIZ)
    assert "Discounted Subtotal" in html and "$231.00" in html
    assert "Post Discount Untaxed" in html and "$46.02" in html
    assert "Post Discount Taxable" in html and "$184.98" in html
    # Post Discount Taxable sits just above Taxes.
    assert html.index("Post Discount Taxable") < html.index("Taxes")


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
