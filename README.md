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