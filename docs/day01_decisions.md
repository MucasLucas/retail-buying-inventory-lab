# Day 1 — Ingestion decisions

## Decisions

1. Use Online Retail II as the primary transaction history.
2. Keep Online Retail separate for overlap reconciliation.
3. Preserve all rows during ingestion.
4. Preserve workbook, sheet, and Excel row provenance.
5. Store identifiers as strings.
6. Record source hashes and resolved Python dependencies.
7. Keep transaction-level data out of Git.

## Observations

Complete these after inspecting the generated audits:

- Observed date coverage:
- Missing customer ID count and percentage:
- Cancellation-prefix count:
- Nonpositive-price count:
- Repeated business-row count:

## Buyer interpretation

Explain in two sentences how these issues could distort purchasing
quantities or customer analysis.

## Day 2 handoff

Reconcile the overlapping sources and define explicit rules for
merchandise sales, cancellations, adjustments, and repeated lines.