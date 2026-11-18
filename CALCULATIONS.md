# Calculations

Every money figure the app shows, how it's worked out, and why. The
code lives in [money.py](src/quote_builder/money.py) (reading and
showing amounts) and [totals.py](src/quote_builder/totals.py) (the
math); this file is the plain-language companion, so a choice with tax
or legal weight is on the record. Figures are frozen onto a quote when
it's marked quoted and shown from then on, so a later rule change never
alters what a customer was given.

## Money, exactness, and rounding

- Money is whole **cents** as integers; quantities and percents are
  **`Decimal`**, read straight from the typed text. Never `float`: it
  can't hold most cents exactly (`0.1 + 0.2 != 0.3`).
- Rounding is **half up** (half a cent rounds up), as people expect on
  a bill, not Python's default half-even ("banker's rounding").
- Each line is worked out to the cent on its own, and the quote's foot
  adds up the lines' cents. So the foot always matches the lines; there
  is no separately-rounded grand total to disagree with them.

## A line

For one line, in order:

1. **Amount** = quantity × unit price, rounded to the cent.
2. **Line discount** (if any): an amount as given, or a percent of the
   amount, rounded to the cent. It can't be more than the line.
3. **Tax** (if the line is taxed): the quote's tax rate × (amount −
   line discount), rounded to the cent. An untaxed line, or any line on
   an untaxed quote, has no tax.
4. **Line total** = amount − line discount + tax.

Tax falls on the **discounted** amount — the customer is taxed on what
they actually pay for the taxable item, never on the pre-discount
figure.

## The foot

The quote's foot sums the lines: **Line Items** (the amounts before any
discount), the discount in play (see below), **Taxes**, and the
**Total**. A row for a discount shows only when that discount is used,
so the foot always reads cleanly.

## Discounts: one mode per quote

A quote can be discounted in one of two ways, **never both at once**:

- **Line discounts** — a discount on individual lines (step 2 above).
- **A Quote Discount** — one discount on the whole quote.

**Why one mode, not both.** Allowing both forces a whole-quote discount
to be split down onto each line's tax base, which drags in uneven-cent
division (a $10 discount over 3 lines isn't $3.33 × 3), the problem of
a per-line share larger than a small line, and per-line totals that no
longer add up on their own. Those "nooks and crannies" are a known
source of billing confusion. Worse, every extra allocation step is a
place to get a line's tax base wrong, and the result is hard for a
person to check or debug by hand — which is exactly where
over-collecting tax creeps in, the one error with real legal weight.
Keeping the two modes apart avoids all of it: tax is always figured one
simple way — once for the quote as a whole in Quote Discount mode (no
line carries a discount of its own), or on each line's own discounted
amount in line-discount mode. Both stay easy to verify and debug, which
keeps the risk of over-taxing to a minimum. The app refuses, on Save,
to use both on one quote.

The coupon case ("$10 off next time for the trouble") is still served:
check for it while drafting and use a Quote Discount on that quote.

## The Quote Discount

A Quote Discount is an amount (`$20`) or a percent (`10%`), applied
**before tax**. A percent is first worked out to dollars as that
percent of the subtotal (Line Items). The discount then comes off the
**taxable** and **non-taxable** parts of the quote in proportion to
each part's share of the subtotal, and tax falls on what's left of the
taxable part.

**Why proportional, and why before tax.** Before tax is the
tax-correct placement: the customer is taxed only on what they actually
pay for taxable goods, so the business never over-collects. Splitting
the discount in the same ratio as the goods is the neutral, defensible
treatment: the discount applies to the whole order, so each part shares
it by its size. (Taking the whole discount off the taxable part would
under-state tax; taking none off it would over-state tax.)

**The odd penny favors the customer.** When the proportional split
leaves a fractional cent, the extra penny goes to the **taxable**
side — a larger taxable discount, a slightly smaller taxable base,
hence tax rounded down by at most a cent, never up. Rounding the
customer's tax down (rather than up) is the conservative direction:
over-collecting tax is the riskier side, and any sub-penny shortfall is
the business's to absorb at filing, where tax is re-figured on total
sales for the period anyway. (This is general reasoning, not tax
advice; a few jurisdictions prescribe their own rounding, so it's worth
an accountant's confirm before release.)

**Validation.** A Quote Discount can't be more than the subtotal (it
can't drive the total below zero). A partial coupon that would exceed
the amount is the business user's to word on the quote.

**On the quote and printout.** With a Quote Discount, each line reads
plainly — `quantity × unit price = amount`, with no per-line "less" or
"taxed" — and the discount and tax show once each in the foot. (Without
one, a taxed line shows its own tax beside "taxed", for a line-by-line
check; a Quote Discount is a whole-quote figure, so that per-line
breakdown isn't shown.)

To keep the tax checkable even so, the foot then shows three more lines
below the Quote Discount: **Discounted Subtotal** (Line Items − Quote
Discount), and that subtotal split into **Post Discount Untaxed** and
**Post Discount Taxable**. Post Discount Taxable sits just above Taxes
because it's the figure tax is worked out on — a customer can multiply
it by the rate and land on the Taxes row. These three always show in
Quote Discount mode (an all-taxable quote simply reads $0.00 for Post
Discount Untaxed, and an all-untaxable one $0.00 for Post Discount
Taxable), so the foot is explicit rather than hiding rows.

**Why the two modes don't read alike.** It would look more uniform to
drop the per-line tax in line-discount mode as well, so that a line is
always pre-tax and tax always sits in the foot. We don't, on purpose: a
per-line tax lets a customer check any taxed line on its own —
quantity × price × (1 + rate), where the `1 + rate` (e.g. `1.0725`) is
a figure people reach for by habit — and that easy hand-check is worth
more than matching the two layouts. A Quote Discount can't offer the
same: its discount, and therefore its tax, is a whole-quote figure, not
a per-line one, so there the lines read plainly and tax is shown once
in the foot. So the two modes read differently because they *are*
different — one itemizes down to the line, the other discounts the
quote as a whole.

## Walkthrough

Tax rate **7.25%**, one flat **$20.00 Quote Discount**, a mix of
taxable and non-taxable lines:

| Line | Qty × Price | Amount | Taxable? |
|------|-------------|--------|----------|
| Widget A | 2 × $45.00 | $90.00 | yes |
| Widget B | 3 × $37.00 | $111.00 | yes |
| Consultation | 1 × $50.00 | $50.00 | no |

1. **Subtotal (Line Items)** = $90.00 + $111.00 + $50.00 = **$251.00**.
   Taxable part = $201.00; non-taxable part = $50.00.
2. **Split the $20.00** by each part's share of the subtotal:
   - Taxable's share = $20.00 × ($201.00 ÷ $251.00) = $16.0159… →
     **$16.02** (rounded up; the odd penny lands on the taxable side).
   - Non-taxable's share = $20.00 − $16.02 = **$3.98**.
3. **Taxable base after discount** = $201.00 − $16.02 = **$184.98**.
4. **Taxes** = 7.25% × $184.98 = $13.41105 → **$13.41**. (The customer
   is taxed on $184.98 — what they pay for the taxable goods after the
   discount — not on the $16.02 the discount removed.)
5. **Total** = ($251.00 − $20.00) + $13.41 = **$244.41**.

The foot:

```
Line Items               $251.00
Quote Discount           −$20.00
Discounted Subtotal       $231.00
Post Discount Untaxed      $46.02
Post Discount Taxable     $184.98
Taxes                     +$13.41
Total                     $244.41
```

Two hand-checks: $251.00 − $20.00 = $231.00 paid before tax, and
$231.00 + $13.41 = $244.41; and the $231.00 is $184.98 taxable +
$46.02 non-taxable, with 7.25% of only the $184.98 giving the $13.41.

A **percent** Quote Discount works the same way: find its dollar value
first (10% of $251.00 = $25.10), then run the same split-and-tax steps.
