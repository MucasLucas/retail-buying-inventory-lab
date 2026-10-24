# Day 2 — Reconciliation and transaction treatment

## Source reconciliation

- Overlap start: [result]
- Overlap end: [result]
- Exact match including repeated-row counts: [True/False]
- Reference unmatched rows: [result]
- Primary unmatched rows: [result]

Online Retail II remains the primary transaction history.
Online Retail is used for validation and is not appended.

## Transaction rules

Rows receive one disposition using this priority:

1. Missing required transaction fields.
2. Cancellation or credit invoice.
3. Negative quantity requiring review.
4. Zero quantity.
5. Nonpositive unit price.
6. Nonstandard stock code requiring review.
7. Eligible merchandise sale.

Merchandise eligibility provisionally requires a five-digit stock code
with an optional alphabetic suffix.

Missing customer IDs do not exclude otherwise eligible product sales.
Missing descriptions are flagged without excluding an otherwise eligible SKU.

Repeated business rows are preserved in the primary analysis.
A second scenario measures the effect of removing repetitions.

## Findings

- Eligible merchandise-sale rows: [result]
- Eligible gross sales in GBP: [result]
- Cancellation-or-credit rows: [result]
- Stock codes requiring review: [count and notable examples]
- Gross sales with customer identification as a percentage of
  all eligible gross sales: [result]
- Difference in gross sales when repeated rows are removed: [result]

## Buyer implications

- Purchasing quantities: [one evidence-based implication]
- Assortment eligibility: [one implication from stock-code review]
- Customer analysis coverage: [one evidence-based limitation]

## Limitations

Eligible sales measure observed purchases, not unconstrained demand.
Gross sales exclude the effect of separately classified credits.
Credit transactions are not matched to original purchases.
Stock-code eligibility remains provisional pending catalog review.
Customer records are not classified as wholesale or consumer.
No inventory availability, purchase costs, or supplier lead times exist.

## Day 3 handoff

Proceed after overlap differences and questionable stock codes have
been reviewed. Use merchandise_sales.parquet for commercial EDA,
retaining the documented repeated-row policy.