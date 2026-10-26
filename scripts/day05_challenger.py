"""Compare a fixed Random Forest challenger with Day 4 baselines."""

from datetime import timedelta
from pathlib import Path
import json

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from day04_baselines import (
    FIRST_WEEK,
    HOLDOUT_END_EXCLUSIVE,
    HOLDOUT_START,
    HORIZON,
    MODELS,
    ORIGINS,
    baseline_predictions,
    require,
    summarize,
)


ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "reports" / "tables"
FIGURES = ROOT / "reports" / "figures"
DOCS = ROOT / "docs"

CHALLENGER = "random_forest"

RF_PARAMS = {
    "n_estimators": 300,
    "max_depth": 12,
    "min_samples_leaf": 5,
    "max_features": 0.8,
    "random_state": 42,
    "n_jobs": -1,
}

FEATURES = [
    "horizon_week",
    "lag_1",
    "lag_2",
    "lag_4",
    "lag_13",
    "lag_52",
    "mean_4",
    "mean_13",
    "std_13",
    "zero_share_13",
    "target_month_sin",
    "target_month_cos",
]


def build_examples(
    weekly: pd.DataFrame,
    codes: list[str],
) -> pd.DataFrame:
    """Build forecast snapshots using only pre-origin features."""
    rows = []

    for code in codes:
        series = weekly[code]

        for position in range(52, len(weekly)):
            issue_date = weekly.index[position]

            if issue_date > HOLDOUT_START:
                break

            history = series.iloc[:position]

            for step in range(1, HORIZON + 1):
                target_position = position + step - 1

                if target_position >= len(weekly):
                    continue

                target_date = weekly.index[target_position]
                angle = 2 * np.pi * (target_date.month - 1) / 12

                rows.append({
                    "StockCode": code,
                    "issue_date": issue_date,
                    "target_date": target_date,
                    "horizon_week": step,
                    "lag_1": float(history.iloc[-1]),
                    "lag_2": float(history.iloc[-2]),
                    "lag_4": float(history.iloc[-4]),
                    "lag_13": float(history.iloc[-13]),
                    "lag_52": float(history.iloc[-52]),
                    "mean_4": float(history.iloc[-4:].mean()),
                    "mean_13": float(history.iloc[-13:].mean()),
                    "std_13": float(
                        history.iloc[-13:].std(ddof=0)
                    ),
                    "zero_share_13": float(
                        history.iloc[-13:].eq(0).mean()
                    ),
                    "target_month_sin": float(np.sin(angle)),
                    "target_month_cos": float(np.cos(angle)),
                    "actual": float(series.iloc[target_position]),
                })

    return pd.DataFrame(rows)


def encode(
    frame: pd.DataFrame,
    codes: list[str],
) -> pd.DataFrame:
    """Encode SKU identity using the cohort fixed before validation."""
    matrix = frame[FEATURES].astype(float).copy()

    for code in codes:
        matrix[f"sku_{code}"] = (
            frame["StockCode"].eq(code).astype(float)
        )

    return matrix


def forecast_origin(
    weekly: pd.DataFrame,
    examples: pd.DataFrame,
    codes: list[str],
    origin: pd.Timestamp,
    include_challenger: bool = True,
) -> pd.DataFrame:
    """Train on completed weeks and issue a four-week forecast."""
    future_weeks = pd.date_range(
        origin,
        periods=HORIZON,
        freq="W-MON",
    )

    query = examples.loc[
        examples["issue_date"].eq(origin)
    ].copy()

    require(
        len(query) == len(codes) * HORIZON,
        f"Incomplete forecast query at {origin}.",
    )

    if include_challenger:
        training = examples.loc[
            examples["target_date"].lt(origin)
        ].copy()

        require(
            not training.empty,
            f"No training examples before {origin}.",
        )

        latest_completed_week = (
            origin.to_pydatetime() - timedelta(weeks=1)
        )

        require(
            training["target_date"].le(
                latest_completed_week
            ).all(),
            "Training contains a target week not yet completed.",
        )

        model = RandomForestRegressor(**RF_PARAMS)

        model.fit(
            encode(training, codes),
            training["actual"],
        )

        query["rf_prediction"] = np.clip(
            model.predict(encode(query, codes)),
            a_min=0,
            a_max=None,
        )

    records = []

    for code in codes:
        history = weekly.loc[
            weekly.index < origin,
            code,
        ]

        naive_scale = float(
            history.diff().abs().dropna().mean()
        )

        forecasts = baseline_predictions(
            history,
            future_weeks,
        )

        code_query = (
            query.loc[query["StockCode"].eq(code)]
            .sort_values("horizon_week")
        )

        if include_challenger:
            forecasts[CHALLENGER] = (
                code_query["rf_prediction"].to_numpy()
            )

        actual_values = weekly.loc[
            future_weeks,
            code,
        ].to_numpy()

        for name, values in forecasts.items():
            for index, week in enumerate(future_weeks):
                prediction = float(values[index])
                actual = float(actual_values[index])

                records.append({
                    "origin": origin,
                    "week": week,
                    "horizon_week": index + 1,
                    "StockCode": code,
                    "model": name,
                    "actual": actual,
                    "prediction": prediction,
                    "training_naive_mae": naive_scale,
                    "scaled_absolute_error": (
                        abs(prediction - actual) / naive_scale
                        if naive_scale > 0 else np.nan
                    ),
                })

    return pd.DataFrame(records)


def indented_table(frame: pd.DataFrame) -> str:
    """Format a plain-text table as an indented Markdown code block."""
    return "\n".join(
        f"    {line}"
        for line in frame.to_string(index=False).splitlines()
    )


def main() -> None:
    for folder in [TABLES, FIGURES, DOCS]:
        folder.mkdir(parents=True, exist_ok=True)

    required_paths = [
        TABLES / "day04_sku_selection.csv",
        TABLES / "day04_validation_predictions.csv",
        ROOT / "data" / "processed" / "merchandise_sales.parquet",
    ]

    for path in required_paths:
        require(
            path.exists(),
            f"Missing required input: {path}",
        )

    selection = pd.read_csv(
        TABLES / "day04_sku_selection.csv",
        dtype={"StockCode": "string"},
    )

    selected = (
        selection["selected"]
        .astype(str)
        .str.lower()
        .eq("true")
    )

    codes = selection.loc[
        selected,
        "StockCode",
    ].tolist()

    require(
        len(codes) == 20 and len(set(codes)) == 20,
        "Expected the 20 unique Day 4 SKUs.",
    )

    sales = pd.read_parquet(
        ROOT / "data" / "processed" / "merchandise_sales.parquet"
    )

    scope = sales.loc[
        sales["StockCode"].isin(codes)
        & sales["InvoiceDate"].ge(FIRST_WEEK)
        & sales["InvoiceDate"].lt(HOLDOUT_END_EXCLUSIVE)
    ].copy()

    scope["week"] = (
        scope["InvoiceDate"]
        .dt.to_period("W-SUN")
        .dt.start_time
    )

    final_week_start = (
        HOLDOUT_END_EXCLUSIVE.to_pydatetime()
        - timedelta(weeks=1)
    )

    calendar = pd.date_range(
        FIRST_WEEK,
        final_week_start,
        freq="W-MON",
    )

    weekly = (
        scope.groupby(["week", "StockCode"])["Quantity"]
        .sum()
        .unstack("StockCode")
        .reindex(index=calendar, columns=codes)
        .fillna(0)
        .astype(float)
    )

    require(
        np.isclose(
            weekly.to_numpy().sum(),
            scope["Quantity"].sum(),
        ),
        "Weekly totals do not reconcile to source sales.",
    )

    examples = build_examples(weekly, codes)

    require(
        not examples.empty,
        "No forecasting examples were generated.",
    )

    validation_parts = []

    for origin in ORIGINS:
        print(
            f"Evaluating validation origin {origin.date()}...",
            flush=True,
        )

        validation_parts.append(
            forecast_origin(
                weekly,
                examples,
                codes,
                origin,
            )
        )

    validation = pd.concat(
        validation_parts,
        ignore_index=True,
    )

    expected_rows = (
        len(ORIGINS)
        * len(codes)
        * HORIZON
        * (len(MODELS) + 1)
    )

    require(
        len(validation) == expected_rows,
        "Unexpected validation prediction count.",
    )

    require(
        np.isfinite(
            validation[["actual", "prediction"]].to_numpy()
        ).all(),
        "Validation contains nonfinite actuals or predictions.",
    )

    # Verify that the baseline comparison reproduces Day 4.
    saved = pd.read_csv(
        TABLES / "day04_validation_predictions.csv",
        dtype={"StockCode": "string"},
        parse_dates=["origin", "week"],
    )

    keys = [
        "origin",
        "week",
        "StockCode",
        "model",
    ]

    current_baselines = validation.loc[
        validation["model"].isin(MODELS)
    ]

    check = saved.merge(
        current_baselines,
        on=keys,
        how="outer",
        suffixes=("_day04", "_day05"),
        indicator=True,
        validate="one_to_one",
    )

    require(
        check["_merge"].eq("both").all(),
        "Day 4 and Day 5 baseline forecast keys differ.",
    )

    for column in ["actual", "prediction"]:
        require(
            np.allclose(
                check[f"{column}_day04"],
                check[f"{column}_day05"],
            ),
            f"Day 4 {column} values changed. "
            "Review data and scripts before continuing.",
        )

    leaderboard = summarize(
        validation,
        ["model"],
    )

    leaderboard["is_challenger"] = (
        leaderboard["model"].eq(CHALLENGER)
    )

    require(
        np.isfinite(leaderboard["wape_pct"]).all(),
        "Validation WAPE is undefined or nonfinite.",
    )

    leaderboard = (
        leaderboard.sort_values(
            ["wape_pct", "is_challenger", "model"]
        )
        .reset_index(drop=True)
    )

    selected_model = str(
        leaderboard.iloc[0]["model"]
    )

    best_baseline = str(
        leaderboard.loc[
            ~leaderboard["is_challenger"],
            "model",
        ].iloc[0]
    )

    # Freeze selection before evaluating the reserved period.
    selection_record = {
        "selected_model": selected_model,
        "best_validation_baseline": best_baseline,
        "selection_metric": "lowest_validation_wape",
        "tie_policy": "prefer_baseline_then_model_name",
        "random_forest_parameters": RF_PARAMS,
        "features": FEATURES,
        "sku_encoding": "fixed_cohort_one_hot",
        "selected_skus": codes,
        "validation_origins": [
            str(date.date()) for date in ORIGINS
        ],
        "holdout_start": str(HOLDOUT_START.date()),
        "holdout_end_exclusive": str(
            HOLDOUT_END_EXCLUSIVE.date()
        ),
    }

    (TABLES / "day05_model_selection.json").write_text(
        json.dumps(selection_record, indent=2),
        encoding="utf-8",
    )

    validation.to_csv(
        TABLES / "day05_validation_predictions.csv",
        index=False,
    )

    leaderboard.to_csv(
        TABLES / "day05_validation_metrics.csv",
        index=False,
    )

    summarize(
        validation,
        ["origin", "model"],
    ).to_csv(
        TABLES / "day05_validation_fold_metrics.csv",
        index=False,
    )

    print(
        f"\nSelection frozen: {selected_model}",
        flush=True,
    )

    print(
        "Evaluating reserved period...",
        flush=True,
    )

    holdout = forecast_origin(
        weekly,
        examples,
        codes,
        HOLDOUT_START,
        include_challenger=(
            selected_model == CHALLENGER
        ),
    )

    # Retain only the frozen winner and baseline comparator.
    holdout = holdout.loc[
        holdout["model"].isin(
            {selected_model, best_baseline}
        )
    ].copy()

    require(
        np.isfinite(
            holdout[["actual", "prediction"]].to_numpy()
        ).all(),
        "Reserved-period results contain nonfinite values.",
    )

    holdout_metrics = summarize(
        holdout,
        ["model"],
    )

    holdout.to_csv(
        TABLES / "day05_holdout_predictions.csv",
        index=False,
    )

    holdout_metrics.to_csv(
        TABLES / "day05_holdout_metrics.csv",
        index=False,
    )

    summarize(
        holdout,
        ["StockCode", "model"],
    ).to_csv(
        TABLES / "day05_holdout_sku_metrics.csv",
        index=False,
    )

    summarize(
        holdout,
        ["horizon_week", "model"],
    ).to_csv(
        TABLES / "day05_holdout_horizon_metrics.csv",
        index=False,
    )

    fig, ax = plt.subplots(figsize=(9, 5))

    colors = [
        "#B86828" if name == CHALLENGER else "#185D73"
        for name in leaderboard["model"]
    ]

    ax.bar(
        leaderboard["model"],
        leaderboard["wape_pct"],
        color=colors,
    )

    ax.set(
        title="Validation: does the challenger improve sales forecasts?",
        ylabel="WAPE (%) — lower is better",
    )

    ax.tick_params(
        axis="x",
        rotation=25,
    )

    fig.tight_layout()

    fig.savefig(
        FIGURES / "day05_validation_comparison.png",
        dpi=160,
    )

    plt.close(fig)

    validation_table = indented_table(leaderboard)
    holdout_table = indented_table(holdout_metrics)

    report = f"""# Day 5 — Forecast model comparison

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

Selected method: {selected_model}

Best validation baseline: {best_baseline}

## Validation metrics

{validation_table}

## Reserved-period metrics

October 31 through November 27, 2011.

{holdout_table}

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
"""

    report_path = DOCS / "day05_model_comparison.md"

    # Preserve a report containing manually completed interpretation.
    if not report_path.exists():
        report_path.write_text(
            report,
            encoding="utf-8",
        )
        print(f"\nCreated report: {report_path.name}")
    else:
        print(
            "\nExisting report preserved: "
            "day05_model_comparison.md"
        )

    print("\nVALIDATION LEADERBOARD")
    print(leaderboard.to_string(index=False))

    print("\nRESERVED-PERIOD RESULTS")
    print(holdout_metrics.to_string(index=False))

    print("\nDay 5 outputs saved.")


if __name__ == "__main__":
    main()