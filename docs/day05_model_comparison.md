# Day 5 — Forecast model comparison

## Protocol

The same 20-SKU cohort and validation origins from Day 4 are used.
A pooled Random Forest predicts each horizon using horizon indicators,
SKU identity, historical sales features, and known calendar features.

Each training target week must finish before its forecast origin.
No realized sales inside a forecast horizon enter its input features.

The Random Forest configuration is fixed.
Selection uses validation WAPE, with ties favoring baselines.
Day 4 baseline predictions are checked for reproducibility.

## Selection

Selected method: mean_4_weeks

Best validation baseline: mean_4_weeks

## Validation metrics

                model  sku_week_forecasts  actual_units  predicted_units  absolute_error_units  mae_units   wape_pct  bias_pct  underforecast_units  overforecast_units  mean_mase  mase_scored_rows  is_challenger
         mean_4_weeks                 240      133520.0    126263.000000          74973.500000 312.389583  56.151513 -5.435141         41115.250000        33858.250000   0.852063               240          False
        mean_13_weeks                 240      133520.0    122858.769231          77554.153846 323.142308  58.084297 -7.984744         44107.692308        33446.461538   0.877377               240          False
        random_forest                 240      133520.0    139705.514975          81880.339110 341.168080  61.324400  4.632651         37847.412067        44032.927043   0.960322               240           True
            last_week                 240      133520.0    135188.000000         106544.000000 443.933333  79.796285  1.249251         52438.000000        54106.000000   1.181201               240          False
    seasonal_52_weeks                 240      133520.0    187305.000000         135981.000000 566.587500 101.843170 40.282355         41098.000000        94883.000000   1.418030               240          False

## Reserved-period metrics

October 31 through November 27, 2011.

           model  sku_week_forecasts  actual_units  predicted_units  absolute_error_units  mae_units  wape_pct   bias_pct  underforecast_units  overforecast_units  mean_mase  mase_scored_rows
    mean_4_weeks                  80       58479.0          52574.0               34443.0   430.5375 58.898066 -10.097642              20174.0             14269.0   1.130767                80

If a baseline wins validation, only that method appears in the
reserved-period comparison. Model selection is not changed based on
reserved-period results.

## Interpretation limits

These are observed-sales forecasts, not unconstrained demand forecasts.
Forecast errors do not measure actual stockouts, excess stock, or savings.
Results apply to the selected established-SKU cohort.
The reserved period was included in earlier descriptive exploration.

MASE uses the historical one-week naive error scale.
It does not directly compare against the four-week baseline's WAPE.

## Buyer interpretation to complete

- Selected method and validation rationale:
- Reserved-period WAPE and bias:
- Does the result support using the more complex method?
- Which SKUs have the largest reserved-period errors?
- What does this imply for purchasing review and inventory buffers?

Do not tune against this reserved period after reviewing its results.
