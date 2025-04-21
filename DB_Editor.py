import streamlit as st
import pandas as pd
from supabase import create_client, Client

# --- Load Supabase credentials from secrets.toml ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

# --- Initialize Supabase client ---
@st.cache_resource
def init_connection():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = init_connection()

# --- Streamlit App UI ---
st.set_page_config(page_title="Pump Selection Data", layout="wide")
st.title("💧 Pump Selection Data Viewer")

try:
    # Fetch up to 2000 rows from your 'pump_selection_data' table
    response = supabase.table("pump_selection_data").select("*").range(0, 1999).execute()
    df = pd.DataFrame(response.data)

    if df.empty:
        st.info("No data found in 'pump_selection_data'.")
    else:
        st.subheader("📋 Raw Data Table")
        st.dataframe(df, use_container_width=True)

        st.subheader("🔍 Summary View")
        for index, row in df.iterrows():
            name = row.get("name", "Unnamed Pump")
            flow = row.get("flow_rate", "N/A")
            head = row.get("head_height", "N/A")
            st.markdown(f"- **{name}**: {flow} LPM @ {head} m head")

except Exception as e:
    st.error(f"Error fetching data: {e}")
