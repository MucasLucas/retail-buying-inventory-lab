# Day 4 — Forecast evaluation protocol

## Scope

- Target: weekly eligible merchandise units, all countries.
- Weeks: Monday through Sunday.
- Horizon: four weeks, issued once at each origin.
- SKU cohort: 20 products selected before August 8, 2011.
- Ranking: previous 52 weeks of unit sales.
- Eligibility: sales in at least 26 of those weeks and
  at least four of the most recent eight weeks.
- Cohort remains fixed across validation folds.
- Missing SKU-week transactions represent zero observed sales.
- Repeated transaction lines remain preserved.

## Validation

Origins: August 8, September 5, and October 3, 2011.
Each forecast uses only observations preceding its origin.
Later origins may use actuals observed during earlier folds.

Baselines:
- Last observed week repeated.
- Mean of the last four weeks repeated.
- Mean of the last 13 weeks repeated.
- Corresponding week 52 weeks earlier.

Primary metric: WAPE across individual SKU-week forecast errors.
Positive bias means overforecasting.
MASE uses each SKU's pre-origin one-week naive MAE.
MASE is undefined when that denominator is zero.

Lowest validation WAPE baseline: mean_4_weeks.
This is a validation result, not a holdout result.

## Reserved evaluation period

October 31 through November 27, 2011.
Today's script does not score or select models using this period.
Day 3 descriptive analysis included these dates, so the period is
reserved for modeling rather than completely unseen exploration.

## Limitations

- Forecasts target observed sales, not unconstrained demand.
- Four weeks is a planning horizon, not an observed supplier lead time.
- The cohort favors established, frequently selling products.
- A 52-week lag is a benchmark, not proof of annual seasonality.
- Underforecast and overforecast units are forecast errors;
  they are not measured stockouts or excess inventory.
- The business and policy rules were defined retrospectively.
