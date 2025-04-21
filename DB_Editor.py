import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client, Client
import logging

# --- Configure logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# --- Fetch data with caching ---
@st.cache_data(ttl=300)  # Cache data for 5 minutes
def fetch_pump_data(max_rows=2000):
    try:
        response = supabase.table("pump_selection_data").select("*").limit(max_rows).execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        logger.error(f"Error fetching data: {e}")
        raise Exception(f"Could not fetch data from Supabase: {e}")

# --- Page Configuration ---
st.set_page_config(
    page_title="Pump Selection Data", 
    page_icon="💧", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- App Header ---
st.title("💧 Pump Selection Data Viewer")
st.markdown("Interactive dashboard for pump selection data analysis")

# --- Initialize Supabase Client ---
supabase = init_connection()

# --- Sidebar Controls ---
with st.sidebar:
    st.header("📊 Data Controls")
    
    # Row limit slider
    max_rows = st.slider("Max rows to load", min_value=100, max_value=5000, value=2000, step=100)
    
    # Refresh data button
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.success("Data cache cleared!")

# --- Main Content ---
try:
    # Loading spinner
    with st.spinner("Loading pump data..."):
        df = fetch_pump_data(max_rows)
    
    # Display data info
    st.subheader("📋 Dataset Information")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="Total Pumps", value=len(df))
    with col2:
        st.metric(label="Unique Manufacturers", value=df["manufacturer"].nunique() if "manufacturer" in df.columns else "N/A")
    with col3:
        st.metric(label="Average Flow Rate", 
                 value=f"{df['flow_rate'].mean():.2f} LPM" if "flow_rate" in df.columns else "N/A")
    
    # Data Explorer Tabs
    tab1, tab2, tab3 = st.tabs(["Data Table", "Visualization", "Summary"])
    
    # Tab 1: Raw Data
    with tab1:
        # Search filter
        if not df.empty:
            search_term = st.text_input("Search pumps by name:")
            if search_term:
                filtered_df = df[df["name"].str.contains(search_term, case=False, na=False)]
            else:
                filtered_df = df
                
            # Column selection
            all_columns = df.columns.tolist()
            selected_columns = st.multiselect("Select columns to display:", all_columns, default=all_columns[:6])
            
            if not filtered_df.empty and selected_columns:
                st.dataframe(filtered_df[selected_columns], use_container_width=True)
            else:
                st.info("No matching data to display.")
        else:
            st.info("No data found in 'pump_selection_data'.")
    
    # Tab 2: Data Visualization
    with tab2:
        if not df.empty and "flow_rate" in df.columns and "head_height" in df.columns:
            st.subheader("🔍 Pump Performance Visualization")
            
            # Scatter plot
            fig = px.scatter(
                df, 
                x="flow_rate", 
                y="head_height",
                hover_name="name",
                color="manufacturer" if "manufacturer" in df.columns else None,
                size="power" if "power" in df.columns else None,
                title="Pump Performance Curve: Flow Rate vs Head Height",
                labels={"flow_rate": "Flow Rate (LPM)", "head_height": "Head Height (m)"}
            )
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Visualization requires flow_rate and head_height data.")
    
    # Tab 3: Summary View
    with tab3:
        st.subheader("🔍 Pump Summary")
        
        if not df.empty:
            # Group by manufacturer if available
            if "manufacturer" in df.columns:
                manufacturers = sorted(df["manufacturer"].dropna().unique())
                selected_manufacturer = st.selectbox("Filter by manufacturer:", ["All"] + list(manufacturers))
                
                if selected_manufacturer != "All":
                    summary_df = df[df["manufacturer"] == selected_manufacturer]
                else:
                    summary_df = df
            else:
                summary_df = df
            
            # Display summary cards
            for index, row in summary_df.iterrows():
                with st.expander(f"{row.get('name', 'Unnamed Pump')}"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**Flow Rate:** {row.get('flow_rate', 'N/A')} LPM")
                        st.markdown(f"**Head Height:** {row.get('head_height', 'N/A')} m")
                        if "power" in df.columns:
                            st.markdown(f"**Power:** {row.get('power', 'N/A')} kW")
                    with col2:
                        if "manufacturer" in df.columns:
                            st.markdown(f"**Manufacturer:** {row.get('manufacturer', 'N/A')}")
                        if "efficiency" in df.columns:
                            st.markdown(f"**Efficiency:** {row.get('efficiency', 'N/A')}%")
                        if "price" in df.columns:
                            st.markdown(f"**Price:** ${row.get('price', 'N/A')}")
        else:
            st.info("No data available for summary view.")

except Exception as e:
    st.error(f"Error: {e}")
    st.info("Try refreshing the data or check your connection to Supabase.")
    
# --- Footer ---
st.markdown("---")
st.markdown("💧 **Pump Selection Data Viewer** | Data from Supabase")
