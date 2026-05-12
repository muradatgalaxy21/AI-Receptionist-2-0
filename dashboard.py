# dashboard.py
"""
Streamlit dashboard for AI Receptionist MVP.
Displays call KPIs, revenue recovery, intent distribution, and a searchable call log.
"""

import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# -----------------------------
# Configuration & Styling
# -----------------------------
st.set_page_config(page_title="AI Receptionist Dashboard", layout="wide")

# Simple CSS for medical aesthetic (blue and white)
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    .header {
        font-size: 2.8rem;
        font-weight: 700;
        background: -webkit-linear-gradient(45deg, #4f8cff, #7c5cfc);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 2rem;
        padding-top: 1rem;
    }
    
    .kpi-card {
        background: rgba(26, 30, 53, 0.6);
        border: 1px solid rgba(79, 140, 255, 0.2);
        border-radius: 16px;
        padding: 1.5rem;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        text-align: center;
        backdrop-filter: blur(10px);
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }
    
    .kpi-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 25px rgba(79, 140, 255, 0.2);
        border-color: rgba(79, 140, 255, 0.4);
    }
    
    .kpi-card h3 {
        color: #8b8fa8;
        font-size: 1.1rem !important;
        font-weight: 600;
        margin-bottom: 0.5rem;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    .kpi-card p {
        color: #ffffff;
        font-size: 2.5rem !important;
        font-weight: 700;
        margin: 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# Authentication (simple)
# -----------------------------
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.sidebar.title("Login")
    user = st.sidebar.text_input("Username")
    pwd = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Login"):
        # In a real app replace with secure validation
        if user == "admin" and pwd == "admin":
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.sidebar.error("Invalid credentials")
    st.stop()

# -----------------------------
# Header
# -----------------------------
st.markdown("<div class='header'>AI and Beyond – Receptionist Dashboard</div>", unsafe_allow_html=True)

# -----------------------------
# Load Data
# -----------------------------
DATA_PATH = Path(__file__).parent / "call_logs.csv"

@st.cache_data(ttl=5)
def load_data() -> pd.DataFrame:
    if not DATA_PATH.exists():
        df = pd.DataFrame(columns=[
            "timestamp",
            "caller_id",
            "patient_name",
            "call_duration",
            "intent",
            "summary",
            "status",
            "estimated_value",
            "recording_url",
        ])
    else:
        df = pd.read_csv(DATA_PATH)
    # Ensure proper types
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["call_duration"] = pd.to_numeric(df["call_duration"], errors="coerce")
    df["estimated_value"] = pd.to_numeric(df["estimated_value"], errors="coerce")
    return df

df = load_data()

# -----------------------------
# Sidebar Filters
# -----------------------------
st.sidebar.subheader("Filters")
# Date range filter
min_date = df["timestamp"].min().date() if not df.empty else datetime.today().date()
max_date = df["timestamp"].max().date() if not df.empty else datetime.today().date()
start_date = st.sidebar.date_input("Start date", min_date)
end_date = st.sidebar.date_input("End date", max_date)

# Search by phone number (caller_id)
search_phone = st.sidebar.text_input("Search by caller ID")

# Apply filters
mask = (df["timestamp"].dt.date >= start_date) & (df["timestamp"].dt.date <= end_date)
if search_phone:
    mask &= df["caller_id"].astype(str).str.contains(search_phone, na=False)
filtered_df = df[mask]

# -----------------------------
# KPI Row
# -----------------------------
col1, col2, col3 = st.columns(3)
with col1:
    total_calls = len(filtered_df)
    st.markdown("""<div class='kpi-card'>
        <h3>Total Calls Handled</h3>
        <p>{}</p>
    </div>""".format(total_calls), unsafe_allow_html=True)
with col2:
    confirmed = filtered_df[filtered_df["status"] == "Confirmed"].shape[0]
    st.markdown("""<div class='kpi-card'>
        <h3>Appointments Confirmed</h3>
        <p>{}</p>
    </div>""".format(confirmed), unsafe_allow_html=True)
with col3:
    revenue = filtered_df["estimated_value"].sum()
    st.markdown("""<div class='kpi-card'>
        <h3>Total Revenue Recovered</h3>
        <p>${:,.2f}</p>
    </div>""".format(revenue), unsafe_allow_html=True)

st.markdown("---")

# -----------------------------
# Visualizations
# -----------------------------
# Revenue Recovery Bar Chart
st.subheader("Revenue Recovery per Day")
if not filtered_df.empty:
    rev_daily = (
        filtered_df.groupby(filtered_df["timestamp"].dt.date)["estimated_value"]
        .sum()
        .reset_index(name="revenue")
    )
    rev_chart = st.bar_chart(data=rev_daily.set_index("timestamp"))
else:
    st.info("No data to display.")

# Call Intent Pie Chart
st.subheader("Call Intent Distribution")
if not filtered_df.empty:
    intent_counts = filtered_df["intent"].value_counts()
    st.pyplot(intent_counts.plot.pie(autopct="%1.1f%%", explode=[0.05]*len(intent_counts), shadow=True).figure)
else:
    st.info("No data to display.")

st.markdown("---")

# -----------------------------
# Lead Table
# -----------------------------
st.subheader("Call Log")
if not filtered_df.empty:
    # Highlight rows needing follow‑up
    def highlight_rows(row):
        return ["background-color: #fff3cd" if row["status"] == "Follow-up Needed" else "" for _ in row]
    styled_df = filtered_df.style.apply(highlight_rows, axis=1)
    st.dataframe(styled_df, use_container_width=True)

    # Row selection – using timestamp as identifier
    selected_ts = st.selectbox(
        "Select a call to view summary",
        options=filtered_df["timestamp"].astype(str),
        format_func=lambda x: x,
    )
    if selected_ts:
        summary_text = filtered_df.loc[filtered_df["timestamp"].astype(str) == selected_ts, "summary"].values[0]
        st.text_area("Full Summary", value=summary_text, height=200)
else:
    st.info("No calls match the current filters.")

# Auto‑refresh every 30 seconds to pick up new rows
st_autorefresh(interval=30_000, limit=None, key="dashboard_refresh")