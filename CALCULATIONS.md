# Calculations

Every money figure the app shows, how it's worked out, and why. The
code lives in [money.py](src/quote_builder/money.py) (reading and
showing amounts) and [totals.py](src/quote_builder/totals.py) (the
math); this file is the plain-language companion, so a choice with tax
or legal weight is on the record. Figures are frozen onto a quote when
it's marked quoted and shown from then on, so a later rule change never
alters what a customer was given.

If a business user is puzzled by how a quote's discounts or tax are
worked out, this is the file to point them to — jump to
[Line-Item Discount mode](#line-item-discount-mode) or
[Quote Discount mode](#quote-discount-mode) for the row-by-row list and
a worked example.

## Money, exactness, and rounding

- Money is whole **cents** as integers; quantities and percents are
  **`Decimal`**, read straight from the typed text. Never `float`: it
  can't hold most cents exactly (`0.1 + 0.2 != 0.3`).
- Rounding is **half up** (half a cent rounds up), as people expect on
  a bill, not Python's default half-even ("banker's rounding").
- Amounts and discounts are worked out **per line** to the cent and
  summed; **tax is figured once** on the pooled taxable base (see
  [Tax](#tax)), not per line. So every figure in the foot reconciles
  exactly: Line Items − discounts + Taxes = Total, and the shown
  **Taxable × rate = Taxes**.

## A line

For one line, in order:

1. **Amount** = quantity × unit price, rounded to the cent.
2. **Line discount** (if any): an amount as given, or a percent of the
   amount, rounded to the cent. It can't be more than the line.
3. **Net** = amount − line discount. This is the line's figure on the
   quote; it carries no tax of its own (see [Tax](#tax)).

A line reads plainly — `qty × price, less any discount = net` — so what
the customer sees on a line never depends on the tax rate.

## Tax

Tax is figured **once for the whole quote**, not per line: the
**taxable base** (the part of the quote that's taxed, after discounts) ×
the quote's rate, rounded to the cent. A quote with no rate (Untaxed),
or with nothing taxable, has no tax.

**Why pooled, not per line.** Pooling is what lets a customer check the
tax with one multiplication: the foot shows the taxable base as
**Taxable**, and `Taxable × rate = Taxes` exactly. Taxing each line and
summing (`round(a × rate) + round(b × rate) + …`) is **not** the same as
taxing the pooled base (`round((a + b + …) × rate)`) — the two can
differ by a cent or two, so a per-line method couldn't be checked
against a single Taxable row. For example, two taxed lines of $10.00
each: per line, `$0.725 → $0.73` twice = **$1.46**; pooled,
`$20.00 × 7.25% = $1.45`.

Pooled rounding is **per-invoice** rounding, a standard US method on the
combined state and local rate. (A few states use bracket tables —
Maryland, Alabama in part — which aren't supported.) This is general
reasoning, not tax advice: a quote isn't the filed return — the
business reconciles real tax at filing on the period's totals — and
it's worth an accountant's confirm before release.

## The foot

The quote's foot shows: **Line Items** (the amounts before any
discount), the discount in play (only the one used), a small breakdown
that makes the tax checkable (differs by mode, below), **Taxes**, and
the **Total**. A row shows only when it applies, so the foot always
reads cleanly.

## One discount mode per quote

A quote can be discounted in one of two ways, **never both at once**:

- **Line discounts** — a discount on individual lines.
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
simple way, once on a single taxable base — the taxed lines' nets in
line-discount mode, or the taxable part after the split in Quote
Discount mode. Both stay easy to verify, which keeps the risk of
over-taxing to a minimum. The app refuses, on Save, to use both on one
quote.

The coupon case ("$10 off next time for the trouble") is still served:
check for it while drafting and use a Quote Discount on that quote.

Both modes read the same way on the quote — lines plainly, tax once in
the foot — so they differ only in **where the discount is entered**
(per line, or one figure for the whole quote).

## Line-Item Discount mode

The common mode: each line can carry its own discount, and many quotes
carry none at all. The foot:

- **Line Items** — the amounts before any discount.
- **Discounts** — the sum of the line discounts. *Shown only when there
  are discounts*, so a business that never discounts sees a plain foot.
- **Discounted Subtotal** — Line Items − Discounts. *Shown only when
  there are discounts.*
- **Taxable** — the taxed lines' nets (amount − that line's discount),
  added up. `Taxable × rate = Taxes`. *Shown only when there's tax*; an
  all-services quote just reads Taxes $0.00. (There's no "Untaxed" row
  here, to keep this common mode's foot minimal.)
- **Taxes**, then **Total**.

**Example.** Tax rate **7.25%**, line discounts, a mix of taxable and
non-taxable lines:

| Line | Qty × Price | Amount | Discount | Net | Taxed? |
|------|-------------|--------|----------|-----|--------|
| Widget A | 2 × $45.00 | $90.00 | less 10% (−$9.00) | $81.00 | yes |
| Widget B | 1 × $40.00 | $40.00 | less $5.00 | $35.00 | yes |
| Consultation | 1 × $50.00 | $50.00 | less 10% (−$5.00) | $45.00 | no |

1. **Line Items** = $90.00 + $40.00 + $50.00 = **$180.00**.
2. **Discounts** = $9.00 + $5.00 + $5.00 = **$19.00**.
3. **Discounted Subtotal** = $180.00 − $19.00 = **$161.00** (the nets:
   $81.00 + $35.00 + $45.00).
4. **Taxable** = the taxed nets only = $81.00 + $35.00 = **$116.00**
   (Consultation's $45.00 is untaxed, so it's not here).
5. **Taxes** = 7.25% × $116.00 = $8.41 ($8.41105 → $8.41).
6. **Total** = $161.00 + $8.41 = **$169.41**.

The foot:

```
Line Items            $180.00
Discounts             −$19.00
Discounted Subtotal   $161.00
Taxable               $116.00
Taxes                  +$8.41
Total                 $169.41
```

Hand-checks: Discounted Subtotal − Taxable = $161.00 − $116.00 =
**$45.00**, exactly the untaxed line's net; and $116.00 × 7.25% =
**$8.41**, the Taxes row.

## Quote Discount mode

One discount on the whole quote, as an amount (`$20`) or a percent
(`10%`), applied **before tax**. A percent is first worked out to
dollars as that percent of the subtotal (Line Items). The discount then
comes off the **taxable** and **non-taxable** parts of the quote in
proportion to each part's share of the subtotal, and tax falls on
what's left of the taxable part. With a Quote Discount the lines carry
no discount of their own, so they read plainly (`qty × price = amount`).

The foot:

- **Line Items** — the amounts before the discount.
- **Quote Discount** — the whole-quote discount, in dollars.
- **Discounted Subtotal** — Line Items − Quote Discount.
- **Post Discount Untaxed** — the non-taxable part of that subtotal.
- **Post Discount Taxable** — the taxable part; `× rate = Taxes`. Sits
  just above Taxes.
- **Taxes**, then **Total**.

These breakdown rows **always show** in Quote Discount mode (an
all-taxable quote simply reads $0.00 for Post Discount Untaxed, and an
all-untaxable one $0.00 for Post Discount Taxable), so the foot is
explicit rather than hiding rows.

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
sales for the period anyway.

**Validation.** A Quote Discount can't be more than the subtotal (it
can't drive the total below zero). A partial coupon that would exceed
the amount is the business user's to word on the quote.

**Example.** Tax rate **7.25%**, one flat **$20.00 Quote Discount**, a
mix of taxable and non-taxable lines:

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
3. **Post Discount Taxable** = $201.00 − $16.02 = **$184.98**.
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

Hand-checks: $251.00 − $20.00 = $231.00 paid before tax, and
$231.00 + $13.41 = $244.41; and the $231.00 is $184.98 taxable +
$46.02 non-taxable, with 7.25% of only the $184.98 giving the $13.41.

A **percent** Quote Discount works the same way: find its dollar value
first (10% of $251.00 = $25.10), then run the same split-and-tax steps.
For a percent, the split is identical to taking that percent off every
line, so it only differs from "that percent off each line" when the
discount is a flat dollar amount.
