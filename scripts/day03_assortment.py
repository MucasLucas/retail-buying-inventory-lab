"""Create a descriptive SKU scorecard and assortment charts."""
from datetime import timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "reports" / "tables"
FIGURES = ROOT / "reports" / "figures"

START = pd.Timestamp("2010-12-01")
END_EXCLUSIVE = pd.Timestamp("2011-12-01")
DAYS = (END_EXCLUSIVE - START).days


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)

    reconciliation = pd.read_csv(
        TABLES / "day02_overlap_reconciliation.csv"
    )
    overlap_ok = (
        reconciliation["reconciliation_accepted"]
        .astype(str)
        .str.lower()
        .eq("true")
        .all()
    )

    if reconciliation.empty or not overlap_ok:
        raise ValueError(
            "Review and resolve Day 2 overlap reconciliation first."
        )

    sales = pd.read_parquet(
        ROOT / "data" / "processed" / "merchandise_sales.parquet"
    )

    period = sales.loc[
        sales["InvoiceDate"].ge(START)
        & sales["InvoiceDate"].lt(END_EXCLUSIVE)
    ].copy()

    if period.empty:
        raise ValueError("No eligible sales in the analysis period.")

    period["sale_date"] = period["InvoiceDate"].dt.normalize()
    period["month"] = (
        period["InvoiceDate"].dt.to_period("M").astype(str)
    )

    # Invoice numbers are treated as source-level transaction IDs.
    # Check that they are not reused across different calendar dates.
    dates_per_invoice = (
        period.groupby("InvoiceNo")["sale_date"].nunique()
    )
    if dates_per_invoice.gt(1).any():
        raise ValueError(
            "An invoice spans multiple dates. Review order identifiers."
        )

    # Aggregate lines before measuring order-size concentration.
    sku_orders = (
        period.groupby(["StockCode", "InvoiceNo"], as_index=False)
        .agg(order_units=("Quantity", "sum"))
    )

    order_stats = (
        sku_orders.groupby("StockCode")
        .agg(
            median_units_per_order=("order_units", "median"),
            largest_order_units=("order_units", "max"),
        )
    )

    scorecard = (
        period.groupby("StockCode")
        .agg(
            units=("Quantity", "sum"),
            gross_sales_gbp=("line_value_gbp", "sum"),
            orders=("InvoiceNo", "nunique"),
            identified_customers=("CustomerID", "nunique"),
            selling_days=("sale_date", "nunique"),
            first_sale_in_window=("InvoiceDate", "min"),
            last_sale_in_window=("InvoiceDate", "max"),
        )
        .join(order_stats)
    )

    # Use the latest available description within this analysis window.
    descriptions = (
        period.loc[period["Description"].notna()]
        .sort_values(
            ["InvoiceDate", "source_sheet", "source_row"],
            kind="stable",
        )
        .drop_duplicates("StockCode", keep="last")
        .set_index("StockCode")["Description"]
    )

    scorecard = scorecard.join(
        descriptions.rename("description")
    )
    scorecard["description"] = (
        scorecard["description"].fillna("Description unavailable")
    )

    scorecard["average_selling_price_gbp"] = (
        scorecard["gross_sales_gbp"] / scorecard["units"]
    )
    scorecard["units_per_calendar_day"] = (
        scorecard["units"] / DAYS
    )
    scorecard["selling_day_share"] = (
        scorecard["selling_days"] / DAYS
    )
    scorecard["largest_order_unit_share"] = (
        scorecard["largest_order_units"] / scorecard["units"]
    )

    # Deterministic ordering for SKUs with equal sales.
    scorecard = (
        scorecard.reset_index()
        .sort_values(
            ["gross_sales_gbp", "StockCode"],
            ascending=[False, True],
        )
        .reset_index(drop=True)
    )

    total_sales = scorecard["gross_sales_gbp"].sum()
    scorecard["sales_share"] = (
        scorecard["gross_sales_gbp"] / total_sales
    )
    scorecard["cumulative_sales_share"] = (
        scorecard["sales_share"].cumsum()
    )

    # Include the SKU crossing each threshold in the preceding class.
    prior_share = (
        scorecard["cumulative_sales_share"]
        - scorecard["sales_share"]
    )
    scorecard["abc_class"] = "C"
    scorecard.loc[prior_share.lt(0.95), "abc_class"] = "B"
    scorecard.loc[prior_share.lt(0.80), "abc_class"] = "A"

    # Review flag, not a customer-type classification.
    scorecard["large_order_review"] = (
        scorecard["largest_order_unit_share"].ge(0.20)
    )

    scorecard.to_csv(
        TABLES / "day03_sku_scorecard.csv",
        index=False,
    )

    abc = (
        scorecard.groupby("abc_class")
        .agg(
            skus=("StockCode", "size"),
            units=("units", "sum"),
            gross_sales_gbp=("gross_sales_gbp", "sum"),
        )
        .reindex(["A", "B", "C"], fill_value=0)
    )
    abc["sku_share"] = abc["skus"] / len(scorecard)
    abc["sales_share"] = abc["gross_sales_gbp"] / total_sales
    abc.to_csv(TABLES / "day03_abc_summary.csv")

    months = pd.period_range(
        START,
        END_EXCLUSIVE.to_pydatetime() - timedelta(days=1),
        freq="M",
    ).astype(str)

    monthly = (
        period.groupby("month")
        .agg(
            units=("Quantity", "sum"),
            gross_sales_gbp=("line_value_gbp", "sum"),
            orders=("InvoiceNo", "nunique"),
            selling_days=("sale_date", "nunique"),
        )
        .reindex(months, fill_value=0)
    )
    monthly.index.name = "month"
    monthly["calendar_days"] = (
        pd.PeriodIndex(monthly.index, freq="M").days_in_month
    )
    monthly["units_per_calendar_day"] = (
        monthly["units"] / monthly["calendar_days"]
    )
    monthly.to_csv(TABLES / "day03_monthly_sales.csv")

    country = (
        period.groupby("Country")
        .agg(
            units=("Quantity", "sum"),
            gross_sales_gbp=("line_value_gbp", "sum"),
            orders=("InvoiceNo", "nunique"),
        )
        .sort_values("gross_sales_gbp", ascending=False)
    )
    country["sales_share"] = (
        country["gross_sales_gbp"] / total_sales
    )
    country.to_csv(TABLES / "day03_country_mix.csv")

    # Chart 1: cumulative contribution across the assortment.
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(
        range(1, len(scorecard) + 1),
        scorecard["cumulative_sales_share"] * 100,
        color="#185D73",
        linewidth=2,
    )
    ax.axhline(80, color="#B86828", linestyle="--", label="80%")
    ax.axhline(95, color="#666666", linestyle=":", label="95%")
    ax.set(
        title="How concentrated are merchandise sales?",
        xlabel="SKUs ranked by eligible gross sales",
        ylabel="Cumulative gross sales (%)",
        ylim=(0, 102),
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURES / "day03_sales_concentration.png", dpi=160)
    plt.close(fig)

    # Chart 2: top products by gross sales.
    top = scorecard.head(15).iloc[::-1].copy()
    labels = (
        top["StockCode"]
        + " | "
        + top["description"].str.slice(0, 35)
    )
    fig, ax = plt.subplots(figsize=(11, 7))
    ax.barh(labels, top["gross_sales_gbp"], color="#185D73")
    ax.set(
        title="Top 15 SKUs by eligible gross sales",
        xlabel="Gross sales (GBP), before credits",
    )
    fig.tight_layout()
    fig.savefig(FIGURES / "day03_top_skus.png", dpi=160)
    plt.close(fig)

    # Chart 3: descriptive monthly sales pattern.
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(
        monthly.index,
        monthly["units_per_calendar_day"],
        marker="o",
        color="#185D73",
    )
    ax.set(
        title="Observed unit sales by month",
        xlabel="Month",
        ylabel="Units per calendar day",
    )
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    fig.savefig(FIGURES / "day03_monthly_units.png", dpi=160)
    plt.close(fig)

    print(
        f"\nAnalysis window: {START.date()} through "
        f"{(END_EXCLUSIVE.to_pydatetime() - timedelta(days=1)).date()}"
    )
    print(f"Eligible sales rows: {len(period):,}")
    print(f"Distinct SKUs: {len(scorecard):,}")
    print(f"Eligible gross sales: GBP {total_sales:,.2f}")

    print("\nABC SUMMARY")
    print(abc.to_string())

    print("\nTOP 10 SKU SCORECARD")
    print(
        scorecard[
            [
                "StockCode",
                "units",
                "gross_sales_gbp",
                "abc_class",
                "largest_order_unit_share",
            ]
        ].head(10).to_string(index=False)
    )

    print("\nDay 3 outputs saved.")


if __name__ == "__main__":
    main()