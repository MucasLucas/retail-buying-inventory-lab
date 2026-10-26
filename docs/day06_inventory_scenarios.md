# Day 6 — Inventory planning scenarios

## Forecast input

Selected method: mean_4_weeks.
The 20-SKU cohort and forecast origin rules remain unchanged.

## Scenario assumptions

Review interval: one week.
Lead times: one, two, or three weeks.
Protection period: lead time plus review interval.
Candidate buffers: 0%, 25%, 50%, and 100%.
Shortage-to-surplus penalty ratios: 2:1, 5:1, and 10:1.

Penalty values are illustrative decision weights, not money.

## Inventory target

Target units = ceiling(protection-period forecast * (1 + buffer)).

The scenario starts with the target inventory available and assumes
no arrivals during the protection period. It is a static coverage
assessment, not a continuous replenishment simulation.

Uncovered units = max(observed units - target units, 0).
Surplus units = max(target units - observed units, 0).

## Selection and assessment

Buffers are selected using validation forecasts only.
Ties favor smaller buffers.
Reserved-period outcomes assess the selected policies.

A selected 100% buffer is the boundary of the tested grid.
It does not establish that 100% is the optimal buffer.

## Limits

The reserved period was already examined on Day 5.
This is retrospective scenario assessment, not a new independent test.

Only three validation origins are available.
Coverage is descriptive and does not establish a future service guarantee.
Penalty ratios are assumptions and unit costs are treated as equal.
Summed inventory targets across validation origins are scenario totals,
not measured simultaneous stock requirements.

Sales may be constrained by historical availability.
Uncovered units are not measured lost sales or stockouts.
Surplus units are not measured obsolete inventory.
Actual on-hand balances, open orders, backorders, supplier lead times,
case packs, and product costs are unavailable.

## Operational handoff

A real order calculation requires a validated inventory position:

Order quantity = max(0, target inventory - inventory position).

Inventory position requires usable on-hand stock, on-order stock,
and committed demand or backorders under the business's definitions.

## Buyer interpretation to complete

- How do selected buffers change with shortage penalties?
- What coverage and surplus result under the 5:1 assumption?
- Which SKUs contribute most uncovered units?
- Does any selected buffer reach the tested grid boundary?
- What operational data is required before issuing purchase orders?
