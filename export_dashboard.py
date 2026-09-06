from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd


EXPORTS = {
    "business_growth.csv": """
        SELECT
            month,
            booked_service_appointments,
            completed_service_appointments,
            cancelled_service_appointments,
            no_show_service_appointments,
            unique_completed_clients,
            observed_new_clients,
            returning_clients,
            completion_rate,
            cancellation_rate,
            no_show_rate,
            completed_service_minutes,
            completed_service_value,
            intervention_period,
            is_partial_month
        FROM v_monthly_performance
        ORDER BY month
    """,
    "active_clients.csv": """
        SELECT
            month,
            month_end,
            active_clients_42d,
            active_clients_90d,
            intervention_period,
            is_partial_month
        FROM v_monthly_active_clients
        ORDER BY month
    """,
    "client_cohorts.csv": """
        SELECT
            cohort_month,
            acquired_clients,
            clients_ever_repeated_observed,
            observed_repeat_rate,
            clients_eligible_42d,
            clients_repeated_42d,
            repeat_rate_42d,
            clients_eligible_90d,
            clients_repeated_90d,
            repeat_rate_90d,
            avg_days_to_second_visit,
            intervention_period,
            is_partial_month
        FROM v_client_cohorts
        ORDER BY cohort_month
    """,
    "repeat_cadence.csv": """
        SELECT
            cadence_band,
            return_intervals,
            pct_of_return_intervals
        FROM v_repeat_cadence_summary
        ORDER BY cadence_band
    """,
}

DATA_DICTIONARY = [
    ("business_growth", "completed_service_appointments", "Primary growth KPI: completed non-administrative Booksy appointments."),
    ("business_growth", "observed_new_clients", "Clients whose first observed completed service visit occurs in the month."),
    ("business_growth", "returning_clients", "Clients completing service in the month who had a prior observed completed visit."),
    ("business_growth", "unique_completed_clients", "Distinct resolved clients with a completed service in the month."),
    ("business_growth", "cancelled_service_appointments", "Booked non-administrative appointments cancelled during the month."),
    ("business_growth", "no_show_service_appointments", "Booked non-administrative appointments marked as no-shows during the month."),
    ("business_growth", "cancellation_rate", "Cancelled service appointments divided by booked service appointments for the month."),
    ("business_growth", "no_show_rate", "No-show service appointments divided by booked service appointments for the month."),
    ("business_growth", "intervention_period", "pre_gbp, gbp_creation_month, or post_gbp."),
    ("business_growth", "is_partial_month", "1 for incomplete edge months in the reporting window."),
    ("active_clients", "active_clients_42d", "Distinct clients with a completed service in the trailing 42 days at month-end."),
    ("active_clients", "active_clients_90d", "Distinct clients with a completed service in the trailing 90 days at month-end."),
    ("client_cohorts", "repeat_rate_42d", "Eligible acquired clients returning for a second completed service within 42 days."),
    ("client_cohorts", "repeat_rate_90d", "Eligible acquired clients returning for a second completed service within 90 days."),
    ("repeat_cadence", "pct_of_return_intervals", "Share of observed intervals between consecutive completed service days."),
]


def apply_views(conn: sqlite3.Connection, views_path: Path) -> None:
    if not views_path.exists():
        raise FileNotFoundError(f"Analytics views file not found: {views_path}")
    conn.executescript(views_path.read_text(encoding="utf-8"))


def validate_views(conn: sqlite3.Connection) -> None:
    required = {
        "v_monthly_performance",
        "v_monthly_active_clients",
        "v_client_cohorts",
        "v_repeat_cadence_summary",
    }
    available = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'view'"
        ).fetchall()
    }
    missing = sorted(required - available)
    if missing:
        raise RuntimeError(f"Required analytics views are missing: {missing}")


def export_dashboard(db_path: Path, views_path: Path, out_dir: Path) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    out_dir.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        apply_views(conn, views_path)
        validate_views(conn)

        row_counts = {}
        for filename, query in EXPORTS.items():
            df = pd.read_sql_query(query, conn)
            df.to_csv(out_dir / filename, index=False)
            row_counts[filename] = len(df)

    dictionary = pd.DataFrame(
        DATA_DICTIONARY,
        columns=["dataset", "field", "definition"],
    )
    dictionary.to_csv(out_dir / "data_dictionary.csv", index=False)

    print(f"Dashboard exports written to: {out_dir}")
    for filename, count in row_counts.items():
        print(f"  {filename}: {count} rows")
    print(f"  data_dictionary.csv: {len(dictionary)} rows")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply analytics views and export Looker Studio-ready CSVs."
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("data/barber_analytics.db"),
        help="SQLite database built by load_database.py",
    )
    parser.add_argument(
        "--views",
        type=Path,
        default=Path("analytics_views.sql"),
        help="SQL file containing the analytical views",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/dashboard"),
        help="Directory for dashboard-ready CSV exports",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    export_dashboard(args.db_path, args.views, args.out_dir)
