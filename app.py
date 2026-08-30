from pathlib import Path

import pandas as pd
import streamlit as st


DATA_DIR = Path(__file__).parent / "data" / "dashboard"
BUSINESS_GROWTH_FILE = DATA_DIR / "business_growth.csv"


@st.cache_data
def load_business_growth() -> pd.DataFrame:
    df = pd.read_csv(BUSINESS_GROWTH_FILE)
    df["month"] = pd.to_datetime(df["month"], format="%Y-%m")
    return df.sort_values("month").reset_index(drop=True)


def format_month(value: pd.Timestamp) -> str:
    return value.strftime("%B %Y")


st.set_page_config(
    page_title="Barber Business Performance",
    layout="wide",
)

st.title("Business Performance")
st.caption("Monthly appointment and client growth")

try:
    growth = load_business_growth()
except FileNotFoundError:
    st.error(
        "Dashboard data is missing. Run `python export_dashboard.py` to create "
        "`data/dashboard/business_growth.csv`."
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

st.caption(
    "Source: Booksy reporting. Completed appointments exclude "
    "administrative review-only bookings."
)
