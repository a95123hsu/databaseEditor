import streamlit as st
import pandas as pd
from supabase import create_client
import json
from datetime import datetime, timedelta
import traceback
from login import get_user_session
import pytz  # Added for timezone support

# --- Define Taiwan timezone ---
taiwan_tz = pytz.timezone('Asia/Taipei')

# --- Page Configuration ---
st.set_page_config(
    page_title="Database History Viewer", 
    page_icon="📜", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Check login session
user = get_user_session()
if not user:
    st.warning("Please log in to access this page.")
    st.stop()

# Initialize Supabase Client
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

supabase = init_connection()

# --- Header ---
st.title("📜 Database History Viewer")
st.markdown("Track all changes made to the pump selection database")

# --- Fetch Audit Trail Data ---
def fetch_audit_data(table_filter=None, date_range=None, user_filter=None):
    try:
        # Start with the base query
        query = supabase.table("audit_trail").select("*")
        
        # Apply table filter
        if table_filter and table_filter != "All Tables":
            query = query.eq("table_name", table_filter)
        
        # Apply date range filter
        if date_range:
            start_date, end_date = date_range
            # Convert end_date to end of day
            end_date = end_date + timedelta(days=1)
            query = query.gte("modified_at", start_date.isoformat()).lt("modified_at", end_date.isoformat())
        
        # Apply user filter
        if user_filter and user_filter != "All Users":
            query = query.eq("modified_by", user_filter)
        
        # Order by most recent first
        query = query.order("modified_at", desc=True)
        
        # Execute and return
        response = query.execute()
        
        if response.data:
            return pd.DataFrame(response.data)
        else:
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Error fetching audit data: {e}")
        st.error(traceback.format_exc())
        return pd.DataFrame()

# --- Get List of Tables and Users ---
def get_table_names():
    try:
        response = supabase.table("audit_trail").select("table_name").execute()
        if response.data:
            tables = sorted(list(set([r["table_name"] for r in response.data if r["table_name"]])))
            return ["All Tables"] + tables
        return ["All Tables"]
    except:
        return ["All Tables"]

def get_user_list():
    try:
        response = supabase.table("audit_trail").select("modified_by").execute()
        if response.data:
            users = sorted(list(set([r["modified_by"] for r in response.data if r["modified_by"]])))
            return ["All Users"] + users
        return ["All Users"]
    except:
        return ["All Users"]

# --- Format Data for Display ---
def format_audit_table(df):
    # Convert timestamps to readable format in Taiwan time
    if 'modified_at' in df.columns:
        # Parse ISO timestamps, assuming they're in UTC, and convert to Taiwan time
        df['modified_at'] = pd.to_datetime(df['modified_at'], format='ISO8601')
        # If timestamps don't have timezone info, localize them to UTC first
        if df['modified_at'].dt.tz is None:
            df['modified_at'] = df['modified_at'].dt.tz_localize('UTC')
        # Convert to Taiwan time and format
        df['modified_at'] = df['modified_at'].dt.tz_convert('Asia/Taipei').dt.strftime('%Y-%m-%d %H:%M:%S')
    
    # Display the table
    return df[['operation', 'table_name', 'record_id', 'modified_by', 'modified_at', 'description']]

# --- Display JSON Diff ---
def display_json_diff(old_data, new_data):
    if not old_data and not new_data:
        st.info("No data comparison available.")
        return
    
    # Parse JSON data
    old_dict = json.loads(old_data) if old_data else {}
    new_dict = json.loads(new_data) if new_data else {}
    
    # Get all keys from both dictionaries
    all_keys = sorted(set(list(old_dict.keys()) + list(new_dict.keys())))
    
    # Create columns for comparison
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Old Values")
        for key in all_keys:
            old_value = old_dict.get(key, "N/A")
            if key in old_dict and key in new_dict and old_dict[key] != new_dict[key]:
                # Highlight changed values
                st.markdown(f"**{key}**: <span style='color:red'>{old_value}</span>", unsafe_allow_html=True)
            else:
                st.write(f"**{key}**: {old_value}")
    
    with col2:
        st.subheader("New Values")
        for key in all_keys:
            new_value = new_dict.get(key, "N/A")
            if key in old_dict and key in new_dict and old_dict[key] != new_dict[key]:
                # Highlight changed values
                st.markdown(f"**{key}**: <span style='color:green'>{new_value}</span>", unsafe_allow_html=True)
            else:
                st.write(f"**{key}**: {new_value}")

# --- Main Page Layout ---
# Sidebar filters
with st.sidebar:
    st.header("Filters")
    
    # Date range filter - Modified to use Taiwan time
    st.subheader("Date Range")
    end_date = datetime.now(taiwan_tz).date()
    start_date = end_date - timedelta(days=30)
    date_range = st.date_input(
        "Select date range",
        value=(start_date, end_date),
        min_value=start_date - timedelta(days=365),
        max_value=end_date
    )
    
    # Table filter
    table_options = get_table_names()
    table_filter = st.selectbox("Table", table_options)
    
    # User filter
    user_options = get_user_list()
    user_filter = st.selectbox("Modified By", user_options)
    
    # Operation filter
    operation_filter = st.multiselect(
        "Operation Type",
        ["INSERT", "UPDATE", "DELETE"],
        default=["INSERT", "UPDATE", "DELETE"]
    )
    
    # Apply filters button
    filter_button = st.button("Apply Filters")
    
    if st.button("Clear Filters"):
        st.rerun()
    
    if st.button("Refresh Data"):
        st.cache_data.clear()
        st.rerun()

# Main content - History table
try:
    # Fetch audit data with filters
    df = fetch_audit_data(table_filter, date_range, user_filter)
    
    if df.empty:
        st.info("No history records found matching your criteria.")
    else:
        # Apply operation type filter if selected
        if operation_filter and len(operation_filter) < 3:  # If not all operations are selected
            df = df[df['operation'].isin(operation_filter)]
        
        # Display record count
        st.success(f"Found {len(df)} history records")
        
        # Format and display the table
        display_df = format_audit_table(df)
        st.dataframe(display_df, use_container_width=True)
        
        # Create expanders for each row's details
        st.subheader("Record Details")
        st.info("Select a record to view detailed changes")
        
        selected_idx = st.selectbox(
            "Select record", 
            range(len(df)), 
            format_func=lambda i: f"{df.iloc[i]['operation']} - {df.iloc[i]['table_name']} (ID: {df.iloc[i]['record_id']}) - {pd.to_datetime(df.iloc[i]['modified_at'], format='ISO8601').tz_localize('UTC').tz_convert('Asia/Taipei').strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        if selected_idx is not None:
            selected_row = df.iloc[selected_idx]
            
            # Display details of selected change
            st.write(f"**Operation:** {selected_row['operation']}")
            st.write(f"**Table:** {selected_row['table_name']}")
            st.write(f"**Record ID:** {selected_row['record_id']}")
            st.write(f"**Modified By:** {selected_row['modified_by']}")
            
            # Convert timestamp to Taiwan time
            modified_at = pd.to_datetime(selected_row['modified_at'], format='ISO8601')
            if isinstance(modified_at, pd.Timestamp) and modified_at.tz is None:
                modified_at = modified_at.tz_localize('UTC').tz_convert('Asia/Taipei')
            elif isinstance(modified_at, str):
                # If it's already been formatted as a string (from display_df)
                st.write(f"**Modified At:** {modified_at}")
            else:
                st.write(f"**Modified At:** {modified_at.strftime('%Y-%m-%d %H:%M:%S')}")
                
            st.write(f"**Description:** {selected_row['description']}")
            
            # Display data changes
            st.subheader("Data Changes")
            display_json_diff(selected_row['old_data'], selected_row['new_data'])

except Exception as e:
    st.error(f"Error: {e}")
    st.error(traceback.format_exc())

# --- Footer ---
st.markdown("---")
st.markdown("📜 **Database History Viewer** | Last updated: " + datetime.now(taiwan_tz).strftime("%Y-%m-%d %H:%M:%S"))
