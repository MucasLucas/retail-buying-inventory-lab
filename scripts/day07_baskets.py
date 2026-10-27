"""Discover directional product-pair rules and check later persistence."""

from pathlib import Path
import json

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix


ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "reports" / "tables"
FIGURES = ROOT / "reports" / "figures"
DOCS = ROOT / "docs"

START = pd.Timestamp("2010-12-01")
SPLIT = pd.Timestamp("2011-09-01")
END = pd.Timestamp("2011-12-01")

COUNTRY = "United Kingdom"
MAX_BASKET_SKUS = 50
TOP_PRODUCTS = 200
SHORTLIST_SIZE = 20

DISCOVERY_MIN_PAIR = 20
DISCOVERY_MIN_CONFIDENCE = 0.15
DISCOVERY_MIN_LIFT = 1.50

CONFIRMATION_MIN_PAIR = 5
CONFIRMATION_MIN_CONFIDENCE = 0.15
CONFIRMATION_MIN_LIFT = 1.20


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def prepare_baskets(
    frame: pd.DataFrame,
    period: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retain eligible invoices and one occurrence per invoice/SKU."""
    pairs = frame[
        ["InvoiceNo", "StockCode"]
    ].drop_duplicates()

    sizes = pairs.groupby("InvoiceNo").size()
    retained_invoices = sizes.loc[
        sizes.le(MAX_BASKET_SKUS)
    ].index

    retained = pairs.loc[
        pairs["InvoiceNo"].isin(retained_invoices)
    ].copy()

    audit = pd.DataFrame([{
        "period": period,
        "eligible_sales_rows_before_basket_filter": len(frame),
        "invoices_before_filter": len(sizes),
        "invoices_excluded_over_size_limit": int(
            sizes.gt(MAX_BASKET_SKUS).sum()
        ),
        "invoices_retained": len(retained_invoices),
        "single_sku_invoices_retained": int(
            sizes.loc[retained_invoices].eq(1).sum()
        ),
        "distinct_skus_retained": int(
            retained["StockCode"].nunique()
        ),
        "maximum_allowed_distinct_skus": MAX_BASKET_SKUS,
    }])

    return retained, audit


def basket_counts(
    pairs: pd.DataFrame,
    vocabulary: list[str],
) -> tuple[int, np.ndarray, np.ndarray]:
    """Count all baskets, SKU occurrences, and pair occurrences."""
    invoices = pd.Index(
        pairs["InvoiceNo"].drop_duplicates()
    )
    products = pd.Index(vocabulary)

    selected = pairs.loc[
        pairs["StockCode"].isin(products)
    ]

    row_indices = invoices.get_indexer(
        selected["InvoiceNo"]
    )
    column_indices = products.get_indexer(
        selected["StockCode"]
    )

    matrix = csr_matrix(
        (
            np.ones(len(selected), dtype=np.int64),
            (row_indices, column_indices),
        ),
        shape=(len(invoices), len(products)),
        dtype=np.int64,
    )

    # Include invoices with no vocabulary products in the denominator.
    product_counts = np.asarray(
        matrix.sum(axis=0)
    ).ravel()

    pair_counts = (matrix.T @ matrix).toarray()

    return len(invoices), product_counts, pair_counts


def score_rules(
    rules: pd.DataFrame,
    vocabulary: list[str],
    baskets: int,
    product_counts: np.ndarray,
    pair_counts: np.ndarray,
    prefix: str,
) -> pd.DataFrame:
    scored = rules.copy()
    positions = {code: i for i, code in enumerate(vocabulary)}

    antecedent_index = scored["antecedent"].map(
        positions
    ).to_numpy(dtype=int)

    consequent_index = scored["consequent"].map(
        positions
    ).to_numpy(dtype=int)

    antecedent_count = product_counts[antecedent_index]
    consequent_count = product_counts[consequent_index]
    together_count = pair_counts[
        antecedent_index, consequent_index
    ]

    confidence = np.divide(
        together_count.astype(float),
        antecedent_count,
        out=np.full(len(scored), np.nan),
        where=antecedent_count > 0,
    )

    consequent_support = consequent_count / baskets

    lift = np.divide(
        confidence,
        consequent_support,
        out=np.full(len(scored), np.nan),
        where=consequent_support > 0,
    )

    scored[f"{prefix}_baskets"] = baskets
    scored[f"{prefix}_antecedent_baskets"] = antecedent_count
    scored[f"{prefix}_consequent_baskets"] = consequent_count
    scored[f"{prefix}_pair_baskets"] = together_count
    scored[f"{prefix}_support"] = together_count / baskets
    scored[f"{prefix}_confidence"] = confidence
    scored[f"{prefix}_lift"] = lift

    return scored


def main() -> None:
    for folder in [TABLES, FIGURES, DOCS]:
        folder.mkdir(parents=True, exist_ok=True)

    input_path = (
        ROOT / "data" / "processed" / "merchandise_sales.parquet"
    )
    require(input_path.exists(), f"Missing input: {input_path}")

    sales = pd.read_parquet(input_path)

    scope = sales.loc[
        sales["Country"].eq(COUNTRY)
        & sales["InvoiceDate"].ge(START)
        & sales["InvoiceDate"].lt(END)
    ].copy()

    require(not scope.empty, "No eligible sales in basket scope.")

    require(
        scope[
            ["InvoiceNo", "StockCode", "InvoiceDate"]
        ].notna().all().all(),
        "Basket fields contain missing values.",
    )

    invoice_dates = (
        scope.assign(
            sale_date=scope["InvoiceDate"].dt.normalize()
        )
        .groupby("InvoiceNo")["sale_date"]
        .nunique()
    )

    require(
        invoice_dates.le(1).all(),
        "An invoice spans multiple dates. Review basket identifiers.",
    )

    discovery_rows = scope.loc[
        scope["InvoiceDate"].lt(SPLIT)
    ].copy()

    confirmation_rows = scope.loc[
        scope["InvoiceDate"].ge(SPLIT)
    ].copy()

    discovery, discovery_audit = prepare_baskets(
        discovery_rows, "discovery"
    )
    confirmation, confirmation_audit = prepare_baskets(
        confirmation_rows, "confirmation"
    )

    require(
        not discovery.empty and not confirmation.empty,
        "Both periods require eligible baskets.",
    )

    frequency = (
        discovery.groupby("StockCode")
        .size()
        .rename("discovery_baskets")
        .reset_index()
        .sort_values(
            ["discovery_baskets", "StockCode"],
            ascending=[False, True],
        )
    )

    vocabulary = (
        frequency.head(TOP_PRODUCTS)["StockCode"].tolist()
    )

    require(
        len(vocabulary) >= 2,
        "At least two candidate products are required.",
    )

    frequency["selected_for_pair_analysis"] = (
        frequency["StockCode"].isin(vocabulary)
    )
    frequency.to_csv(
        TABLES / "day07_product_frequency.csv",
        index=False,
    )

    discovery_n, discovery_items, discovery_pairs = basket_counts(
        discovery, vocabulary
    )

    # Evaluate every directional pair among discovery-selected SKUs.
    rule_keys = pd.DataFrame(
        [
            (antecedent, consequent)
            for antecedent in vocabulary
            for consequent in vocabulary
            if antecedent != consequent
        ],
        columns=["antecedent", "consequent"],
    )

    scored = score_rules(
        rule_keys,
        vocabulary,
        discovery_n,
        discovery_items,
        discovery_pairs,
        "discovery",
    )

    candidates = scored.loc[
        scored["discovery_pair_baskets"].ge(
            DISCOVERY_MIN_PAIR
        )
        & scored["discovery_confidence"].ge(
            DISCOVERY_MIN_CONFIDENCE
        )
        & scored["discovery_lift"].ge(
            DISCOVERY_MIN_LIFT
        )
    ].copy()

    candidates = candidates.sort_values(
        [
            "discovery_lift",
            "discovery_pair_baskets",
            "antecedent",
            "consequent",
        ],
        ascending=[False, False, True, True],
    )

    candidates.to_csv(
        TABLES / "day07_discovery_candidates.csv",
        index=False,
    )

    # Freeze the shortlist before scoring later-period baskets.
    shortlist = candidates.head(SHORTLIST_SIZE).copy()

    descriptions = (
        discovery_rows.loc[
            discovery_rows["Description"].notna()
        ]
        .sort_values(
            ["InvoiceDate", "source_sheet", "source_row"],
            kind="stable",
        )
        .drop_duplicates("StockCode", keep="last")
        .set_index("StockCode")["Description"]
    )

    for column in ["antecedent", "consequent"]:
        shortlist[f"{column}_description"] = (
            shortlist[column].map(descriptions)
        )

    confirmation_n, confirmation_items, confirmation_pairs = (
        basket_counts(confirmation, vocabulary)
    )

    assessed = score_rules(
        shortlist,
        vocabulary,
        confirmation_n,
        confirmation_items,
        confirmation_pairs,
        "confirmation",
    )

    assessed["persists_later"] = (
        assessed["confirmation_pair_baskets"].ge(
            CONFIRMATION_MIN_PAIR
        )
        & assessed["confirmation_confidence"].ge(
            CONFIRMATION_MIN_CONFIDENCE
        )
        & assessed["confirmation_lift"].ge(
            CONFIRMATION_MIN_LIFT
        )
    )

    assessed.to_csv(
        TABLES / "day07_cross_sell_shortlist.csv",
        index=False,
    )

    pd.concat(
        [discovery_audit, confirmation_audit],
        ignore_index=True,
    ).to_csv(
        TABLES / "day07_basket_audit.csv",
        index=False,
    )

    config = {
        "country": COUNTRY,
        "discovery_start": str(START.date()),
        "confirmation_start": str(SPLIT.date()),
        "end_exclusive": str(END.date()),
        "maximum_basket_skus": MAX_BASKET_SKUS,
        "maximum_candidate_products": TOP_PRODUCTS,
        "maximum_shortlist_rules": SHORTLIST_SIZE,
        "discovery_min_pair_baskets": DISCOVERY_MIN_PAIR,
        "discovery_min_confidence": DISCOVERY_MIN_CONFIDENCE,
        "discovery_min_lift": DISCOVERY_MIN_LIFT,
        "confirmation_min_pair_baskets": CONFIRMATION_MIN_PAIR,
        "confirmation_min_confidence": CONFIRMATION_MIN_CONFIDENCE,
        "confirmation_min_lift": CONFIRMATION_MIN_LIFT,
    }

    (TABLES / "day07_analysis_config.json").write_text(
        json.dumps(config, indent=2),
        encoding="utf-8",
    )

    fig, ax = plt.subplots(figsize=(10, 6))

    if assessed.empty:
        ax.text(
            0.5, 0.5,
            "No rules passed the fixed discovery thresholds.",
            ha="center", va="center",
            transform=ax.transAxes,
        )
        ax.set_axis_off()
    else:
        chart = assessed.head(10).iloc[::-1]
        labels = (
            chart["antecedent"] + " → " + chart["consequent"]
        )
        positions = np.arange(len(chart))

        ax.barh(
            positions - 0.18,
            chart["discovery_confidence"] * 100,
            height=0.35,
            label="Discovery",
            color="#185D73",
        )
        ax.barh(
            positions + 0.18,
            chart["confirmation_confidence"] * 100,
            height=0.35,
            label="Later period",
            color="#B86828",
        )
        ax.set_yticks(positions)
        ax.set_yticklabels(labels)
        ax.set_xlabel("Baskets with B among baskets containing A (%)")
        ax.set_title("Do discovery-period pairings persist later?")
        ax.legend()

    fig.tight_layout()
    fig.savefig(
        FIGURES / "day07_pair_persistence.png",
        dpi=160,
    )
    plt.close(fig)

    report = f"""# Day 7 — Market basket analysis

## Scope

United Kingdom eligible merchandise sales.
Discovery: December 2010 through August 2011.
Confirmation: September through November 2011.

An invoice is one basket. Each SKU counts once per basket.
Baskets with more than 50 distinct eligible SKUs are excluded.
Single-SKU baskets remain in the denominator.
Customer identification is not required.

## Method

Candidate products are the top 200 discovery-period SKUs by basket count.
Only single-product-to-single-product directional rules are assessed.
All eligible retained baskets remain in support denominators,
including baskets without a candidate-vocabulary SKU.

Discovery requires at least 20 shared baskets, confidence at least
15%, and lift at least 1.5.

The top 20 passing rules are shortlisted by discovery lift,
then shared-basket count, with SKU codes breaking remaining ties.

Later persistence requires at least five shared baskets,
confidence at least 15%, and lift at least 1.2.

## Results

Discovery baskets: {discovery_n:,}
Confirmation baskets: {confirmation_n:,}
Discovery rules passing thresholds: {len(candidates):,}
Shortlisted directional rules: {len(assessed):,}
Shortlisted rules persisting later: {int(assessed["persists_later"].sum()):,}

## Limits

Associations do not establish incremental recommendation impact.
Lift is not a sales-uplift estimate.
Thresholds are screening rules, not statistical significance tests.
Repeated purchases by the same customer may influence associations.
Product availability, prices, and seasonal assortment can change.
Related product variants may dominate pairings.
The basket-size filter does not identify customer type.
A-to-B and B-to-A share a product pair but can have different confidence.
This later period was previously explored in other project analyses;
it is a temporal persistence check, not wholly unseen validation.

## Buyer interpretation to complete

- Select up to three persistent rules and describe their products.
- Explain support, confidence, and lift for each.
- Are these complementary products, variants, or related collections?
- What placement or recommendation experiment would you propose?
- What inventory and margin checks must happen before launch?

## Suggested experiment

For eligible shoppers viewing product A, randomly assign a product-B
recommendation or the existing experience. Measure product-B attachment,
overall conversion, and gross profit per eligible visitor if cost data
is available. Monitor availability and customer experience.

These historical rules prioritize experiments; they do not prove impact.
"""

    report_path = DOCS / "day07_cross_sell_analysis.md"

    if not report_path.exists():
        report_path.write_text(report, encoding="utf-8")
    else:
        print("Existing Day 7 report preserved.")

    print(f"\nDiscovery baskets: {discovery_n:,}")
    print(f"Confirmation baskets: {confirmation_n:,}")
    print(f"Candidate products: {len(vocabulary):,}")
    print(f"Discovery rules passing thresholds: {len(candidates):,}")
    print(f"Shortlisted rules: {len(assessed):,}")
    print(
        "Rules persisting later: "
        f"{int(assessed['persists_later'].sum()):,}"
    )

    if not assessed.empty:
        print("\nSHORTLIST: FIRST 10 BY DISCOVERY RANK")
        print(
            assessed[
                [
                    "antecedent",
                    "consequent",
                    "discovery_pair_baskets",
                    "discovery_confidence",
                    "discovery_lift",
                    "confirmation_pair_baskets",
                    "confirmation_confidence",
                    "confirmation_lift",
                    "persists_later",
                ]
            ].head(10).to_string(index=False)
        )

    print("\nDay 7 outputs saved.")


if __name__ == "__main__":
    main()