# Day 7 — Market basket analysis

## Scope

United Kingdom eligible merchandise sales.
Discovery: December 2010 through August 2011.
Confirmation: September through November 2011.

An invoice is one basket. Each SKU counts once per basket.
Baskets with more than 50 distinct eligible SKUs are excluded.
Single-SKU baskets remain in the denominator.
Customer identification is not required.

## Method

Candidate products are the top 200 discovery-period SKUs by basket count.
Only single-product-to-single-product directional rules are assessed.
All eligible retained baskets remain in support denominators,
including baskets without a candidate-vocabulary SKU.

Discovery requires at least 20 shared baskets, confidence at least
15%, and lift at least 1.5.

The top 20 passing rules are shortlisted by discovery lift,
then shared-basket count, with SKU codes breaking remaining ties.

Later persistence requires at least five shared baskets,
confidence at least 15%, and lift at least 1.2.

## Results

Discovery baskets: 10,174
Confirmation baskets: 5,161
Discovery rules passing thresholds: 1,551
Shortlisted directional rules: 20
Shortlisted rules persisting later: 20

## Limits

Associations do not establish incremental recommendation impact.
Lift is not a sales-uplift estimate.
Thresholds are screening rules, not statistical significance tests.
Repeated purchases by the same customer may influence associations.
Product availability, prices, and seasonal assortment can change.
Related product variants may dominate pairings.
The basket-size filter does not identify customer type.
A-to-B and B-to-A share a product pair but can have different confidence.
This later period was previously explored in other project analyses;
it is a temporal persistence check, not wholly unseen validation.

## Buyer interpretation to complete

- Select up to three persistent rules and describe their products.
- Explain support, confidence, and lift for each.
- Are these complementary products, variants, or related collections?
- What placement or recommendation experiment would you propose?
- What inventory and margin checks must happen before launch?

## Suggested experiment

For eligible shoppers viewing product A, randomly assign a product-B
recommendation or the existing experience. Measure product-B attachment,
overall conversion, and gross profit per eligible visitor if cost data
is available. Monitor availability and customer experience.

These historical rules prioritize experiments; they do not prove impact.
