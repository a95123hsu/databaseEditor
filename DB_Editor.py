import streamlit as st
import pandas as pd
from supabase import create_client, Client

# Load secrets
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

@st.cache_resource
def init_connection():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = init_connection()

st.title("📊 Pump Data Viewer")

try:
    response = supabase.table("pump_selection_data").select("*").range(0, 1999).execute()
    df = pd.DataFrame(response.data)

    if df.empty:
        st.info("No data found.")
    else:
        st.dataframe(df, use_container_width=True)

except Exception as e:
    st.error(f"Failed to load data: {e}")
