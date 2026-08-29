from __future__ import annotations

import argparse
import math
import sqlite3
from pathlib import Path

import pandas as pd


FILES = {
    "clients": "clients_clean.csv",
    "appointments": "appointments_clean.csv",
    "sales": "sales_clean.csv",
}

LOAD_COLUMNS = {
    "clients": [
        "client_key", "groups", "bookings_count", "no_shows_count", "first_visit",
        "last_visit", "bookings_value", "revenue_net", "discount", "tax",
        "tip_amount", "total_revenue",
    ],
    "appointments": [
        "booking_id", "appointment_datetime", "main_category", "service", "staffer",
        "service_value", "addons_value", "revenue_net", "discount", "tax",
        "tip_amount", "total_revenue", "status", "service_length_minutes",
        "client_key", "client_match_status",
    ],
    "sales": [
        "checkout_date", "transaction_id", "type", "category", "item", "staffer",
        "quantity", "booking_date", "service_value", "addons_value", "revenue_net",
        "discount", "tax", "tip_amount", "total_revenue", "payment_type",
        "client_key", "client_match_status",
    ],
}


def sql_value(value):
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def read_clean_csv(path: Path, table: str) -> pd.DataFrame:
    dtype = {}
    if table == "clients":
        dtype["client_key"] = "string"
    elif table == "appointments":
        dtype.update({"booking_id": "string", "client_key": "string"})
    elif table == "sales":
        dtype.update({"transaction_id": "string", "client_key": "string"})

    df = pd.read_csv(path, dtype=dtype)
    required = LOAD_COLUMNS[table]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"{table}: missing required clean columns: {missing}")
    return df[required].copy()


def insert_dataframe(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> int:
    columns = LOAD_COLUMNS[table]
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)
    sql = f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})"
    rows = [tuple(sql_value(v) for v in row) for row in df.itertuples(index=False, name=None)]
    conn.executemany(sql, rows)
    return len(rows)


def validate_database(conn: sqlite3.Connection, expected_counts: dict[str, int]) -> None:
    for table, expected in expected_counts.items():
        actual = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if actual != expected:
            raise RuntimeError(f"{table}: expected {expected} rows, database contains {actual}")

    fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if fk_violations:
        raise RuntimeError(f"Foreign-key violations found: {fk_violations[:10]}")

    duplicate_appointments = conn.execute(
        "SELECT COUNT(*) - COUNT(DISTINCT booking_id) FROM appointments"
    ).fetchone()[0]
    if duplicate_appointments:
        raise RuntimeError(f"appointments: {duplicate_appointments} duplicate booking IDs")


def build_database(clean_dir: Path, db_path: Path, schema_path: Path) -> None:
    frames = {}
    for table, filename in FILES.items():
        path = clean_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Clean input not found: {path}")
        frames[table] = read_clean_csv(path, table)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = db_path.with_suffix(db_path.suffix + ".tmp")
    if temp_path.exists():
        temp_path.unlink()

    try:
        with sqlite3.connect(temp_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(schema_path.read_text(encoding="utf-8"))

            counts = {}
            with conn:
                # Parent table first so foreign keys can be enforced during child loads.
                for table in ("clients", "appointments", "sales"):
                    counts[table] = insert_dataframe(conn, table, frames[table])

            validate_database(conn, counts)

            statuses = conn.execute(
                "SELECT status, COUNT(*) FROM appointments GROUP BY status ORDER BY status"
            ).fetchall()
            unique_transactions = conn.execute(
                "SELECT COUNT(DISTINCT transaction_id) FROM sales"
            ).fetchone()[0]

        temp_path.replace(db_path)

    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise

    print(f"Database built: {db_path}")
    print(f"clients:      {counts['clients']}")
    print(f"appointments: {counts['appointments']}")
    print(f"sales lines:  {counts['sales']}")
    print(f"sales transactions: {unique_transactions}")
    print("appointment statuses:")
    for status, count in statuses:
        print(f"  {status}: {count}")
    print("foreign-key check: PASS")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild the barber analytics SQLite database.")
    parser.add_argument("--clean-dir", type=Path, default=Path("data/clean"))
    parser.add_argument("--db-path", type=Path, default=Path("data/barber_analytics.db"))
    parser.add_argument("--schema", type=Path, default=Path("schema.sql"))
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    build_database(args.clean_dir, args.db_path, args.schema)
