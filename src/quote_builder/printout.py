"""The printout: a quote as a standalone HTML page for the browser.

`render_quote_html` builds a self-contained page (its styles inline),
so it can be written to a file and opened in the user's default
browser, where Print offers Save as PDF. The page asks to print itself
on load. It renders from the quote and its business; once a quote's
details are frozen at Mark Quoted, those frozen copies will feed it
instead (planned; see REQUIREMENTS.md).

Layout A, the letterhead: the business's name and details centered at
the top, above the quote.
"""

from html import escape

from quote_builder.business import Business, PrintedBusiness
from quote_builder.dates import format_numeric_date
from quote_builder.money import format_discount, format_money
from quote_builder.phones import format_phone_ext
from quote_builder.quotes import Quote, version_name
from quote_builder.totals import shown_line_totals, shown_quote_totals
from quote_builder.units import format_quantity


def _esc(text: str) -> str:
    """Escape text for HTML body content, leaving quotes and apostrophes
    as they are (nothing here goes into an attribute, so a name like
    "John Doe's" stays readable)."""
    return escape(text, quote=False)

# Inline so the page stands alone (opened from a file, not the server).
_STYLE = """
  @media print { @page { margin: 18mm; } .no-print { display: none; } }
  body { background: #fff; color: #222; margin: 0; padding: 32px;
         font-family: Georgia, "Times New Roman", serif; }
  .sheet { max-width: 680px; margin: 0 auto; }
  .letterhead { text-align: center; }
  .biz-name { font-size: 20px; }
  .muted { color: #666; font-size: 12.5px; line-height: 1.5; }
  hr.rule { border: 0; border-top: 1px solid #ccc; margin: 14px 0; }
  .head { display: flex; justify-content: space-between; align-items: flex-start;
          gap: 24px; }
  .quote-title { font-size: 22px; font-weight: bold; }
  .right { text-align: right; }
  table.lines { width: 100%; border-collapse: collapse; margin-top: 18px;
                font-size: 13.5px; }
  table.lines th, table.lines td { text-align: left; padding: 7px 0;
                                   border-bottom: 1px solid #e3e3e3; }
  table.lines th.amt, table.lines td.amt { text-align: right; }
  table.lines thead th { font-family: Arial, sans-serif; font-size: 11px;
                         color: #777; text-transform: uppercase;
                         letter-spacing: .04em; }
  table.totals { width: 260px; margin-left: auto; margin-top: 10px;
                 font-size: 13.5px; }
  table.totals td { padding: 3px 0; }
  table.totals td.amt { text-align: right; }
  table.totals tr.grand td { font-weight: bold; font-size: 15px;
                             border-top: 1px solid #ccc; padding-top: 6px; }
  .section-h { font-family: Arial, sans-serif; font-size: 11px; color: #777;
               text-transform: uppercase; letter-spacing: .04em; margin: 22px 0 4px; }
  .terms, .notes { font-size: 12.5px; color: #444; white-space: pre-wrap; }
  /* A quote with no customer: a label and a line to write a name on. */
  .prepared { margin: 10px 0 0; }
  .writein { border-bottom: 1px solid #999; height: 22px; width: 60%;
             margin-top: 4px; }
  .toolbar { text-align: center; margin-bottom: 18px; }
  /* The app's primary blue, so the printout matches the window. */
  .toolbar button { font: inherit; padding: 7px 16px; cursor: pointer;
                    background: #5898d4; color: #fff; border: 0;
                    border-radius: 4px; }
  .toolbar button:hover { background: #4e86bd; }
"""


def _one_line_address(address: str) -> str:
    """An address as one line: its lines joined with commas, blanks dropped."""
    return ", ".join(line.strip() for line in address.splitlines() if line.strip())


def _business_details(business: Business | PrintedBusiness) -> str:
    """The business's contact details on one line, present parts only."""
    parts = [
        _one_line_address(business.address),
        format_phone_ext(business.phone, business.ext),
        business.email,
        business.website,
    ]
    return " · ".join(part for part in parts if part.strip())


def _customer_block(quote: Quote) -> str:
    """The "Prepared for" block: the customer's details, or a label and a
    ruled line to write a name by hand when the quote has no customer."""
    customer = quote.customer
    if customer is None or not (customer.name or customer.details):
        return "<p class='prepared'>Prepared for:</p><div class='writein'></div>"
    name = f"<b>{_esc(customer.name)}</b>" if customer.name else ""
    lead = "Prepared for " if customer.name else "Prepared for:"
    details = (
        f"<br><span class='muted'>{_esc(customer.details)}</span>"
        if customer.details
        else ""
    )
    return f"<p>{lead}{name}{details}</p>"


def _lines_rows(quote: Quote) -> str:
    rows = []
    for item in quote.line_items:
        line_totals = shown_line_totals(item, quote.tax_percent)
        qty = format_quantity(item.quantity, item.unit)
        qty_price = f"{qty} × {format_money(item.unit_price_cents)}"
        if discount := format_discount(item.discount_cents, item.discount_percent):
            qty_price += f", less {discount}"
        if item.taxed:
            # The line's own tax beside "taxed", so a customer can check the
            # figures add up (no parentheses, to read like the rest).
            qty_price += f", taxed {format_money(line_totals.tax_cents)}"
        rows.append(
            f"<tr><td>{_esc(item.description)}</td>"
            f"<td>{_esc(qty_price)}</td>"
            f"<td class='amt'>{format_money(line_totals.total_cents)}</td></tr>"
        )
    return "".join(rows)


def _totals_rows(quote: Quote) -> str:
    totals = shown_quote_totals(quote)
    rows = [
        ("Items", totals.items_cents),
        ("Discounts", -totals.discount_cents),
        ("Tax", totals.tax_cents),
    ]
    body = "".join(
        f"<tr><td>{label}</td><td class='amt'>{format_money(cents)}</td></tr>"
        for label, cents in rows
    )
    body += (
        "<tr class='grand'><td>Total</td>"
        f"<td class='amt'>{format_money(totals.total_cents)}</td></tr>"
    )
    return body


def render_quote_html(quote: Quote, business: Business | PrintedBusiness) -> str:
    """A standalone HTML page for `quote`, in the letterhead layout.

    `business` is the frozen snapshot on a finalized quote, or the live
    business for a draft; both carry the same detail fields.
    """
    title = version_name(quote.number, quote.revision) if quote.number else "Quote"
    name = _esc(business.name) if business.name else "Quote"
    details = _business_details(business)
    details_html = f"<div class='muted'>{_esc(details)}</div>" if details else ""

    dates = ""
    if quote.issued_on and quote.valid_until:
        dates = (
            f"<div class='muted right'>Issued {format_numeric_date(quote.issued_on)}"
            f"<br>Valid through {format_numeric_date(quote.valid_until)}</div>"
        )

    tax = f"Tax rate: {_esc(quote.tax_name)} {quote.tax_percent}%" if quote.tax_name \
        else "Tax rate: Untaxed"

    terms = (
        f"<div class='section-h'>Terms</div><div class='terms'>"
        f"{_esc(business.terms)}</div>"
        if business.terms.strip()
        else ""
    )
    notes = (
        f"<div class='section-h'>Notes</div><div class='notes'>"
        f"{_esc(quote.notes)}</div>"
        if quote.notes.strip()
        else ""
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{_esc(title)}</title>
<style>{_STYLE}</style>
</head>
<body>
<div class="sheet">
  <div class="toolbar no-print">
    <button onclick="window.print()">Print / Save as PDF</button>
  </div>
  <div class="letterhead">
    <div class="biz-name">{name}</div>
    {details_html}
  </div>
  <hr class="rule">
  <div class="head">
    <div><span class="quote-title">{_esc(title)}</span></div>
    {dates}
  </div>
  {_customer_block(quote)}
  <div class="muted">{tax}</div>
  <table class="lines">
    <thead><tr><th>Description</th><th>Qty × Price</th>
      <th class="amt">Amount</th></tr></thead>
    <tbody>{_lines_rows(quote)}</tbody>
  </table>
  <table class="totals">{_totals_rows(quote)}</table>
  {notes}
  {terms}
</div>
<script>window.addEventListener("load", function () {{ window.print(); }});</script>
</body>
</html>
"""
