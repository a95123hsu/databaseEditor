import streamlit as st
import pandas as pd
from supabase import create_client, Client

# --- Load Supabase credentials from secrets.toml ---
@st.cache_resource(show_spinner=False)
def init_connection():
    try:
        supabase_url = st.secrets["SUPABASE_URL"]
        supabase_key = st.secrets["SUPABASE_KEY"]
        return create_client(supabase_url, supabase_key)
    except KeyError as e:
        st.error(f"Missing required secret: {e}")
        st.stop()
    except Exception as e:
        st.error(f"Failed to initialize Supabase connection: {e}")
        st.stop()

# --- Page Configuration ---
st.set_page_config(
    page_title="Pump Selection Data", 
    page_icon="💧", 
    layout="wide"
)

# --- App Header ---
st.title("💧 Pump Selection Data Viewer")

# --- Initialize Supabase Client ---
supabase = init_connection()

# --- Main Content ---
try:
    # Fetch data
    with st.spinner("Loading pump data..."):
        response = supabase.table("pump_selection_data").select("*").limit(2000).execute()
        df = pd.DataFrame(response.data)
    
    if df.empty:
        st.info("No data found in 'pump_selection_data'.")
    else:
        # Display data info
        st.subheader(f"Found {len(df)} pump records")
        
        # Data Table
        st.subheader("📋 Raw Data Table")
        st.dataframe(df, use_container_width=True)
        
        # Summary View
        st.subheader("🔍 Pump Summary")
        for index, row in df.iterrows():
            name = row.get("name", "Unnamed Pump")
            flow = row.get("flow_rate", "N/A")
            head = row.get("head_height", "N/A")
            with st.expander(f"{name}"):
                st.markdown(f"- **Flow Rate:** {flow} LPM")
                st.markdown(f"- **Head Height:** {head} m")
                # Display additional fields if available
                for col in df.columns:
                    if col not in ["name", "flow_rate", "head_height"] and pd.notna(row.get(col)):
                        st.markdown(f"- **{col.replace('_', ' ').title()}:** {row.get(col)}")
        
except Exception as e:
    st.error(f"Error fetching data: {e}")
    st.info("Please check your connection to Supabase.")
    
# --- Footer ---
st.markdown("---")
st.markdown("💧 **Pump Selection Data Viewer** | Data from Supabase")
