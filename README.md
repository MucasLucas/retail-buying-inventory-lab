# Retail Buying & Inventory Decision Lab

A retail analytics portfolio project translating transaction history into
assortment, replenishment, cross-selling, and customer decisions.

## Business questions

- Which SKUs deserve purchasing attention?
- How accurately can observed unit sales be forecast?
- How do inventory policies perform under explicit operating assumptions?
- Which products are candidates for cross-selling?
- Which customer groups drive repeat purchasing?

## Data sources and attribution

- Chen, D. (2015). Online Retail.
  UCI Machine Learning Repository.
  https://doi.org/10.24432/C5BW33
- Chen, D. (2012). Online Retail II.
  UCI Machine Learning Repository.
  https://doi.org/10.24432/C5CG6D

Both datasets are licensed under CC BY 4.0.

## Source policy

Online Retail II is the primary transaction history.
Online Retail is retained separately for overlapping-period reconciliation.
The two datasets are not appended together.

Raw records are preserved locally. Data files are excluded from Git.
Aggregate audits, source URLs, and workbook SHA-256 hashes are committed.

## Reproduce Day 1

Requires Python 3.11 or newer.

    python -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements-lock.txt
    .venv\Scripts\python.exe scripts/day01_ingest.py

## Analytical limitations

- Observed sales may understate demand when products are unavailable.
- Stock balances, supplier lead times, and purchase costs are unavailable.
- Inventory results will be scenarios, not measured operational savings.
- Basket associations do not establish incremental cross-selling effects.
- Customer analysis depends on records with usable customer identifiers.

## Progress

- Day 1: Source ingestion and audit.
- Day 2: Reconciled overlapping sources, classified all primary-source
  records, and created eligible merchandise sales with documented
  customer coverage and repeated-row sensitivity.
- Day 3: Built a 12-month SKU scorecard, gross-sales ABC classification,
  order-concentration flags, country mix, and assortment charts.
  - Day 4: Evaluated four weekly-sales baselines across three historical
  four-week validation windows for a cohort selected using prior data.
  Reserved a later four-week period for final model evaluation.
- Day 5: Compared a fixed Random Forest challenger with reproducible
  baselines, selected a method using validation WAPE, and evaluated
  the frozen selection on a reserved four-week period.
  - Day 6: Selected inventory buffers using historical validation forecasts
  and assessed coverage-versus-surplus trade-offs under explicit
  lead-time and shortage-penalty scenarios.
  - Day 7: Discovered directional product-pair associations in UK baskets
  and checked a frozen shortlist for later-period persistence.
  Framed persistent rules as cross-selling experiment candidates.
  - Day 8: Built tie-aware UK customer RFM segments, quantified
  customer-identification coverage and gross-sales concentration,
  and proposed segment-specific commercial experiments.