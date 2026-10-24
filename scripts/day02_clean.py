"""Reconcile UCI sources and classify transactions for retail analysis."""

from pathlib import Path
import json

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"
TABLES = ROOT / "reports" / "tables"

BUSINESS_COLUMNS = [
    "InvoiceNo",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "UnitPrice",
    "CustomerID",
    "Country",
]

TEXT_COLUMNS = [
    "InvoiceNo",
    "StockCode",
    "Description",
    "CustomerID",
    "Country",
]


def require(condition: bool, message: str) -> None:
    """Stop processing when a required check fails."""
    if not condition:
        raise ValueError(message)


def row_counts(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    """Count occurrences of each business row, including missing values."""
    return (
        frame.groupby(
            BUSINESS_COLUMNS,
            dropna=False,
            observed=True,
        )
        .size()
        .rename(name)
        .reset_index()
    )


def resolve_internal_overlap(primary: pd.DataFrame) -> pd.DataFrame:
    """Give the newer sheet ownership of the verified overlap."""
    original_rows = len(primary)
    expected_sheets = {"Year 2009-2010", "Year 2010-2011"}

    require(
        set(primary["source_sheet"].unique()) == expected_sheets,
        "Unexpected workbook sheets: review source ownership.",
    )

    older = primary.loc[
        primary["source_sheet"].eq("Year 2009-2010")
    ].copy()

    newer = primary.loc[
        primary["source_sheet"].eq("Year 2010-2011")
    ].copy()

    require(
        not older.empty and not newer.empty,
        "Both expected workbook sheets must contain records.",
    )
    require(
        primary["InvoiceDate"].notna().all(),
        "Missing invoice dates prevent reliable sheet ownership.",
    )

    boundary = newer["InvoiceDate"].min()

    older_overlap = older.loc[
        older["InvoiceDate"].ge(boundary)
    ].copy()

    overlap_check = row_counts(
        older_overlap, "older_count"
    ).merge(
        row_counts(newer, "newer_count"),
        on=BUSINESS_COLUMNS,
        how="left",
        validate="one_to_one",
    )

    uncovered = (
        overlap_check["older_count"]
        - overlap_check["newer_count"].fillna(0)
    ).clip(lower=0).sum()

    require(
        uncovered == 0,
        "Some older-sheet overlap rows are absent from the newer "
        "sheet. Review before removing any overlap.",
    )

    retained = pd.concat(
        [
            older.loc[older["InvoiceDate"].lt(boundary)],
            newer,
        ],
        ignore_index=True,
    )

    require(
        len(retained) + len(older_overlap) == original_rows,
        "Internal overlap row accounting failed.",
    )

    pd.DataFrame([{
        "original_rows": original_rows,
        "newer_sheet_ownership_start": str(boundary),
        "older_overlap_rows_removed": len(older_overlap),
        "uncovered_older_overlap_rows": int(uncovered),
        "retained_primary_rows": len(retained),
    }]).to_csv(
        TABLES / "day02_internal_overlap.csv",
        index=False,
    )

    print(
        f"Internal overlap: removed {len(older_overlap):,} "
        f"older-sheet rows; retained {len(retained):,} rows.",
        flush=True,
    )

    return retained


def reconcile_sources(
    reference: pd.DataFrame,
    primary: pd.DataFrame,
) -> dict:
    """Compare overlapping records and their occurrence counts."""
    start = reference["InvoiceDate"].min()
    end = reference["InvoiceDate"].max()

    overlap = primary.loc[
        primary["InvoiceDate"].between(start, end),
        BUSINESS_COLUMNS,
    ].copy()

    comparison = row_counts(
        reference, "reference_count"
    ).merge(
        row_counts(overlap, "primary_count"),
        on=BUSINESS_COLUMNS,
        how="outer",
        validate="one_to_one",
    )

    count_columns = ["reference_count", "primary_count"]

    comparison[count_columns] = (
        comparison[count_columns].fillna(0).astype("int64")
    )

    matched = comparison[count_columns].min(axis=1)

    reference_excess = comparison["reference_count"] - matched
    primary_excess = comparison["primary_count"] - matched

    exact_match = bool(
        reference_excess.sum() == 0
        and primary_excess.sum() == 0
    )

    extra = comparison.loc[primary_excess.gt(0)]

    # This exception applies only to the specifically inspected
    # extra postage line. Every reference row must still match.
    known_postage_difference = bool(
        reference_excess.sum() == 0
        and primary_excess.sum() == 1
        and len(extra) == 1
        and extra["InvoiceNo"].eq("581587").all()
        and extra["StockCode"].eq("POST").all()
        and extra["Description"].eq("POSTAGE").all()
        and extra["Quantity"].eq(1).all()
        and extra["UnitPrice"].eq(18.0).all()
        and extra["Country"].eq("France").all()
        and extra["InvoiceDate"].eq(
            pd.Timestamp("2011-12-09 12:50:00")
        ).all()
    )

    summary = {
        "overlap_start": str(start),
        "overlap_end": str(end),
        "reference_rows": len(reference),
        "primary_overlap_rows": len(overlap),
        "matched_rows_with_multiplicity": int(matched.sum()),
        "reference_unmatched_rows": int(reference_excess.sum()),
        "primary_unmatched_rows": int(primary_excess.sum()),
        "exact_multiset_match": exact_match,
        "known_postage_difference": known_postage_difference,
        "reconciliation_accepted": bool(
            exact_match or known_postage_difference
        ),
    }

    pd.DataFrame([summary]).to_csv(
        TABLES / "day02_overlap_reconciliation.csv",
        index=False,
    )

    daily_tables = []

    for label, frame in [
        ("reference", reference),
        ("primary", overlap),
    ]:
        daily = (
            frame.assign(
                date=frame["InvoiceDate"].dt.normalize()
            )
            .groupby("date")
            .agg(
                rows=("Quantity", "size"),
                signed_units=("Quantity", "sum"),
            )
            .add_prefix(f"{label}_")
        )
        daily_tables.append(daily)

    daily = (
        daily_tables[0]
        .join(daily_tables[1], how="outer")
        .fillna(0)
    )

    daily["row_difference"] = (
        daily["primary_rows"] - daily["reference_rows"]
    )
    daily["signed_unit_difference"] = (
        daily["primary_signed_units"]
        - daily["reference_signed_units"]
    )

    daily.to_csv(TABLES / "day02_overlap_daily.csv")

    return summary


def classify_transactions(primary: pd.DataFrame) -> pd.DataFrame:
    """Normalize working fields and assign one disposition per row."""
    frame = primary.copy()

    for column in TEXT_COLUMNS:
        frame[f"raw_{column}"] = frame[column]
        frame[column] = (
            frame[column].astype("string").str.strip()
        )
        frame[column] = frame[column].replace("", pd.NA)

    frame["InvoiceNo"] = frame["InvoiceNo"].str.upper()
    frame["StockCode"] = frame["StockCode"].str.upper()

    frame["line_value_gbp"] = (
        frame["Quantity"] * frame["UnitPrice"]
    )

    frame["is_cancellation"] = (
        frame["InvoiceNo"].str.startswith("C", na=False)
    )

    frame["missing_customer_id"] = frame["CustomerID"].isna()
    frame["missing_description"] = frame["Description"].isna()

    # Provisional merchandise rule, subject to stock-code review.
    frame["standard_stock_code"] = (
        frame["StockCode"]
        .str.fullmatch(r"\d{5}[A-Z]*", na=False)
    )

    # Preserve repeated lines; flag later occurrences for sensitivity.
    frame["repeated_business_row"] = frame.duplicated(
        subset=BUSINESS_COLUMNS,
        keep="first",
    )

    frame["disposition"] = "eligible_sale"

    required_fields = [
        "InvoiceNo",
        "StockCode",
        "InvoiceDate",
        "Quantity",
        "UnitPrice",
        "Country",
    ]

    rules = [
        (
            frame[required_fields].isna().any(axis=1),
            "missing_required_field",
        ),
        (
            frame["is_cancellation"],
            "cancellation_or_credit",
        ),
        (
            frame["Quantity"].lt(0),
            "negative_quantity_review",
        ),
        (
            frame["Quantity"].eq(0),
            "zero_quantity",
        ),
        (
            frame["UnitPrice"].le(0),
            "nonpositive_price",
        ),
        (
            ~frame["standard_stock_code"],
            "stock_code_review",
        ),
    ]

    # Earlier rules take priority.
    for mask, label in rules:
        unassigned = frame["disposition"].eq("eligible_sale")
        frame.loc[unassigned & mask, "disposition"] = label

    frame["eligible_for_customer_analysis"] = (
        frame["disposition"].eq("eligible_sale")
        & ~frame["missing_customer_id"]
    )

    return frame


def main() -> None:
    for folder in [PROCESSED, TABLES]:
        folder.mkdir(parents=True, exist_ok=True)

    paths = {
        "reference": INTERIM / "online_retail.parquet",
        "primary": INTERIM / "online_retail_ii.parquet",
    }

    for path in paths.values():
        require(path.exists(), f"Missing Day 1 output: {path}")

    print("Loading Day 1 outputs...", flush=True)

    reference = pd.read_parquet(paths["reference"])
    primary = pd.read_parquet(paths["primary"])

    primary = resolve_internal_overlap(primary)

    print("Reconciling overlapping records...", flush=True)
    reconciliation = reconcile_sources(reference, primary)

    print("\nOVERLAP RECONCILIATION")
    print(json.dumps(reconciliation, indent=2))

    require(
        reconciliation["reconciliation_accepted"],
        "Source reconciliation failed. Inspect the overlap reports "
        "before generating new processed sales files.",
    )

    print("Classifying primary-source transactions...", flush=True)
    classified = classify_transactions(primary)

    sales = classified.loc[
        classified["disposition"].eq("eligible_sale")
    ].copy()

    require(
        len(sales) > 0,
        "No eligible sales: inspect the rules.",
    )
    require(
        sales["Quantity"].gt(0).all(),
        "Eligible sales contain nonpositive quantities.",
    )
    require(
        sales["UnitPrice"].gt(0).all(),
        "Eligible sales contain nonpositive prices.",
    )
    require(
        not sales["is_cancellation"].any(),
        "Eligible sales contain cancellation invoices.",
    )
    require(
        not classified.duplicated(
            ["source_dataset", "source_sheet", "source_row"]
        ).any(),
        "Source-row provenance is not unique.",
    )

    disposition = (
        classified.groupby("disposition")
        .agg(
            rows=("Quantity", "size"),
            signed_units=("Quantity", "sum"),
            signed_line_value_gbp=("line_value_gbp", "sum"),
        )
        .reset_index()
    )

    require(
        int(disposition["rows"].sum()) == len(primary),
        "Classification did not account for every retained source row.",
    )

    disposition.to_csv(
        TABLES / "day02_disposition_summary.csv",
        index=False,
    )

    # Include all nonstandard codes, even if another rule excluded
    # their records first.
    code_review = (
        classified.loc[~classified["standard_stock_code"]]
        .groupby("StockCode", dropna=False)
        .agg(
            rows=("Quantity", "size"),
            example_description=("Description", "first"),
            signed_line_value_gbp=("line_value_gbp", "sum"),
        )
        .sort_values("rows", ascending=False)
        .reset_index()
    )

    code_review.to_csv(
        TABLES / "day02_stock_code_review.csv",
        index=False,
    )

    without_repeats = sales.loc[
        ~sales["repeated_business_row"]
    ]

    sensitivity = pd.DataFrame([
        {
            "scenario": label,
            "rows": len(frame),
            "units": float(frame["Quantity"].sum()),
            "gross_sales_gbp": float(
                frame["line_value_gbp"].sum()
            ),
        }
        for label, frame in [
            ("preserve_repeated_rows_primary", sales),
            ("remove_repeated_rows_sensitivity", without_repeats),
        ]
    ])

    sensitivity.to_csv(
        TABLES / "day02_repeat_sensitivity.csv",
        index=False,
    )

    coverage = pd.DataFrame([
        {
            "scope": label,
            "rows": len(frame),
            "units": float(frame["Quantity"].sum()),
            "gross_sales_gbp": float(
                frame["line_value_gbp"].sum()
            ),
        }
        for label, frame in [
            ("all_eligible_sales", sales),
            (
                "eligible_sales_with_customer_id",
                sales.loc[sales["eligible_for_customer_analysis"]],
            ),
        ]
    ])

    coverage.to_csv(
        TABLES / "day02_customer_coverage.csv",
        index=False,
    )

    classified.to_parquet(
        PROCESSED / "transactions_classified.parquet",
        index=False,
    )

    sales.to_parquet(
        PROCESSED / "merchandise_sales.parquet",
        index=False,
    )

    print("\nTRANSACTION DISPOSITIONS")
    print(disposition.to_string(index=False))

    print("\nREPEATED-ROW SENSITIVITY")
    print(sensitivity.to_string(index=False))

    print("\nCUSTOMER COVERAGE")
    print(coverage.to_string(index=False))

    print("\nDay 2 processing complete. No sources were appended.")


if __name__ == "__main__":
    main()