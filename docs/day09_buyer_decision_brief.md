# Day 9 — Buyer decision brief

## Decision objective

Connect descriptive analysis, forecasting, inventory scenarios,
product-pair associations, and customer segments to reviewable actions.

## Scope boundaries

- Assortment: all countries, December 2010-November 2011.
- Forecasting: 20 selected SKUs, all countries.
- Inventory: static scenarios for that forecast cohort.
- Basket rules: UK baskets with the documented size filter.
- RFM: identified UK customers in the annual analysis window.

These outputs are not a single common population.
UK associations and customer behavior are not assumed to explain
all-country forecast errors.

## Proposed actions

| action_id | priority | finding | proposed_action |
| --- | --- | --- | --- |
| A01 | P1 | 825 A-class SKUs represent 21.77% of SKUs and 80.02% of gross sales. | Prioritize A-class products for availability and purchasing review. |
| A02 | P1 | mean_4_weeks: validation WAPE 56.15%; reserved-period WAPE 58.90%; bias -10.10%. | Retain the validation-selected method as a planning baseline. |
| A03 | P1 | Selected buffer 50%: coverage 86.44% versus 71.98%; surplus 28,320 units. | Review SKU-level buffers after obtaining operational inventory inputs. |
| A06 | P1 | Identified customers represent 83.13% of eligible UK gross sales. | Document coverage and investigate identity capture before broad targeting. |
| F01 | P1 | SKU 22197: 6,015 absolute error units; bias -49.28%. | Inspect large orders, credits, availability, and sales history. |
| F02 | P1 | SKU 84077: 3,796 absolute error units; bias 89.82%. | Inspect large orders, credits, availability, and sales history. |
| F03 | P1 | SKU 85123A: 3,002 absolute error units; bias -66.25%. | Inspect large orders, credits, availability, and sales history. |
| A04 | P2 | 1 of 9 selected policies reach the maximum tested buffer. | Document sensitivity and uncertainty before operational adoption. |
| A05 | P2 | Champions contributes 65.73% of identified-customer gross sales. | Protect availability of frequently purchased products; test relevant complementary-product recommendations. |
| X01 | P2 | 47590A -> 47590B: later confidence 69.1%, lift 58.46, shared baskets 38. | Review product compatibility and propose a randomized placement test. |
| X02 | P2 | 21668 -> 21669: later confidence 73.5%, lift 63.20, shared baskets 36. | Review product compatibility and propose a randomized placement test. |
| X03 | P2 | 22568 -> 22570: later confidence 28.7%, lift 32.20, shared baskets 33. | Review product compatibility and propose a randomized placement test. |

## Inventory sensitivity

| lead_weeks | protection_weeks | shortage_penalty | buffer_fraction | selection_grid_boundary |
| --- | --- | --- | --- | --- |
| 1 | 2 | 2.0 | 0.0 | False |
| 1 | 2 | 5.0 | 0.5 | False |
| 1 | 2 | 10.0 | 1.0 | True |
| 2 | 3 | 2.0 | 0.25 | False |
| 2 | 3 | 5.0 | 0.5 | False |
| 2 | 3 | 10.0 | 0.5 | False |
| 3 | 4 | 2.0 | 0.25 | False |
| 3 | 4 | 5.0 | 0.5 | False |
| 3 | 4 | 10.0 | 0.5 | False |

Penalty ratios are illustrative decision weights, not actual money.
Different protection periods cover different quantities and durations.
Compare buffers within the same scenario before comparing across scenarios.

## Delivery backlog

P1: validate data, investigate forecasting exceptions, and establish
operational inputs before purchasing decisions.

P2: prepare merchandising and customer experiments after prerequisite
availability, margin, and implementation checks.

Owners are proposed roles. No tasks have been assigned or messages sent.

## Evidence and claims

Every action references an existing aggregate output.
No inventory savings, campaign lift, or retention improvements are claimed.
Historical scenario assessment does not establish future performance.

## Review checklist

- Confirm the Day 7 and Day 8 interpretations are complete.
- Inspect the three largest forecasting exceptions.
- Review product descriptions for cross-selling compatibility.
- Confirm the scope of every proposed action.
- Identify operational inputs required before implementation.
- Record remaining uncertainties before the final business report.
