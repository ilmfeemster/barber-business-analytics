from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


HEADER_ROW = 7
CORE_FILES = {
    "appointments": "appointments_list.xlsx",
    "clients": "client_list.xlsx",
    "sales": "sales_log.xlsx",
}
MONEY_COLUMNS = {
    "service_value",
    "addons_value",
    "revenue_net",
    "discount",
    "tax",
    "tip_amount",
    "total_revenue",
    "bookings_value",
}
ALLOWED_APPOINTMENT_STATUSES = {"Completed", "Cancelled", "No-show"}


@dataclass
class ValidationResult:
    dataset: str
    rows: int
    errors: list[str]
    warnings: list[str]
    metrics: dict


def snake_case(value: object) -> str:
    text = str(value).strip().replace("&", " and ").replace("/", " ").replace("-", " ")
    text = re.sub(r"[^A-Za-z0-9]+", "_", text)
    return text.strip("_").lower()


def normalize_client_name(value: object) -> str | None:
    """Normalize spacing while preserving case because case can help disambiguate Booksy records."""
    if pd.isna(value):
        return None
    text = " ".join(str(value).strip().split())
    if not text:
        return None
    if text.casefold() in {"walk-in", "walk in", "walkin"}:
        return "WALK_IN"
    return text


def make_client_key(name: object, first_visit: object) -> str | None:
    """Create a deterministic surrogate key from Booksy client name + first-visit date."""
    normalized_name = normalize_client_name(name)
    if normalized_name is None or pd.isna(first_visit):
        return None
    first_visit_ts = pd.Timestamp(first_visit)
    identity = f"{normalized_name}|{first_visit_ts.date().isoformat()}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"client_{digest[:16]}"


def normalize_identifier(value: object) -> str | None:
    """Preserve source IDs as text and remove Excel's trailing .0 for integer IDs."""
    if pd.isna(value):
        return None
    if isinstance(value, (int,)):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0", text):
        return text[:-2]
    return text or None


def parse_duration_minutes(value: object) -> int | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    match = re.fullmatch(r"(?:(\d+)h:)?(\d+)min", text)
    if not match:
        return None
    return int(match.group(1) or 0) * 60 + int(match.group(2))


def read_booksy_export(path: Path) -> tuple[pd.DataFrame, dict]:
    raw = pd.read_excel(path, header=None)
    metadata_text = " | ".join(
        str(v).strip()
        for v in raw.iloc[:HEADER_ROW].to_numpy().ravel()
        if pd.notna(v) and str(v).strip()
    )
    period_match = re.search(
        r"Period from\s+(\d{1,2}/\d{1,2}/\d{2,4})\s+to\s+(\d{1,2}/\d{1,2}/\d{2,4})",
        metadata_text,
        flags=re.IGNORECASE,
    )
    metadata = {
        "source_file": path.name,
        "report_period_start": period_match.group(1) if period_match else None,
        "report_period_end": period_match.group(2) if period_match else None,
    }

    df = pd.read_excel(path, header=HEADER_ROW)
    df = df.dropna(axis=1, how="all")

    # Booksy exports two presentation-only leading columns: blank spacer + row number.
    while len(df.columns) and str(df.columns[0]).startswith("Unnamed"):
        df = df.iloc[:, 1:]

    df.columns = [snake_case(c) for c in df.columns]
    total_mask = df.apply(
        lambda row: row.astype(str).str.strip().str.casefold().eq("total").any(), axis=1
    )
    df = df.loc[~total_mask].dropna(how="all").reset_index(drop=True)
    return df, metadata


def convert_money(df: pd.DataFrame) -> pd.DataFrame:
    for column in MONEY_COLUMNS.intersection(df.columns):
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def prepare_clients(path: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Return analysis-ready clients plus a private matching reference containing names."""
    df, metadata = read_booksy_export(path)
    df = df.rename(
        columns={
            "first_and_last_name": "client_name",
            "no_of_bookings": "bookings_count",
            "no_of_no_shows": "no_shows_count",
        }
    )
    df["client_name"] = df["client_name"].map(normalize_client_name)
    df["first_visit"] = pd.to_datetime(df["first_visit"], errors="coerce", format="mixed")
    df["last_visit"] = pd.to_datetime(df["last_visit"], errors="coerce", format="mixed")
    for column in ("bookings_count", "no_shows_count"):
        df[column] = pd.to_numeric(df[column], errors="coerce").astype("Int64")
    df = convert_money(df)
    df["client_key"] = [make_client_key(n, d) for n, d in zip(df["client_name"], df["first_visit"])]

    reference = df[["client_key", "client_name", "first_visit"]].copy()
    reference["client_name_casefold"] = reference["client_name"].str.casefold()

    clean = df.drop(columns=["client_name"]).copy()
    cols = ["client_key"] + [c for c in clean.columns if c != "client_key"]
    return clean[cols], reference, metadata


def resolve_client(name: object, event_date: object, reference: pd.DataFrame) -> tuple[str | None, str]:
    normalized = normalize_client_name(name)
    if normalized is None or normalized == "WALK_IN":
        return None, "unmatched"

    event_ts = pd.Timestamp(event_date) if pd.notna(event_date) else pd.NaT

    exact = reference[reference["client_name"] == normalized]
    if len(exact) == 1:
        return exact.iloc[0]["client_key"], "exact_name"
    if len(exact) > 1:
        key = _resolve_candidates_by_date(exact, event_ts)
        return (key, "event_date") if key else (None, "ambiguous")

    folded = reference[reference["client_name_casefold"] == normalized.casefold()]
    if len(folded) == 1:
        return folded.iloc[0]["client_key"], "casefold_unique"
    if len(folded) > 1:
        key = _resolve_candidates_by_date(folded, event_ts)
        return (key, "event_date") if key else (None, "ambiguous")

    return None, "unmatched"


def _resolve_candidates_by_date(candidates: pd.DataFrame, event_ts: pd.Timestamp) -> str | None:
    if pd.isna(event_ts):
        return None

    same_day = candidates[candidates["first_visit"].dt.date == event_ts.date()]
    if len(same_day) == 1:
        return str(same_day.iloc[0]["client_key"])

    eligible = candidates[candidates["first_visit"].dt.date <= event_ts.date()]
    if len(eligible) == 1:
        return str(eligible.iloc[0]["client_key"])

    return None


def clean_appointments(path: Path, client_reference: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    df, metadata = read_booksy_export(path)
    df = df.rename(columns={"date_and_time": "appointment_datetime", "add_ons_value": "addons_value"})
    df["appointment_datetime"] = pd.to_datetime(df["appointment_datetime"], errors="coerce", format="mixed")
    df["booking_id"] = df["booking_id"].map(normalize_identifier).astype("string")
    df["service_length_minutes"] = df["service_length"].map(parse_duration_minutes)
    df = df.drop(columns=["service_length"])
    df = convert_money(df)

    resolved = [
        resolve_client(name, event_date, client_reference)
        for name, event_date in zip(df["client"], df["appointment_datetime"])
    ]
    df["client_key"] = [x[0] for x in resolved]
    df["client_match_status"] = [x[1] for x in resolved]
    df = df.drop(columns=["client"])
    return df, metadata


def clean_sales(path: Path, client_reference: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    df, metadata = read_booksy_export(path)
    df = df.rename(columns={"service_product_add_on": "item", "add_on_value": "addons_value"})
    for column in ("checkout_date", "booking_date"):
        df[column] = pd.to_datetime(df[column], errors="coerce", format="mixed")
    df["transaction_id"] = df["transaction_id"].map(normalize_identifier).astype("string")
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df = convert_money(df)

    resolved = [
        resolve_client(name, event_date, client_reference)
        for name, event_date in zip(df["client"], df["booking_date"].fillna(df["checkout_date"]))
    ]
    df["client_key"] = [x[0] for x in resolved]
    df["client_match_status"] = [x[1] for x in resolved]
    df = df.drop(columns=["client"])
    return df, metadata


def _date_text(series: pd.Series | None, maximum: bool = False) -> str | None:
    if series is None:
        return None
    valid = series.dropna()
    if valid.empty:
        return None
    value = valid.max() if maximum else valid.min()
    return pd.Timestamp(value).isoformat()


def validate_clients(df: pd.DataFrame) -> ValidationResult:
    errors, warnings = [], []
    required = {"client_key", "first_visit", "last_visit"}
    missing = sorted(required - set(df.columns))
    if missing:
        errors.append(f"Missing required columns: {missing}")
    if "client_key" in df:
        missing_keys = int(df["client_key"].isna().sum())
        duplicate_keys = int(df["client_key"].duplicated(keep=False).sum())
        if missing_keys:
            errors.append(f"{missing_keys} client rows have no generated client_key.")
        if duplicate_keys:
            errors.append(f"{duplicate_keys} client rows share a generated client_key.")
    if {"first_visit", "last_visit"}.issubset(df.columns):
        reversed_dates = int((df["first_visit"] > df["last_visit"]).fillna(False).sum())
        if reversed_dates:
            errors.append(f"{reversed_dates} clients have first_visit after last_visit.")
    metrics = {
        "first_visit_min": _date_text(df.get("first_visit")),
        "last_visit_max": _date_text(df.get("last_visit"), maximum=True),
        "unique_client_keys": int(df["client_key"].nunique()) if "client_key" in df else None,
    }
    return ValidationResult("clients", len(df), errors, warnings, metrics)


def validate_appointments(df: pd.DataFrame) -> ValidationResult:
    errors, warnings = [], []
    required = {"appointment_datetime", "booking_id", "service", "status", "client_match_status"}
    missing = sorted(required - set(df.columns))
    if missing:
        errors.append(f"Missing required columns: {missing}")
    if "booking_id" in df:
        blank_ids = int(df["booking_id"].isna().sum())
        duplicate_ids = int(df["booking_id"].duplicated(keep=False).sum())
        if blank_ids:
            errors.append(f"{blank_ids} rows have a missing Booking ID.")
        if duplicate_ids:
            errors.append(f"{duplicate_ids} appointment rows share a Booking ID.")
    if "appointment_datetime" in df and df["appointment_datetime"].isna().any():
        errors.append(f"{int(df['appointment_datetime'].isna().sum())} rows have invalid appointment datetime.")
    if "status" in df:
        unexpected = sorted(set(df["status"].dropna().astype(str)) - ALLOWED_APPOINTMENT_STATUSES)
        if unexpected:
            warnings.append(f"Unexpected appointment statuses: {unexpected}")
    match_counts = df["client_match_status"].value_counts(dropna=False).to_dict()
    ambiguous = int((df["client_match_status"] == "ambiguous").sum())
    if ambiguous:
        warnings.append(f"{ambiguous} appointments have ambiguous client identity and remain unlinked.")
    metrics = {
        "date_min": _date_text(df.get("appointment_datetime")),
        "date_max": _date_text(df.get("appointment_datetime"), maximum=True),
        "unique_booking_ids": int(df["booking_id"].nunique()),
        "linked_clients": int(df["client_key"].nunique()),
        "status_counts": {str(k): int(v) for k, v in df["status"].value_counts(dropna=False).to_dict().items()},
        "client_match_counts": {str(k): int(v) for k, v in match_counts.items()},
    }
    return ValidationResult("appointments", len(df), errors, warnings, metrics)


def validate_sales(df: pd.DataFrame) -> ValidationResult:
    errors, warnings = [], []
    required = {"checkout_date", "transaction_id", "type", "client_match_status"}
    missing = sorted(required - set(df.columns))
    if missing:
        errors.append(f"Missing required columns: {missing}")
    if "checkout_date" in df and df["checkout_date"].isna().any():
        errors.append(f"{int(df['checkout_date'].isna().sum())} rows have invalid checkout date.")
    if "transaction_id" in df and df["transaction_id"].isna().any():
        errors.append(f"{int(df['transaction_id'].isna().sum())} sales rows have missing transaction ID.")
    match_counts = df["client_match_status"].value_counts(dropna=False).to_dict()
    ambiguous = int((df["client_match_status"] == "ambiguous").sum())
    unmatched = int((df["client_match_status"] == "unmatched").sum())
    if ambiguous:
        warnings.append(f"{ambiguous} sales rows have ambiguous client identity and remain unlinked.")
    if unmatched:
        warnings.append(f"{unmatched} sales rows could not be linked to a client record.")
    metrics = {
        "date_min": _date_text(df.get("checkout_date")),
        "date_max": _date_text(df.get("checkout_date"), maximum=True),
        "unique_transactions": int(df["transaction_id"].nunique()),
        "linked_clients": int(df["client_key"].nunique()),
        "client_match_counts": {str(k): int(v) for k, v in match_counts.items()},
    }
    return ValidationResult("sales", len(df), errors, warnings, metrics)


def write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, date_format="%Y-%m-%d %H:%M:%S")


def run_pipeline(input_dir: Path, output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_dir": str(input_dir.resolve()),
        "output_dir": str(output_dir.resolve()),
        "datasets": {},
    }

    clients_path = input_dir / CORE_FILES["clients"]
    appointments_path = input_dir / CORE_FILES["appointments"]
    sales_path = input_dir / CORE_FILES["sales"]
    missing = [str(p) for p in (clients_path, appointments_path, sales_path) if not p.exists()]
    if missing:
        print(json.dumps({"errors": [f"Source file not found: {p}" for p in missing]}, indent=2))
        return 1

    clients, client_reference, client_meta = prepare_clients(clients_path)
    appointments, appointment_meta = clean_appointments(appointments_path, client_reference)
    sales, sales_meta = clean_sales(sales_path, client_reference)

    datasets = {
        "clients": (clients, client_meta, validate_clients(clients)),
        "appointments": (appointments, appointment_meta, validate_appointments(appointments)),
        "sales": (sales, sales_meta, validate_sales(sales)),
    }

    any_errors = False
    for dataset, (df, metadata, result) in datasets.items():
        any_errors = any_errors or bool(result.errors)
        output_file = output_dir / f"{dataset}_clean.csv"
        write_csv(df, output_file)
        report["datasets"][dataset] = {
            "metadata": metadata,
            "validation": asdict(result),
            "output_file": output_file.name,
        }

    report_path = output_dir / "validation_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print("\nPipeline completed with validation errors." if any_errors else "\nPipeline completed successfully.")
    return 1 if any_errors else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean and validate core Booksy XLSX exports.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/clean"))
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(run_pipeline(args.input_dir, args.output_dir))
