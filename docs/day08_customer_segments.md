# Day 8 — Customer RFM segmentation

## Scope

Country: United Kingdom.
Purchase window: December 1, 2010 through November 30, 2011.
Snapshot: December 1, 2011.

Identified customers: 3,882.
Eligible UK gross sales: GBP 8,174,883.82.
Identified-customer gross sales: GBP 6,795,530.42.
Identified share of eligible UK gross sales:
83.13%.

## Definitions

Recency: calendar days since the last eligible purchase.
Frequency: distinct eligible purchase invoices.
Monetary: eligible gross merchandise sales before credits.

Missing customer IDs are excluded from segmentation but remain in
the coverage denominator. No missing IDs are imputed.

Scores use average-rank percentiles on a 1-to-5 scale.
Higher scores indicate stronger observed purchasing behavior.
Tied values receive identical scores, so score groups need not
contain exactly 20% of customers and some scores may be absent.

## Segment rules in priority order

- Champions: R >= 4, F >= 4, M >= 4.
- Recent repeat buyers: R >= 4, F >= 3, after Champions.
- Recent low-frequency buyers: R >= 4, F <= 2.
- High-frequency buyers at risk: R <= 2, F >= 4.
- High-value buyers at risk: R <= 2, M >= 4, after the prior rule.
- Other inactive buyers: remaining R <= 2.
- Developing buyers: all remaining customers.

Labels are relative behavioral descriptions, not verified lifecycle
states. A low-frequency buyer is not necessarily newly acquired.

## Concentration

The top 389 identified customers by gross sales account for
58.45% of identified gross sales.
This is gross-sales concentration, not profit or lifetime value.

## Limits

Credits are not subtracted from monetary value.
Large purchases can dominate gross monetary scores.
Customer identity quality limits segmentation.
The scores and segments are descriptive, not predictions.
No campaign response or retention improvement has been measured.
Earlier purchases outside the analysis window are not represented.

## Buyer interpretation to complete

- Which segment contributes the largest share of gross sales?
- Which segment has the largest customer share?
- What action would you test for recent repeat buyers?
- What investigation would you prioritize for at-risk buyers?
- How does missing customer identification limit the analysis?

## Experiment proposal

Choose one segment and randomly assign an eligible intervention
or the existing experience. Measure incremental repeat purchase
and gross sales per assigned customer over a fixed follow-up period.
Include margin and campaign costs when those inputs are available.
