from pathlib import Path

import pandas as pd
import streamlit as st


DATA_DIR = Path(__file__).parent / "data" / "dashboard"
BUSINESS_GROWTH_FILE = DATA_DIR / "business_growth.csv"
CLIENT_COHORTS_FILE = DATA_DIR / "client_cohorts.csv"


@st.cache_data
def load_business_growth() -> pd.DataFrame:
    df = pd.read_csv(BUSINESS_GROWTH_FILE)
    df["month"] = pd.to_datetime(df["month"], format="%Y-%m")
    return df.sort_values("month").reset_index(drop=True)


@st.cache_data
def load_client_cohorts() -> pd.DataFrame:
    df = pd.read_csv(CLIENT_COHORTS_FILE)
    df["cohort_month"] = pd.to_datetime(df["cohort_month"], format="%Y-%m")
    return df.sort_values("cohort_month").reset_index(drop=True)


def format_month(value: pd.Timestamp) -> str:
    return value.strftime("%B %Y")


def format_repeat_rate(row: pd.Series, window_days: int) -> str:
    """Format a cohort repeat rate with its auditable numerator and denominator."""
    eligible = int(row[f"clients_eligible_{window_days}d"])
    if eligible == 0:
        return "Not yet eligible"

    repeated = int(row[f"clients_repeated_{window_days}d"])
    rate = row[f"repeat_rate_{window_days}d"]
    if pd.isna(rate):
        return "—"

    return f"{rate:.1%} ({repeated} of {eligible} eligible)"


st.set_page_config(
    page_title="Barber Business Performance",
    layout="wide",
)

st.title("Business Performance")
st.caption("Monthly appointment and client growth")

try:
    growth = load_business_growth()
    cohorts = load_client_cohorts()
except FileNotFoundError:
    st.error(
        "Dashboard data is missing. Run `python export_dashboard.py` to create "
        "the files in `data/dashboard`."
    )
    st.stop()

latest = growth.iloc[-1]
latest_month = format_month(latest["month"])

if int(latest["is_partial_month"]) == 1:
    st.caption(f"{latest_month} is a partial month.")
else:
    st.caption(latest_month)

completed_col, new_col, returning_col = st.columns(3)

with completed_col:
    st.metric(
        "Completed Appointments",
        int(latest["completed_service_appointments"]),
    )

with new_col:
    st.metric(
        "New Clients",
        int(latest["observed_new_clients"]),
    )

with returning_col:
    st.metric(
        "Returning Clients",
        int(latest["returning_clients"]),
    )

st.subheader("Completed Appointments by Month")
appointments_chart = (
    growth.set_index("month")[["completed_service_appointments"]]
    .rename(columns={"completed_service_appointments": "Completed Appointments"})
)
st.line_chart(
    appointments_chart,
    x_label="Month",
    y_label="Appointments",
)

st.subheader("New vs. Returning Clients")
client_chart = (
    growth.set_index("month")[["observed_new_clients", "returning_clients"]]
    .rename(
        columns={
            "observed_new_clients": "New Clients",
            "returning_clients": "Returning Clients",
        }
    )
)
st.line_chart(
    client_chart,
    x_label="Month",
    y_label="Clients",
)

st.subheader("Appointment Leakage")
st.caption(
    "Cancelled and no-show appointments are booked demand that did not turn into "
    "a completed service."
)

lost_bookings = int(
    latest["cancelled_service_appointments"]
    + latest["no_show_service_appointments"]
)
lost_col, cancellation_col, no_show_col = st.columns(3)

with lost_col:
    st.metric("Lost Bookings", lost_bookings)
    st.caption(
        f"{int(latest['cancelled_service_appointments'])} cancelled + "
        f"{int(latest['no_show_service_appointments'])} no-show"
    )

with cancellation_col:
    st.metric("Cancellation Rate", f"{latest['cancellation_rate']:.1%}")

with no_show_col:
    st.metric("No-Show Rate", f"{latest['no_show_rate']:.1%}")

leakage_chart = (
    growth.set_index("month")[["cancellation_rate", "no_show_rate"]]
    .mul(100)
    .rename(
        columns={
            "cancellation_rate": "Cancellation Rate",
            "no_show_rate": "No-Show Rate",
        }
    )
)
st.line_chart(
    leakage_chart,
    x_label="Month",
    y_label="Rate (%)",
)

st.subheader("New-Client Retention by Cohort")
st.caption(
    "Percentage of newly acquired clients who completed a second visit within "
    "42 or 90 days of their first completed visit. Rates include the returning "
    "client count and eligible-client denominator."
)

retention_table = pd.DataFrame(
    {
        "Acquisition Cohort": cohorts["cohort_month"].map(format_month),
        "Acquired Clients": cohorts["acquired_clients"].astype(int),
        "42-Day Repeat Rate": cohorts.apply(format_repeat_rate, axis=1, window_days=42),
        "90-Day Repeat Rate": cohorts.apply(format_repeat_rate, axis=1, window_days=90),
    }
)
st.dataframe(retention_table, hide_index=True, use_container_width=True)

st.caption(
    "Source: Booksy reporting. Completed appointments exclude "
    "administrative review-only bookings."
)
