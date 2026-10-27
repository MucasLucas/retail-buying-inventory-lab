"""Build UK customer RFM segments and aggregate commercial profiles."""

from pathlib import Path
import json

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
TABLES = ROOT / "reports" / "tables"
FIGURES = ROOT / "reports" / "figures"
DOCS = ROOT / "docs"

START = pd.Timestamp("2010-12-01")
SNAPSHOT = pd.Timestamp("2011-12-01")
COUNTRY = "United Kingdom"

SEGMENT_ORDER = [
    "Champions",
    "Recent repeat buyers",
    "Recent low-frequency buyers",
    "High-frequency buyers at risk",
    "High-value buyers at risk",
    "Other inactive buyers",
    "Developing buyers",
]

ACTIONS = {
    "Champions": (
        "Protect availability of frequently purchased products; "
        "test relevant complementary-product recommendations."
    ),
    "Recent repeat buyers": (
        "Support repeat purchasing with replenishment reminders "
        "and relevant assortment recommendations."
    ),
    "Recent low-frequency buyers": (
        "Test a second-purchase journey; do not assume these "
        "customers are newly acquired."
    ),
    "High-frequency buyers at risk": (
        "Investigate lapses in formerly frequent purchasing; "
        "test targeted reengagement."
    ),
    "High-value buyers at risk": (
        "Review historical product preferences and large orders "
        "before personalized reengagement."
    ),
    "Other inactive buyers": (
        "Use a limited reactivation test and assess incremental "
        "response before expanding investment."
    ),
    "Developing buyers": (
        "Test relevant product discovery and repeat-purchase "
        "messages rather than blanket discounts."
    ),
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def behavior_score(
    values: pd.Series,
    higher_is_better: bool,
) -> pd.Series:
    """Create tie-aware percentile scores from 1 through 5."""
    percentiles = values.rank(
        method="average",
        pct=True,
        ascending=higher_is_better,
    )

    return (
        np.ceil(percentiles * 5)
        .clip(1, 5)
        .astype("int64")
    )


def assign_segments(rfm: pd.DataFrame) -> pd.Series:
    """Apply explicit segment rules in priority order."""
    r = rfm["R_score"]
    f = rfm["F_score"]
    m = rfm["M_score"]

    conditions = [
        r.ge(4) & f.ge(4) & m.ge(4),
        r.ge(4) & f.ge(3),
        r.ge(4) & f.le(2),
        r.le(2) & f.ge(4),
        r.le(2) & m.ge(4),
        r.le(2),
    ]

    labels = SEGMENT_ORDER[:-1]

    return pd.Series(
        np.select(
            conditions,
            labels,
            default="Developing buyers",
        ),
        index=rfm.index,
        dtype="string",
    )


def main() -> None:
    for folder in [PROCESSED, TABLES, FIGURES, DOCS]:
        folder.mkdir(parents=True, exist_ok=True)

    input_path = PROCESSED / "merchandise_sales.parquet"
    require(input_path.exists(), f"Missing input: {input_path}")

    sales = pd.read_parquet(input_path)

    scope = sales.loc[
        sales["Country"].eq(COUNTRY)
        & sales["InvoiceDate"].ge(START)
        & sales["InvoiceDate"].lt(SNAPSHOT)
    ].copy()

    require(
        not scope.empty,
        "No eligible sales in the selected UK window.",
    )
    require(
        scope["Quantity"].gt(0).all()
        and scope["UnitPrice"].gt(0).all(),
        "RFM input contains nonpositive sales quantities or prices.",
    )
    require(
        not scope["is_cancellation"].any(),
        "RFM input contains cancellation invoices.",
    )

    # Standardize IDs defensively without inventing missing identities.
    scope["CustomerID"] = (
        scope["CustomerID"]
        .astype("string")
        .str.strip()
        .replace("", pd.NA)
    )

    identified = scope.loc[
        scope["CustomerID"].notna()
    ].copy()

    require(
        not identified.empty,
        "No identified customers are available for RFM.",
    )

    invoice_customer_counts = (
        identified.groupby("InvoiceNo")["CustomerID"].nunique()
    )

    require(
        invoice_customer_counts.le(1).all(),
        "An invoice maps to multiple customer IDs. Review before RFM.",
    )

    total_gross = float(scope["line_value_gbp"].sum())
    identified_gross = float(
        identified["line_value_gbp"].sum()
    )

    coverage = pd.DataFrame([
        {
            "scope": label,
            "rows": len(frame),
            "distinct_invoices": int(
                frame["InvoiceNo"].nunique()
            ),
            "gross_sales_gbp": float(
                frame["line_value_gbp"].sum()
            ),
        }
        for label, frame in [
            ("all_eligible_uk_sales", scope),
            ("identified_customer_uk_sales", identified),
        ]
    ])

    coverage["gross_sales_share_of_all_eligible_uk"] = (
        coverage["gross_sales_gbp"] / total_gross
    )

    coverage.to_csv(
        TABLES / "day08_customer_coverage.csv",
        index=False,
    )

    rfm = (
        identified.groupby("CustomerID")
        .agg(
            last_purchase=("InvoiceDate", "max"),
            first_purchase_in_window=("InvoiceDate", "min"),
            frequency_orders=("InvoiceNo", "nunique"),
            monetary_gbp=("line_value_gbp", "sum"),
            units=("Quantity", "sum"),
        )
        .reset_index()
    )

    rfm["recency_days"] = (
        SNAPSHOT - rfm["last_purchase"].dt.normalize()
    ).dt.days

    rfm["average_order_value_gbp"] = (
        rfm["monetary_gbp"] / rfm["frequency_orders"]
    )

    # Lower recency is better; higher frequency and monetary are better.
    rfm["R_score"] = behavior_score(
        rfm["recency_days"],
        higher_is_better=False,
    )
    rfm["F_score"] = behavior_score(
        rfm["frequency_orders"],
        higher_is_better=True,
    )
    rfm["M_score"] = behavior_score(
        rfm["monetary_gbp"],
        higher_is_better=True,
    )

    rfm["rfm_code"] = (
        rfm["R_score"].astype(str)
        + rfm["F_score"].astype(str)
        + rfm["M_score"].astype(str)
    )

    rfm["segment"] = assign_segments(rfm)

    require(
        rfm["CustomerID"].is_unique,
        "Customer-level output has duplicate IDs.",
    )
    require(
        rfm["recency_days"].ge(1).all(),
        "Invalid recency: check snapshot and purchase dates.",
    )
    require(
        np.isclose(rfm["monetary_gbp"].sum(), identified_gross),
        "Customer monetary totals do not reconcile.",
    )
    require(
        int(rfm["frequency_orders"].sum())
        == identified["InvoiceNo"].nunique(),
        "Customer order totals do not reconcile.",
    )

    # Customer-level output remains inside ignored data/.
    rfm.to_parquet(
        PROCESSED / "customer_rfm.parquet",
        index=False,
    )

    profile = (
        rfm.groupby("segment")
        .agg(
            customers=("CustomerID", "size"),
            orders=("frequency_orders", "sum"),
            gross_sales_gbp=("monetary_gbp", "sum"),
            units=("units", "sum"),
            median_recency_days=("recency_days", "median"),
            median_orders_per_customer=(
                "frequency_orders", "median"
            ),
            median_gross_sales_per_customer_gbp=(
                "monetary_gbp", "median"
            ),
        )
        .reindex(SEGMENT_ORDER)
    )

    # Empty rule-defined segments remain visible in the summary.
    count_columns = [
        "customers",
        "orders",
        "gross_sales_gbp",
        "units",
    ]
    profile[count_columns] = (
        profile[count_columns].fillna(0)
    )

    profile["customer_share"] = (
        profile["customers"] / len(rfm)
    )
    profile["identified_gross_sales_share"] = (
        profile["gross_sales_gbp"] / identified_gross
    )
    profile["average_order_value_gbp"] = (
        profile["gross_sales_gbp"]
        / profile["orders"].replace(0, np.nan)
    )
    profile["buyer_action"] = [
        ACTIONS[segment] for segment in profile.index
    ]

    require(
        int(profile["customers"].sum()) == len(rfm),
        "Segment totals do not account for every customer.",
    )

    profile.to_csv(
        TABLES / "day08_segment_profiles.csv",
        index_label="segment",
    )

    score_ranges = []

    for metric, score_column in [
        ("recency_days", "R_score"),
        ("frequency_orders", "F_score"),
        ("monetary_gbp", "M_score"),
    ]:
        ranges = (
            rfm.groupby(score_column)[metric]
            .agg(
                customers="size",
                minimum="min",
                maximum="max",
            )
            .reset_index()
            .rename(columns={score_column: "score"})
        )
        ranges.insert(0, "metric", metric)
        score_ranges.append(ranges)

    pd.concat(
        score_ranges,
        ignore_index=True,
    ).to_csv(
        TABLES / "day08_score_ranges.csv",
        index=False,
    )

    ranked = rfm.sort_values(
        ["monetary_gbp", "CustomerID"],
        ascending=[False, True],
    )

    top_count = max(1, int(np.ceil(len(ranked) * 0.10)))
    top_sales = float(
        ranked.head(top_count)["monetary_gbp"].sum()
    )

    concentration = pd.DataFrame([{
        "identified_customers": len(rfm),
        "top_customer_count": top_count,
        "actual_top_customer_fraction": top_count / len(rfm),
        "top_customers_gross_sales_gbp": top_sales,
        "top_customers_gross_sales_share": (
            top_sales / identified_gross
        ),
    }])

    concentration.to_csv(
        TABLES / "day08_customer_concentration.csv",
        index=False,
    )

    chart = profile.loc[profile["customers"].gt(0)]
    positions = np.arange(len(chart))

    fig, ax = plt.subplots(figsize=(12, 6))

    ax.barh(
        positions - 0.18,
        chart["customer_share"] * 100,
        height=0.35,
        label="Share of identified customers",
        color="#185D73",
    )
    ax.barh(
        positions + 0.18,
        chart["identified_gross_sales_share"] * 100,
        height=0.35,
        label="Share of identified gross sales",
        color="#B86828",
    )

    ax.set_yticks(positions)
    ax.set_yticklabels(chart.index)
    ax.invert_yaxis()
    ax.set(
        title="Which customer segments account for gross sales?",
        xlabel="Share (%)",
    )
    ax.legend()

    fig.tight_layout()
    fig.savefig(
        FIGURES / "day08_segment_contribution.png",
        dpi=160,
    )
    plt.close(fig)

    config = {
        "country": COUNTRY,
        "purchase_window_start": str(START.date()),
        "snapshot_date_exclusive": str(SNAPSHOT.date()),
        "monetary_definition": (
            "eligible gross merchandise sales before credits"
        ),
        "frequency_definition": "distinct purchase invoices",
        "scoring": (
            "ceil(5 * average-rank percentile); ties share scores"
        ),
        "customer_level_output": (
            "data/processed/customer_rfm.parquet"
        ),
        "segment_priority": SEGMENT_ORDER,
    }

    (TABLES / "day08_rfm_config.json").write_text(
        json.dumps(config, indent=2),
        encoding="utf-8",
    )

    report = f"""# Day 8 — Customer RFM segmentation

## Scope

Country: {COUNTRY}.
Purchase window: December 1, 2010 through November 30, 2011.
Snapshot: December 1, 2011.

Identified customers: {len(rfm):,}.
Eligible UK gross sales: GBP {total_gross:,.2f}.
Identified-customer gross sales: GBP {identified_gross:,.2f}.
Identified share of eligible UK gross sales:
{100 * identified_gross / total_gross:.2f}%.

## Definitions

Recency: calendar days since the last eligible purchase.
Frequency: distinct eligible purchase invoices.
Monetary: eligible gross merchandise sales before credits.

Missing customer IDs are excluded from segmentation but remain in
the coverage denominator. No missing IDs are imputed.

Scores use average-rank percentiles on a 1-to-5 scale.
Higher scores indicate stronger observed purchasing behavior.
Tied values receive identical scores, so score groups need not
contain exactly 20% of customers and some scores may be absent.

## Segment rules in priority order

- Champions: R >= 4, F >= 4, M >= 4.
- Recent repeat buyers: R >= 4, F >= 3, after Champions.
- Recent low-frequency buyers: R >= 4, F <= 2.
- High-frequency buyers at risk: R <= 2, F >= 4.
- High-value buyers at risk: R <= 2, M >= 4, after the prior rule.
- Other inactive buyers: remaining R <= 2.
- Developing buyers: all remaining customers.

Labels are relative behavioral descriptions, not verified lifecycle
states. A low-frequency buyer is not necessarily newly acquired.

## Concentration

The top {top_count:,} identified customers by gross sales account for
{100 * top_sales / identified_gross:.2f}% of identified gross sales.
This is gross-sales concentration, not profit or lifetime value.

## Limits

Credits are not subtracted from monetary value.
Large purchases can dominate gross monetary scores.
Customer identity quality limits segmentation.
The scores and segments are descriptive, not predictions.
No campaign response or retention improvement has been measured.
Earlier purchases outside the analysis window are not represented.

## Buyer interpretation to complete

- Which segment contributes the largest share of gross sales?
- Which segment has the largest customer share?
- What action would you test for recent repeat buyers?
- What investigation would you prioritize for at-risk buyers?
- How does missing customer identification limit the analysis?

## Experiment proposal

Choose one segment and randomly assign an eligible intervention
or the existing experience. Measure incremental repeat purchase
and gross sales per assigned customer over a fixed follow-up period.
Include margin and campaign costs when those inputs are available.
"""

    report_path = DOCS / "day08_customer_segments.md"

    if not report_path.exists():
        report_path.write_text(report, encoding="utf-8")
    else:
        print("Existing Day 8 report preserved.")

    print(f"\nIdentified UK customers: {len(rfm):,}")
    print(f"Eligible UK gross sales: GBP {total_gross:,.2f}")
    print(
        "Identified share of eligible UK gross sales: "
        f"{100 * identified_gross / total_gross:.2f}%"
    )

    print("\nSEGMENT PROFILES")
    print(
        profile[
            [
                "customers",
                "gross_sales_gbp",
                "customer_share",
                "identified_gross_sales_share",
                "median_recency_days",
                "median_orders_per_customer",
            ]
        ].to_string()
    )

    print(
        f"\nTop {top_count:,} customers' share of identified "
        f"gross sales: {100 * top_sales / identified_gross:.2f}%"
    )

    print("\nDay 8 outputs saved.")


if __name__ == "__main__":
    main()