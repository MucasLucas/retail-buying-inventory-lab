"""Integrate retail analyses into an evidence-backed buyer action plan."""

from pathlib import Path
import json

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "reports" / "tables"
DOCS = ROOT / "docs"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_table(filename: str, **kwargs) -> pd.DataFrame:
    path = TABLES / filename
    require(path.exists(), f"Missing prerequisite: {path}")
    return pd.read_csv(path, **kwargs)


def true_values(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().eq("true")


def markdown_table(frame: pd.DataFrame) -> str:
    """Render a simple Markdown table without extra dependencies."""
    def clean(value):
        if pd.isna(value):
            return ""
        return (
            str(value)
            .replace("|", "/")
            .replace("\n", " ")
            .replace("\r", " ")
        )

    header = "| " + " | ".join(
        str(column) for column in frame.columns
    ) + " |"

    separator = "| " + " | ".join(
        "---" for _ in frame.columns
    ) + " |"

    rows = [
        "| " + " | ".join(clean(value) for value in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    ]

    return "\n".join([header, separator] + rows)


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)

    abc = read_table("day03_abc_summary.csv")
    validation = read_table("day05_validation_metrics.csv")
    holdout = read_table("day05_holdout_metrics.csv")
    sku_errors = read_table(
        "day05_holdout_sku_metrics.csv",
        dtype={"StockCode": "string"},
    )
    policies = read_table("day06_selected_policies.csv")
    assessment = read_table("day06_assessment_summary.csv")
    cross_sell = read_table(
        "day07_cross_sell_shortlist.csv",
        dtype={
            "antecedent": "string",
            "consequent": "string",
        },
    )
    segments = read_table("day08_segment_profiles.csv")
    coverage = read_table("day08_customer_coverage.csv")

    selection_path = TABLES / "day05_model_selection.json"
    require(selection_path.exists(), "Missing Day 5 model selection.")

    selection = json.loads(
        selection_path.read_text(encoding="utf-8")
    )
    model = selection["selected_model"]

    actions = []

    def add_action(
        action_id,
        priority,
        scope,
        finding,
        action,
        owner,
        success_measure,
        limitation,
        evidence,
    ):
        actions.append({
            "action_id": action_id,
            "priority": priority,
            "scope": scope,
            "finding": finding,
            "proposed_action": action,
            "proposed_owner": owner,
            "success_measure": success_measure,
            "limitation": limitation,
            "evidence_file": evidence,
        })

    # Assortment contribution.
    a_class = abc.loc[abc["abc_class"].eq("A")]
    require(len(a_class) == 1, "Expected one A-class summary row.")
    a = a_class.iloc[0]

    add_action(
        "A01",
        "P1",
        "All countries; December 2010-November 2011 assortment",
        (
            f"{int(a['skus']):,} A-class SKUs represent "
            f"{100 * a['sku_share']:.2f}% of SKUs and "
            f"{100 * a['sales_share']:.2f}% of gross sales."
        ),
        "Prioritize A-class products for availability and purchasing review.",
        "Buyer / inventory planner",
        "Document availability, margin, and lead-time review for priority SKUs.",
        "Gross-sales contribution does not establish profitability.",
        "day03_abc_summary.csv",
    )

    # Forecast selection and later-period uncertainty.
    selected_validation = validation.loc[
        validation["model"].eq(model)
    ]
    selected_holdout = holdout.loc[holdout["model"].eq(model)]

    require(
        len(selected_validation) == 1 and len(selected_holdout) == 1,
        "Selected model metrics are missing or duplicated.",
    )

    v = selected_validation.iloc[0]
    h = selected_holdout.iloc[0]

    add_action(
        "A02",
        "P1",
        "20 selected SKUs; all countries; four-week forecasts",
        (
            f"{model}: validation WAPE {v['wape_pct']:.2f}%; "
            f"reserved-period WAPE {h['wape_pct']:.2f}%; "
            f"bias {h['bias_pct']:.2f}%."
        ),
        "Retain the validation-selected method as a planning baseline.",
        "Demand planner / analyst",
        "Monitor prospective SKU-week WAPE and bias before deployment.",
        "Observed sales may understate unconstrained demand.",
        "day05_holdout_metrics.csv;day05_validation_metrics.csv",
    )

    error_leaders = (
        sku_errors.loc[sku_errors["model"].eq(model)]
        .sort_values(
            ["absolute_error_units", "StockCode"],
            ascending=[False, True],
        )
        .head(3)
    )

    for index, row in enumerate(
        error_leaders.itertuples(index=False), start=1
    ):
        add_action(
            f"F{index:02d}",
            "P1",
            "Selected forecast cohort; reserved four-week period",
            (
                f"SKU {row.StockCode}: "
                f"{row.absolute_error_units:,.0f} absolute error units; "
                f"bias {row.bias_pct:.2f}%."
            ),
            "Inspect large orders, credits, availability, and sales history.",
            "Demand planner / buyer",
            "Record an evidence-backed exception assessment for this SKU.",
            "Large errors alone do not identify the cause or best remedy.",
            "day05_holdout_sku_metrics.csv",
        )

    # Inventory scenario comparison: fixed four-week, 5:1 scenario.
    inventory_scope = assessment.loc[
        assessment["protection_weeks"].eq(4)
        & assessment["shortage_penalty"].eq(5.0)
    ]

    buffered = inventory_scope.loc[
        inventory_scope["policy"].eq("validation_selected")
    ]
    zero = inventory_scope.loc[
        inventory_scope["policy"].eq("zero_buffer_comparator")
    ]

    require(
        len(buffered) == 1 and len(zero) == 1,
        "Expected one selected and one zero-buffer inventory scenario.",
    )

    b = buffered.iloc[0]
    z = zero.iloc[0]

    add_action(
        "A03",
        "P1",
        "20 SKUs; four-week static coverage scenario; 5:1 penalty",
        (
            f"Selected buffer {100 * b['buffer_fraction']:.0f}%: "
            f"coverage {b['observed_unit_coverage_pct']:.2f}% "
            f"versus {z['observed_unit_coverage_pct']:.2f}%; "
            f"surplus {b['surplus_units']:,.0f} units."
        ),
        "Review SKU-level buffers after obtaining operational inventory inputs.",
        "Inventory planner / supply chain",
        "Validate lead times, inventory positions, case packs, and unit costs.",
        "Scenario coverage is not a future service guarantee or measured saving.",
        "day06_assessment_summary.csv",
    )

    boundary_count = int(
        true_values(policies["selection_grid_boundary"]).sum()
    )

    add_action(
        "A04",
        "P2",
        "Inventory assumption sensitivity",
        (
            f"{boundary_count} of {len(policies)} selected policies "
            "reach the maximum tested buffer."
        ),
        "Document sensitivity and uncertainty before operational adoption.",
        "Inventory planner / analyst",
        "Approve explicit assumptions and a prospective evaluation protocol.",
        "A grid-boundary result does not establish an optimal buffer.",
        "day06_selected_policies.csv",
    )

    # Preserve discovery ranking; do not rerank on confirmation outcomes.
    persistent = cross_sell.loc[
        true_values(cross_sell["persists_later"])
    ].copy()

    # Avoid proposing both directions of the same pair as separate tests.
    seen_pairs = set()
    pair_actions = 0

    for _, row in persistent.iterrows():
        pair_key = tuple(sorted([
            str(row["antecedent"]),
            str(row["consequent"]),
        ]))

        if pair_key in seen_pairs:
            continue

        seen_pairs.add(pair_key)
        pair_actions += 1

        add_action(
            f"X{pair_actions:02d}",
            "P2",
            "UK retained baskets; discovery then later-period assessment",
            (
                f"{row['antecedent']} -> {row['consequent']}: "
                f"later confidence "
                f"{100 * row['confirmation_confidence']:.1f}%, "
                f"lift {row['confirmation_lift']:.2f}, "
                f"shared baskets "
                f"{int(row['confirmation_pair_baskets'])}."
            ),
            "Review product compatibility and propose a randomized placement test.",
            "Merchandiser / ecommerce product team",
            "Measure incremental attachment and gross profit per eligible visitor.",
            "Association and lift do not establish incremental sales impact.",
            "day07_cross_sell_shortlist.csv",
        )

        if pair_actions == 3:
            break

    if pair_actions == 0:
        add_action(
            "X00",
            "P2",
            "UK market basket analysis",
            "No shortlisted pair passed the fixed later-persistence screen.",
            "Document the negative result and defer pair-based launch decisions.",
            "Merchandiser / analyst",
            "Define a new prospective hypothesis before further analysis.",
            "Do not lower thresholds after inspecting confirmation outcomes.",
            "day07_cross_sell_shortlist.csv",
        )

    # Customer segment contribution and coverage.
    nonempty_segments = segments.loc[
        segments["customers"].gt(0)
    ]
    require(
        not nonempty_segments.empty,
        "No nonempty RFM segments found.",
    )

    top_segment = nonempty_segments.sort_values(
        ["gross_sales_gbp", "segment"],
        ascending=[False, True],
    ).iloc[0]

    add_action(
        "A05",
        "P2",
        "Identified UK customers; December 2010-November 2011",
        (
            f"{top_segment['segment']} contributes "
            f"{100 * top_segment['identified_gross_sales_share']:.2f}% "
            "of identified-customer gross sales."
        ),
        str(top_segment["buyer_action"]),
        "CRM / merchandising",
        "Test incremental repeat purchase and gross sales per assigned customer.",
        "Gross sales are before credits and do not measure customer profitability.",
        "day08_segment_profiles.csv",
    )

    identified_coverage = coverage.loc[
        coverage["scope"].eq("identified_customer_uk_sales")
    ]
    require(
        len(identified_coverage) == 1,
        "Expected one identified-customer coverage row.",
    )

    share = float(
        identified_coverage.iloc[0][
            "gross_sales_share_of_all_eligible_uk"
        ]
    )

    add_action(
        "A06",
        "P1",
        "UK customer-identification coverage",
        f"Identified customers represent {100 * share:.2f}% of eligible UK gross sales.",
        "Document coverage and investigate identity capture before broad targeting.",
        "CRM / data engineering",
        "Track valid identification coverage without inventing customer identities.",
        "RFM cannot describe purchases without usable customer identifiers.",
        "day08_customer_coverage.csv",
    )

    action_table = (
        pd.DataFrame(actions)
        .sort_values(["priority", "action_id"])
        .reset_index(drop=True)
    )

    # Check every referenced evidence file before exporting recommendations.
    for references in action_table["evidence_file"]:
        for filename in references.split(";"):
            require(
                (TABLES / filename).exists(),
                f"Missing action evidence: {filename}",
            )

    action_table.to_csv(
        TABLES / "day09_buyer_action_plan.csv",
        index=False,
    )

    sensitivity = policies[
        [
            "lead_weeks",
            "protection_weeks",
            "shortage_penalty",
            "buffer_fraction",
            "selection_grid_boundary",
        ]
    ].sort_values(["lead_weeks", "shortage_penalty"])

    sensitivity.to_csv(
        TABLES / "day09_inventory_sensitivity.csv",
        index=False,
    )

    backlog = action_table[
        [
            "action_id",
            "priority",
            "proposed_action",
            "proposed_owner",
            "success_measure",
            "evidence_file",
        ]
    ].copy()

    backlog["status"] = "Proposed"
    backlog["next_step"] = np.where(
        backlog["priority"].eq("P1"),
        "Validate inputs and review with the proposed owner.",
        "Prepare an experiment or review brief after prerequisite checks.",
    )

    backlog.to_csv(
        TABLES / "day09_prioritized_backlog.csv",
        index=False,
    )

    compact = action_table[
        ["action_id", "priority", "finding", "proposed_action"]
    ]

    report = f"""# Day 9 — Buyer decision brief

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

{markdown_table(compact)}

## Inventory sensitivity

{markdown_table(sensitivity)}

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
"""

    report_path = DOCS / "day09_buyer_decision_brief.md"

    if not report_path.exists():
        report_path.write_text(report, encoding="utf-8")
    else:
        print("Existing Day 9 decision brief preserved.")

    print(f"\nSelected forecast method: {model}")
    print(f"Proposed actions: {len(action_table)}")
    print(f"Distinct cross-selling pairs proposed: {pair_actions}")
    print(f"Inventory policies at grid boundary: {boundary_count}")

    print("\nBUYER ACTION PLAN")
    print(
        action_table[
            ["action_id", "priority", "scope", "finding"]
        ].to_string(index=False)
    )

    print("\nDay 9 outputs saved.")


if __name__ == "__main__":
    main()