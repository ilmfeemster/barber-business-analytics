# Barber Analytics — Recovery / Windows Package

This package is a complete working copy of the barber analytics V1 backend as of August 2026.

## Important privacy note

`data/raw/` contains real Booksy exports with client names and other business information. Keep this project private. Do not commit the raw data, generated clean files, database, or snapshots to a public repository.

## What is included

- `booksy_pipeline.py` — cleans/validates the three Booksy exports and pseudonymizes client identity.
- `schema.sql` — SQLite base schema.
- `load_database.py` — rebuilds `data/barber_analytics.db` from clean files.
- `analytics_views.sql` — latest analytical views (V4).
- `export_dashboard.py` — applies the analytical views and creates Looker Studio-ready CSVs.
- `data/raw/` — the three real source exports used for the current analysis.
- `snapshots/` — recovery copies of the latest built database and dashboard CSVs.
- `run_refresh.bat` — Windows one-command setup/refresh.

## Windows setup — easiest path

1. Install Python 3.11+ if Python is not installed. During installation, allow the Python launcher (`py`).
2. Extract this ZIP somewhere private, for example:
   `C:\Users\<you>\Scripts\barber-analytics`
3. Double-click `run_refresh.bat` or run it from Command Prompt.

The first run creates `.venv`, installs dependencies, cleans the Booksy data, rebuilds SQLite, and exports dashboard files.

## Manual commands

From the project folder:

```bat
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python booksy_pipeline.py
python load_database.py
python export_dashboard.py
```

## Expected project flow

```text
Booksy XLSX exports
    -> booksy_pipeline.py
    -> data/clean/*.csv
    -> load_database.py
    -> data/barber_analytics.db
    -> export_dashboard.py + analytics_views.sql
    -> data/dashboard/*.csv
    -> Google Sheets
    -> Looker Studio
```

## Booksy files expected in `data/raw/`

The scripts expect these exact filenames:

- `appointments_list.xlsx`
- `client_list.xlsx`
- `sales_log.xlsx`

To refresh later, replace those three files with newer Booksy exports using the same filenames, then run `run_refresh.bat` again.

## Dashboard-ready outputs

`export_dashboard.py` creates:

- `data/dashboard/business_growth.csv`
- `data/dashboard/active_clients.csv`
- `data/dashboard/client_cohorts.csv`
- `data/dashboard/repeat_cadence.csv`
- `data/dashboard/data_dictionary.csv`

For the current Looker Studio V1, the first four are separate Google Sheet tabs.

## Current Looker Studio build state

Client-facing report name: `Franko.Fadezz Business Performance`.

Current first page is `Business Performance` and has been built around:

- Current period: August 2026 through Aug. 25
- Scorecards: Completed Appointments = 49; New Clients = 14; Returning Clients = 27
- Line chart: Completed Appointments by Month
- Line chart: New vs. Returning Clients

The dashboard is for the barber's operational benefit. The consulting intervention/case-study story should be analyzed separately rather than cluttering the client dashboard.

## Important analytical conventions

- Completed non-administrative Booksy appointments are the primary business-growth KPI.
- `LEAVE A REVIEW` administrative bookings are excluded from service-demand analysis.
- Booksy revenue is incomplete and should not be presented as total business revenue.
- Appointment-level reliable history begins July 25, 2025.
- July 2025 and the current August 2026 reporting period are partial months.
- Client identity is a derived pseudonymous surrogate, not a true Booksy customer ID.
- Return/retention analysis uses distinct completed service days so multiple services on the same day do not count as a repeat visit.

## Recovery snapshot

`snapshots/barber_analytics_v4_snapshot.db` is the latest previously built analytical database. It is included only as a recovery reference; the preferred workflow is to rebuild the database from the raw exports.
