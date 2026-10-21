"""Download, standardize, and audit the UCI Online Retail datasets."""

from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile, is_zipfile

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
TABLES = ROOT / "reports" / "tables"

SOURCES = {
    "online_retail": {
        "url": (
            "https://archive.ics.uci.edu/static/public/"
            "352/online%2Bretail.zip"
        ),
        "workbook": "Online Retail.xlsx",
        "doi": "https://doi.org/10.24432/C5BW33",
        "expected_rows": 541_909,
    },
    "online_retail_ii": {
        "url": (
            "https://archive.ics.uci.edu/static/public/"
            "502/online%2Bretail%2Bii.zip"
        ),
        "workbook": "online_retail_II.xlsx",
        "doi": "https://doi.org/10.24432/C5CG6D",
        "expected_rows": 1_067_371,
    },
}

COLUMNS = [
    "InvoiceNo",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "UnitPrice",
    "CustomerID",
    "Country",
]

ALIASES = {
    "Invoice": "InvoiceNo",
    "Price": "UnitPrice",
    "Customer ID": "CustomerID",
}


def sha256(path: Path) -> str:
    """Calculate a file hash for source tracking."""
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def download(
    session: requests.Session,
    url: str,
    path: Path,
) -> None:
    """Cache successful downloads without keeping partial files."""
    if path.exists():
        if not is_zipfile(path):
            raise ValueError(
                f"Cached file is not a valid ZIP: {path}. "
                "Delete that file and rerun ingestion."
            )
        return

    temporary = path.with_suffix(".part")

    try:
        with session.get(
            url,
            stream=True,
            timeout=(30, 180),
        ) as response:
            response.raise_for_status()

            with temporary.open("wb") as handle:
                for chunk in response.iter_content(
                    chunk_size=1024 * 1024
                ):
                    if chunk:
                        handle.write(chunk)

        if not is_zipfile(temporary):
            raise ValueError(
                f"Downloaded content is not a ZIP: {url}"
            )

        temporary.replace(path)

    finally:
        temporary.unlink(missing_ok=True)


def read_workbook(path: Path) -> pd.DataFrame:
    """Read all sheets and standardize their column names."""
    frames = []

    with pd.ExcelFile(path, engine="openpyxl") as workbook:
        for sheet in workbook.sheet_names:
            print(f"  Reading sheet: {sheet}", flush=True)

            frame = pd.read_excel(
                workbook,
                sheet_name=sheet,
            )

            frame.columns = frame.columns.str.strip()
            frame = frame.rename(columns=ALIASES)

            if (
                len(frame.columns) != len(COLUMNS)
                or set(frame.columns) != set(COLUMNS)
            ):
                raise ValueError(
                    f"Unexpected schema in {path.name}/{sheet}: "
                    f"{list(frame.columns)}"
                )

            frame = frame[COLUMNS].copy()

            for column in [
                "InvoiceNo",
                "StockCode",
                "CustomerID",
            ]:
                frame[column] = (
                    frame[column]
                    .astype("string")
                    .str.replace(r"\.0$", "", regex=True)
                )

            for column in ["Description", "Country"]:
                frame[column] = frame[column].astype("string")

            frame["InvoiceDate"] = pd.to_datetime(
                frame["InvoiceDate"],
                errors="raise",
            )

            for column in ["Quantity", "UnitPrice"]:
                frame[column] = pd.to_numeric(
                    frame[column],
                    errors="raise",
                )

            frame["source_sheet"] = sheet

            # Excel row 1 contains the column headers.
            frame["source_row"] = range(2, len(frame) + 2)

            frames.append(frame)

    return pd.concat(frames, ignore_index=True)


def audit(frame: pd.DataFrame, source: str) -> dict:
    """Summarize source coverage and potential quality issues."""
    return {
        "source": source,
        "rows": len(frame),
        "date_min": str(frame["InvoiceDate"].min()),
        "date_max": str(frame["InvoiceDate"].max()),
        "distinct_invoices": int(
            frame["InvoiceNo"].nunique()
        ),
        "distinct_stock_codes": int(
            frame["StockCode"].nunique()
        ),
        "distinct_identified_customers": int(
            frame["CustomerID"].nunique()
        ),
        "missing_customer_id_rows": int(
            frame["CustomerID"].isna().sum()
        ),
        "missing_description_rows": int(
            frame["Description"].isna().sum()
        ),
        "cancellation_prefix_rows": int(
            frame["is_cancellation"].sum()
        ),
        "negative_quantity_rows": int(
            frame["Quantity"].lt(0).sum()
        ),
        "zero_quantity_rows": int(
            frame["Quantity"].eq(0).sum()
        ),
        "nonpositive_price_rows": int(
            frame["UnitPrice"].le(0).sum()
        ),
        "duplicate_business_rows_after_first": int(
            frame.duplicated(subset=COLUMNS).sum()
        ),
        "signed_line_value_gbp_unfiltered": float(
            frame["line_value_gbp"].sum()
        ),
    }


def main() -> None:
    """Ingest each source separately and save audit outputs."""
    for directory in [RAW, INTERIM, TABLES]:
        directory.mkdir(parents=True, exist_ok=True)

    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )

    summaries = []
    missingness = []

    manifest = {
        "ingested_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "python_version": platform.python_version(),
        "pandas_version": pd.__version__,
        "primary_source": "online_retail_ii",
        "sources": {},
    }

    with requests.Session() as session:
        session.mount(
            "https://",
            HTTPAdapter(max_retries=retry),
        )

        for name, source in SOURCES.items():
            print(f"\nProcessing {name}...", flush=True)

            archive = RAW / f"{name}.zip"
            workbook_path = RAW / source["workbook"]

            download(session, source["url"], archive)

            with ZipFile(archive) as zipped:
                matches = [
                    member
                    for member in zipped.namelist()
                    if Path(member).name == source["workbook"]
                ]

                if len(matches) != 1:
                    raise ValueError(
                        "Expected exactly one matching workbook "
                        f"in {archive.name}"
                    )

                # Extract only the expected workbook.
                with zipped.open(matches[0]) as src:
                    with workbook_path.open("wb") as dst:
                        while chunk := src.read(1024 * 1024):
                            dst.write(chunk)

            frame = read_workbook(workbook_path)

            if len(frame) != source["expected_rows"]:
                raise ValueError(
                    f"{name}: expected "
                    f"{source['expected_rows']:,} rows, "
                    f"received {len(frame):,}. "
                    "Investigate before proceeding."
                )

            frame["source_dataset"] = name

            frame["is_cancellation"] = (
                frame["InvoiceNo"]
                .str.upper()
                .str.startswith("C", na=False)
            )

            frame["line_value_gbp"] = (
                frame["Quantity"] * frame["UnitPrice"]
            )

            summaries.append(audit(frame, name))

            for column in COLUMNS:
                missingness.append({
                    "source": name,
                    "column": column,
                    "missing_rows": int(
                        frame[column].isna().sum()
                    ),
                    "missing_fraction": float(
                        frame[column].isna().mean()
                    ),
                })

            output_path = INTERIM / f"{name}.parquet"
            frame.to_parquet(output_path, index=False)

            manifest["sources"][name] = {
                **source,
                "archive_sha256": sha256(archive),
                "workbook_sha256": sha256(workbook_path),
                "sheet_rows": {
                    str(sheet): int(count)
                    for sheet, count in frame.groupby(
                        "source_sheet"
                    ).size().items()
                },
                "observed_rows": len(frame),
            }

            print(
                f"  Saved {len(frame):,} rows to "
                f"{output_path.name}",
                flush=True,
            )

    pd.DataFrame(summaries).to_csv(
        TABLES / "day01_source_audit.csv",
        index=False,
    )

    pd.DataFrame(missingness).to_csv(
        TABLES / "day01_missingness.csv",
        index=False,
    )

    manifest_path = TABLES / "day01_ingestion_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print("\nIngestion complete. Sources remain separate.")

    print(
        pd.DataFrame(summaries)[
            ["source", "rows", "date_min", "date_max"]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()