# Barber Growth Analytics

An end-to-end analytics solution for an independent barber business, built to turn operational booking data into useful business performance insights.

The project combines Python-based data preparation, SQLite/SQL analytics, and a Streamlit client dashboard.

## Project Objective

The goal is to help a small service business understand:

- Appointment volume and growth
- New-client acquisition
- Returning-client activity
- Customer retention and repeat behavior
- Changes in the active client base
- Business performance trends over time

The project is designed as a practical business analytics solution rather than simply a dashboard exercise.

## Architecture

```text
Booksy exports
      ↓
Python ETL / validation
      ↓
SQLite
      ↓
SQL analytical views
      ↓
Aggregate dashboard datasets
      ↓
Streamlit
      ↓
Client-facing web dashboard