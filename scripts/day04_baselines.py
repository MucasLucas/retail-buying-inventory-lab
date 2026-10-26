"""Evaluate four-week SKU sales forecasts using historical baselines."""

from pathlib import Path
import json

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "reports" / "tables"
FIGURES = ROOT / "reports" / "figures"
DOCS = ROOT / "docs"

# All intervals are Monday through Sunday.
FIRST_WEEK = pd.Timestamp("2009-12-07")
SELECTION_DATE = pd.Timestamp("2011-08-08")
HOLDOUT_START = pd.Timestamp("2011-10-31")
HOLDOUT_END_EXCLUSIVE = pd.Timestamp("2011-11-28")

ORIGINS = [
    pd.Timestamp("2011-08-08"),
    pd.Timestamp("2011-09-05"),
    pd.Timestamp("2011-10-03"),
]

HORIZON = 4
TOP_N = 20

MODELS = [
    "last_week",
    "mean_4_weeks",
    "mean_13_weeks",
    "seasonal_52_weeks",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def baseline_predictions(
    train: pd.Series,
    future_weeks: pd.DatetimeIndex,
) -> dict:
    """Issue all horizon predictions using only pre-origin history."""
    require(
        len(train) >= 52,
        "At least 52 historical weeks are required.",
    )

    seasonal_dates = future_weeks - pd.Timedelta(weeks=52)

    require(
        seasonal_dates.isin(train.index).all(),
        "Seasonal baseline dates are missing from training history.",
    )

    return {
        "last_week": np.repeat(float(train.iloc[-1]), HORIZON),
        "mean_4_weeks": np.repeat(
            float(train.iloc[-4:].mean()), HORIZON
        ),
        "mean_13_weeks": np.repeat(
            float(train.iloc[-13:].mean()), HORIZON
        ),
        "seasonal_52_weeks": train.reindex(
            seasonal_dates
        ).to_numpy(dtype=float),
    }


def metrics(frame: pd.DataFrame) -> dict:
    error = frame["prediction"] - frame["actual"]
    actual_total = float(frame["actual"].sum())
    absolute_error = float(error.abs().sum())

    return {
        "sku_week_forecasts": len(frame),
        "actual_units": actual_total,
        "predicted_units": float(frame["prediction"].sum()),
        "absolute_error_units": absolute_error,
        "mae_units": float(error.abs().mean()),
        "wape_pct": (
            100 * absolute_error / actual_total
            if actual_total > 0 else np.nan
        ),
        # Positive bias means overforecasting.
        "bias_pct": (
            100 * float(error.sum()) / actual_total
            if actual_total > 0 else np.nan
        ),
        "underforecast_units": float(
            (-error).clip(lower=0).sum()
        ),
        "overforecast_units": float(
            error.clip(lower=0).sum()
        ),
        "mean_mase": float(frame["scaled_absolute_error"].mean()),
        "mase_scored_rows": int(
            frame["scaled_absolute_error"].notna().sum()
        ),
    }


def summarize(
    predictions: pd.DataFrame,
    group_columns: list[str],
) -> pd.DataFrame:
    rows = []

    for key, frame in predictions.groupby(group_columns):
        if not isinstance(key, tuple):
            key = (key,)

        row = dict(zip(group_columns, key))
        row.update(metrics(frame))
        rows.append(row)

    return pd.DataFrame(rows)


def main() -> None:
    for folder in [TABLES, FIGURES, DOCS]:
        folder.mkdir(parents=True, exist_ok=True)

    reconciliation = pd.read_csv(
        TABLES / "day02_overlap_reconciliation.csv"
    )

    require(
        not reconciliation.empty
        and reconciliation["reconciliation_accepted"]
        .astype(str).str.lower().eq("true").all(),
        "Day 2 reconciliation must pass before forecasting.",
    )

    sales = pd.read_parquet(
        ROOT / "data" / "processed" / "merchandise_sales.parquet"
    )

    # Do not use reserved-period sales in today's analysis.
    development = sales.loc[
        sales["InvoiceDate"].ge(FIRST_WEEK)
        & sales["InvoiceDate"].lt(HOLDOUT_START)
    ].copy()

    development["week"] = (
        development["InvoiceDate"]
        .dt.to_period("W-SUN")
        .dt.start_time
    )

    final_development_week = (
        HOLDOUT_START - pd.Timedelta(weeks=1)
    )
    calendar = pd.date_range(
        FIRST_WEEK,
        final_development_week,
        freq="W-MON",
    )

    # Select candidates using only the year before the first origin.
    selection_start = (
        SELECTION_DATE - pd.Timedelta(weeks=52)
    )
    selection_rows = development.loc[
        development["InvoiceDate"].ge(selection_start)
        & development["InvoiceDate"].lt(SELECTION_DATE)
    ]

    selection_calendar = pd.date_range(
        selection_start,
        periods=52,
        freq="W-MON",
    )

    candidate_weekly = (
        selection_rows.groupby(["week", "StockCode"])["Quantity"]
        .sum()
        .unstack("StockCode")
        .reindex(selection_calendar)
        .fillna(0)
    )

    require(
        not candidate_weekly.empty,
        "No sales available for pre-origin SKU selection.",
    )

    candidates = pd.DataFrame({
        "StockCode": candidate_weekly.columns,
        "selection_units": candidate_weekly.sum().to_numpy(),
        "weeks_with_sales": (
            candidate_weekly.gt(0).sum().to_numpy()
        ),
        "recent_8_weeks_with_sales": (
            candidate_weekly.iloc[-8:].gt(0).sum().to_numpy()
        ),
    })

    candidates["eligible"] = (
        candidates["weeks_with_sales"].ge(26)
        & candidates["recent_8_weeks_with_sales"].ge(4)
    )

    candidates = candidates.sort_values(
        ["selection_units", "StockCode"],
        ascending=[False, True],
    ).reset_index(drop=True)

    selected_codes = (
        candidates.loc[candidates["eligible"], "StockCode"]
        .head(TOP_N)
        .tolist()
    )

    require(
        len(selected_codes) == TOP_N,
        f"Expected {TOP_N} qualifying SKUs; found "
        f"{len(selected_codes)}. Review selection rules.",
    )

    candidates["selected"] = (
        candidates["StockCode"].isin(selected_codes)
    )
    candidates.to_csv(
        TABLES / "day04_sku_selection.csv",
        index=False,
    )

    selected_rows = development.loc[
        development["StockCode"].isin(selected_codes)
    ]

    weekly = (
        selected_rows.groupby(["week", "StockCode"])["Quantity"]
        .sum()
        .unstack("StockCode")
        .reindex(index=calendar, columns=selected_codes)
        .fillna(0)
        .astype(float)
    )

    require(
        np.isclose(
            weekly.to_numpy().sum(),
            selected_rows["Quantity"].sum(),
        ),
        "Weekly aggregation does not reconcile to selected sales.",
    )

    output_rows = []

    for origin in ORIGINS:
        future_weeks = pd.date_range(
            origin,
            periods=HORIZON,
            freq="W-MON",
        )

        require(
            future_weeks[-1] + pd.Timedelta(weeks=1)
            <= HOLDOUT_START,
            "Validation overlaps the reserved evaluation period.",
        )

        for stock_code in selected_codes:
            history = weekly.loc[
                weekly.index < origin, stock_code
            ]
            actual = weekly.loc[future_weeks, stock_code]

            forecasts = baseline_predictions(
                history, future_weeks
            )

            # MASE denominator: historical one-week naive error.
            scale = float(history.diff().abs().dropna().mean())

            for model, predicted_values in forecasts.items():
                for step, week in enumerate(future_weeks):
                    predicted = float(predicted_values[step])
                    observed = float(actual.iloc[step])

                    output_rows.append({
                        "origin": origin,
                        "week": week,
                        "horizon_week": step + 1,
                        "StockCode": stock_code,
                        "model": model,
                        "actual": observed,
                        "prediction": predicted,
                        "training_naive_mae": scale,
                        "scaled_absolute_error": (
                            abs(predicted - observed) / scale
                            if scale > 0 else np.nan
                        ),
                    })

    predictions = pd.DataFrame(output_rows)

    require(
        len(predictions)
        == len(ORIGINS) * TOP_N * HORIZON * len(MODELS),
        "Unexpected number of forecast records.",
    )
    require(
        np.isfinite(
            predictions[["actual", "prediction"]].to_numpy()
        ).all(),
        "Forecasts or actuals contain nonfinite values.",
    )

    overall = (
        summarize(predictions, ["model"])
        .sort_values(["wape_pct", "model"])
        .reset_index(drop=True)
    )

    fold_metrics = summarize(
        predictions, ["origin", "model"]
    )
    sku_metrics = summarize(
        predictions, ["StockCode", "model"]
    )
    horizon_metrics = summarize(
        predictions, ["horizon_week", "model"]
    )

    predictions.to_csv(
        TABLES / "day04_validation_predictions.csv",
        index=False,
    )
    overall.to_csv(
        TABLES / "day04_baseline_metrics.csv",
        index=False,
    )
    fold_metrics.to_csv(
        TABLES / "day04_fold_metrics.csv",
        index=False,
    )
    sku_metrics.to_csv(
        TABLES / "day04_sku_metrics.csv",
        index=False,
    )
    horizon_metrics.to_csv(
        TABLES / "day04_horizon_metrics.csv",
        index=False,
    )

    # Score individual SKU-week errors before any chart aggregation.
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(
        overall["model"],
        overall["wape_pct"],
        color="#185D73",
    )
    ax.set(
        title="Four-week baseline accuracy across 20 selected SKUs",
        xlabel="Forecasting baseline",
        ylabel="Validation WAPE (%) — lower is better",
    )
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    fig.savefig(
        FIGURES / "day04_baseline_wape.png",
        dpi=160,
    )
    plt.close(fig)

    best_model = str(overall.iloc[0]["model"])

    protocol = f"""# Day 4 — Forecast evaluation protocol

## Scope

- Target: weekly eligible merchandise units, all countries.
- Weeks: Monday through Sunday.
- Horizon: four weeks, issued once at each origin.
- SKU cohort: {TOP_N} products selected before August 8, 2011.
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

Lowest validation WAPE baseline: {best_model}.
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
"""

    (DOCS / "day04_forecast_protocol.md").write_text(
        protocol,
        encoding="utf-8",
    )

    print(f"\nSelected SKUs: {TOP_N}")
    print("Validation origins: 2011-08-08, 2011-09-05, 2011-10-03")
    print("Forecast horizon: four weeks")
    print("\nBASELINE METRICS")
    print(overall.to_string(index=False))

    print("\nMETRICS BY VALIDATION ORIGIN")
    print(fold_metrics.to_string(index=False))

    print(f"\nLowest validation WAPE: {best_model}")
    print("Reserved evaluation period remains unscored.")
    print("Day 4 outputs saved.")


if __name__ == "__main__":
    main()