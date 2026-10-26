"""Assess inventory buffers using fixed forecast and cost scenarios."""

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

BUFFERS = [0.0, 0.25, 0.50, 1.0]
LEAD_TIMES = [1, 2, 3]
REVIEW_WEEKS = 1

# These are decision weights, not actual monetary costs.
SHORTAGE_PENALTIES = [2.0, 5.0, 10.0]
SURPLUS_PENALTY = 1.0


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_forecasts(path: Path, model: str) -> pd.DataFrame:
    frame = pd.read_csv(
        path,
        dtype={"StockCode": "string"},
        parse_dates=["origin", "week"],
    )

    frame = frame.loc[frame["model"].eq(model)].copy()

    require(
        not frame.empty,
        f"No forecasts found for {model} in {path.name}.",
    )
    require(
        not frame.duplicated(
            ["origin", "StockCode", "horizon_week"]
        ).any(),
        f"Duplicate forecast keys in {path.name}.",
    )
    require(
        np.isfinite(
            frame[["actual", "prediction"]].to_numpy()
        ).all(),
        f"Nonfinite forecast values in {path.name}.",
    )
    require(
        frame[["actual", "prediction"]].ge(0).all().all(),
        f"Negative sales or predictions in {path.name}.",
    )

    for (origin, code), group in frame.groupby(
        ["origin", "StockCode"]
    ):
        require(
            sorted(group["horizon_week"].tolist())
            == [1, 2, 3, 4],
            f"Incomplete four-week forecast: {origin}, {code}.",
        )

        expected_week = (
            group["origin"]
            + pd.to_timedelta(
                (group["horizon_week"] - 1) * 7,
                unit="D",
            )
        )
        require(
            group["week"].eq(expected_week).all(),
            f"Inconsistent forecast dates: {origin}, {code}.",
        )

    return frame


def protection_windows(forecasts: pd.DataFrame) -> pd.DataFrame:
    """Sum forecast and observed units over each protection period."""
    windows = []

    for lead_weeks in LEAD_TIMES:
        protection_weeks = lead_weeks + REVIEW_WEEKS

        subset = forecasts.loc[
            forecasts["horizon_week"].le(protection_weeks)
        ]

        totals = (
            subset.groupby(
                ["origin", "StockCode"],
                as_index=False,
            )
            .agg(
                forecast_units=("prediction", "sum"),
                observed_units=("actual", "sum"),
            )
        )

        totals["lead_weeks"] = lead_weeks
        totals["review_weeks"] = REVIEW_WEEKS
        totals["protection_weeks"] = protection_weeks

        windows.append(totals)

    return pd.concat(windows, ignore_index=True)


def evaluate_grid(windows: pd.DataFrame) -> pd.DataFrame:
    """Assess a fixed grid of buffer and penalty assumptions."""
    results = []

    for buffer in BUFFERS:
        for shortage_penalty in SHORTAGE_PENALTIES:
            frame = windows.copy()

            frame["buffer_fraction"] = buffer
            frame["shortage_penalty"] = shortage_penalty
            frame["surplus_penalty"] = SURPLUS_PENALTY

            frame["inventory_target_units"] = np.ceil(
                frame["forecast_units"] * (1 + buffer)
            ).astype("int64")

            frame["buffer_units_above_forecast"] = (
                frame["inventory_target_units"]
                - frame["forecast_units"]
            )

            frame["uncovered_units"] = (
                frame["observed_units"]
                - frame["inventory_target_units"]
            ).clip(lower=0)

            frame["surplus_units"] = (
                frame["inventory_target_units"]
                - frame["observed_units"]
            ).clip(lower=0)

            frame["covered_units"] = (
                frame["observed_units"]
                - frame["uncovered_units"]
            )

            frame["weighted_penalty"] = (
                shortage_penalty * frame["uncovered_units"]
                + SURPLUS_PENALTY * frame["surplus_units"]
            )

            frame["fully_covered"] = frame[
                "uncovered_units"
            ].eq(0)

            results.append(frame)

    return pd.concat(results, ignore_index=True)


def summarize(
    frame: pd.DataFrame,
    group_columns: list[str],
) -> pd.DataFrame:
    summary = (
        frame.groupby(group_columns, as_index=False)
        .agg(
            sku_windows=("StockCode", "size"),
            forecast_units=("forecast_units", "sum"),
            observed_units=("observed_units", "sum"),
            inventory_target_units=(
                "inventory_target_units", "sum"
            ),
            uncovered_units=("uncovered_units", "sum"),
            surplus_units=("surplus_units", "sum"),
            covered_units=("covered_units", "sum"),
            weighted_penalty=("weighted_penalty", "sum"),
            fully_covered_sku_windows=(
                "fully_covered", "sum"
            ),
        )
    )

    summary["observed_unit_coverage_pct"] = (
        100
        * summary["covered_units"]
        / summary["observed_units"].replace(0, np.nan)
    )

    summary["fully_covered_sku_windows_pct"] = (
        100
        * summary["fully_covered_sku_windows"]
        / summary["sku_windows"]
    )

    return summary


def main() -> None:
    for folder in [TABLES, FIGURES, DOCS]:
        folder.mkdir(parents=True, exist_ok=True)

    required_paths = [
        TABLES / "day05_model_selection.json",
        TABLES / "day05_validation_predictions.csv",
        TABLES / "day05_holdout_predictions.csv",
    ]

    for path in required_paths:
        require(path.exists(), f"Missing input: {path}")

    selection = json.loads(
        (TABLES / "day05_model_selection.json").read_text(
            encoding="utf-8"
        )
    )
    model = selection["selected_model"]

    validation_forecasts = read_forecasts(
        TABLES / "day05_validation_predictions.csv",
        model,
    )
    holdout_forecasts = read_forecasts(
        TABLES / "day05_holdout_predictions.csv",
        model,
    )

    require(
        set(validation_forecasts["StockCode"])
        == set(holdout_forecasts["StockCode"]),
        "Validation and reserved-period SKU cohorts differ.",
    )
    require(
        holdout_forecasts["origin"].nunique() == 1,
        "Expected one reserved-period origin.",
    )
    require(
        validation_forecasts["week"].max()
        < holdout_forecasts["origin"].min(),
        "Validation overlaps the reserved-period origin.",
    )

    validation_grid = evaluate_grid(
        protection_windows(validation_forecasts)
    )

    group_columns = [
        "lead_weeks",
        "review_weeks",
        "protection_weeks",
        "shortage_penalty",
        "surplus_penalty",
        "buffer_fraction",
    ]

    validation_summary = summarize(
        validation_grid,
        group_columns,
    )

    # Choose buffers using validation only.
    # If penalties tie, prefer the smaller buffer.
    policies = (
        validation_summary.sort_values(
            [
                "lead_weeks",
                "shortage_penalty",
                "weighted_penalty",
                "buffer_fraction",
            ]
        )
        .drop_duplicates(
            ["lead_weeks", "shortage_penalty"],
            keep="first",
        )
        .copy()
    )

    policies["selection_grid_boundary"] = policies[
        "buffer_fraction"
    ].eq(max(BUFFERS))

    validation_summary.to_csv(
        TABLES / "day06_validation_scenarios.csv",
        index=False,
    )
    policies.to_csv(
        TABLES / "day06_selected_policies.csv",
        index=False,
    )

    # Evaluate only the validation-selected policies and a
    # zero-buffer comparator for the reserved period.
    holdout_grid = evaluate_grid(
        protection_windows(holdout_forecasts)
    )

    policy_keys = [
        "lead_weeks",
        "shortage_penalty",
        "buffer_fraction",
    ]

    selected_holdout = holdout_grid.merge(
        policies[policy_keys],
        on=policy_keys,
        how="inner",
        validate="many_to_one",
    )
    selected_holdout["policy"] = "validation_selected"

    zero_holdout = holdout_grid.loc[
        holdout_grid["buffer_fraction"].eq(0)
    ].copy()
    zero_holdout["policy"] = "zero_buffer_comparator"

    assessment = pd.concat(
        [selected_holdout, zero_holdout],
        ignore_index=True,
    )

    assessment_summary = summarize(
        assessment,
        ["policy"] + group_columns,
    )

    assessment.to_csv(
        TABLES / "day06_assessment_sku_details.csv",
        index=False,
    )
    assessment_summary.to_csv(
        TABLES / "day06_assessment_summary.csv",
        index=False,
    )

    # Plot the middle penalty scenario for readability.
    middle = assessment_summary.loc[
        assessment_summary["shortage_penalty"].eq(5.0)
    ]

    fig, axes = plt.subplots(
        1, 2, figsize=(11, 4.5)
    )

    for policy, frame in middle.groupby("policy"):
        frame = frame.sort_values("protection_weeks")

        axes[0].plot(
            frame["protection_weeks"],
            frame["observed_unit_coverage_pct"],
            marker="o",
            label=policy,
        )
        axes[1].plot(
            frame["protection_weeks"],
            frame["inventory_target_units"],
            marker="o",
            label=policy,
        )

    axes[0].set(
        title="Observed unit coverage",
        xlabel="Protection period (weeks)",
        ylabel="Covered observed units (%)",
        ylim=(0, 105),
    )
    axes[1].set(
        title="Inventory required by the scenario",
        xlabel="Protection period (weeks)",
        ylabel="Total target units across 20 SKUs",
    )

    for ax in axes:
        ax.set_xticks([2, 3, 4])
        ax.legend(fontsize=8)

    fig.suptitle(
        "Illustrative shortage-to-surplus penalty ratio: 5:1"
    )
    fig.tight_layout()
    fig.savefig(
        FIGURES / "day06_inventory_tradeoffs.png",
        dpi=160,
    )
    plt.close(fig)

    report = f"""# Day 6 — Inventory planning scenarios

## Forecast input

Selected method: {model}.
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
"""

    report_path = DOCS / "day06_inventory_scenarios.md"

    if not report_path.exists():
        report_path.write_text(
            report,
            encoding="utf-8",
        )
    else:
        print("Existing Day 6 report preserved.")

    print(f"\nForecast method: {model}")

    print("\nVALIDATION-SELECTED POLICIES")
    print(
        policies[
            [
                "lead_weeks",
                "protection_weeks",
                "shortage_penalty",
                "buffer_fraction",
                "weighted_penalty",
                "selection_grid_boundary",
            ]
        ].to_string(index=False)
    )

    print("\nRESERVED-PERIOD SCENARIO ASSESSMENT")
    print(
        assessment_summary[
            [
                "policy",
                "protection_weeks",
                "shortage_penalty",
                "buffer_fraction",
                "inventory_target_units",
                "uncovered_units",
                "surplus_units",
                "observed_unit_coverage_pct",
            ]
        ].to_string(index=False)
    )

    print("\nDay 6 outputs saved.")


if __name__ == "__main__":
    main()