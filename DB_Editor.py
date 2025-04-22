import streamlit as st
import pandas as pd
from supabase import create_client, Client
import re
import traceback
from login import login_form, get_user_session, logout
import bcrypt
import uuid
import os
import json
from datetime import datetime, timedelta
import pytz  # Added for timezone support

# --- Define Taiwan timezone ---
taiwan_tz = pytz.timezone('Asia/Taipei')

# --- Page Configuration ---
st.set_page_config(
    page_title="Pump Selection Data Manager", 
    page_icon="💧", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Check login session
user = get_user_session()
if not user:
    login_form()
    st.stop()

# Optional: Add logout button to sidebar
with st.sidebar:
    if st.button("🚪 Logout"):
        logout()

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

# --- Audit Trail/Version Control Functions ---
def log_database_change(table_name, record_id, operation, old_data=None, new_data=None, description=None):
    """
    Log changes to the database into an audit trail table
    
    Parameters:
    - table_name: The name of the table being modified
    - record_id: The DB ID of the record being modified
    - operation: String - "INSERT", "UPDATE", or "DELETE"
    - old_data: JSON object representing the previous state (for updates/deletes)
    - new_data: JSON object representing the new state (for inserts/updates)
    - description: Optional description of the change
    """
    try:
        # Get the current user from session
        user = get_user_session()
        
        # Extract user info - handle different user object structures
        if user:
            # Try to get user email with different approaches based on the object structure
            if isinstance(user, dict):
                # If user is a dictionary
                user_email = user.get('email', user.get('username', 'unknown'))
            elif hasattr(user, 'email'):
                # If user has email attribute
                user_email = user.email
            elif hasattr(user, 'username'):
                # If user has username attribute
                user_email = user.username
            else:
                # Use string representation as fallback
                user_email = str(user)
        else:
            user_email = 'anonymous'
        
        # Convert numpy data types to Python native types to make them JSON serializable
        def convert_to_serializable(obj):
            if obj is None:
                return None
                
            if isinstance(obj, dict):
                return {k: convert_to_serializable(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_to_serializable(item) for item in obj]
            # Handle numpy data types
            elif hasattr(obj, 'dtype') and hasattr(obj, 'item'):
                return obj.item()  # Convert numpy types to native Python types
            elif pd.isna(obj):
                return None
            
            # Try to convert to native Python types for any other object
            try:
                return float(obj) if isinstance(obj, float) else int(obj) if isinstance(obj, int) else str(obj)
            except (ValueError, TypeError):
                return str(obj)
        
        # Convert the data to JSON serializable format
        clean_old_data = convert_to_serializable(old_data) if old_data else None
        clean_new_data = convert_to_serializable(new_data) if new_data else None
        
        # Convert record_id to int if it's a numpy type
        if hasattr(record_id, 'dtype') and hasattr(record_id, 'item'):
            record_id = record_id.item()
        
        # Prepare the audit record - using Taiwan time
        audit_record = {
            "id": str(uuid.uuid4()),
            "table_name": table_name,
            "record_id": record_id,
            "operation": operation,
            "old_data": json.dumps(clean_old_data) if clean_old_data else None,
            "new_data": json.dumps(clean_new_data) if clean_new_data else None,
            "modified_by": user_email,
            "modified_at": datetime.now(taiwan_tz).isoformat(),  # Using Taiwan timezone
            "description": description
        }
        
        # Insert into audit_trail table
        response = supabase.table("audit_trail").insert(audit_record).execute()
        
        # Log success for debugging
        print(f"Audit trail entry created for {operation} on {table_name} (ID: {record_id})")
        return True
    except Exception as e:
        st.error(f"Failed to create audit trail entry: {e}")
        st.error(traceback.format_exc())
        return False

# --- Realtime Updates Component ---
def setup_realtime_updates():
    """Set up a live feed of database changes using Supabase realtime"""
    
    # Create a container for the live updates
    live_container = st.empty()
    
    # Initialize session state for tracking changes
    if 'last_changes' not in st.session_state:
        st.session_state.last_changes = []
    if 'last_check' not in st.session_state:
        st.session_state.last_check = datetime.now(taiwan_tz)  # Using Taiwan timezone
    
    # Function to fetch recent changes
    def fetch_recent_changes():
        try:
            # Get changes since last check
            response = supabase.table("audit_trail") \
                .select("*") \
                .gte("modified_at", st.session_state.last_check.isoformat()) \
                .order("modified_at", desc=True) \
                .limit(10) \
                .execute()
            
            # Update last check time with Taiwan timezone
            st.session_state.last_check = datetime.now(taiwan_tz)
            
            if response.data:
                # Add new changes to the session state
                new_changes = response.data
                st.session_state.last_changes = new_changes + st.session_state.last_changes
                # Keep only the 20 most recent changes
                st.session_state.last_changes = st.session_state.last_changes[:20]
                
                # Return true if we found new changes
                return True
            return False
        except Exception as e:
            st.error(f"Error fetching realtime updates: {e}")
            return False
    
    # Function to display the changes
    def display_changes():
        with live_container.container():
            st.subheader("📡 Live Database Activity")
            
            if not st.session_state.last_changes:
                st.info("No recent database activity. Changes will appear here in real-time.")
                return
            
            for change in st.session_state.last_changes:
                # Create a clean timestamp in Taiwan time
                try:
                    # Parse the timestamp and convert to Taiwan time
                    dt = pd.to_datetime(change['modified_at'])
                    if dt.tz is None:
                        dt = dt.tz_localize('UTC')
                    timestamp = dt.tz_convert('Asia/Taipei').strftime('%H:%M:%S')
                except:
                    timestamp = "Unknown time"
                
                # Determine the icon based on operation type
                if change['operation'] == 'INSERT':
                    icon = "✅"
                elif change['operation'] == 'UPDATE':
                    icon = "🔄"
                elif change['operation'] == 'DELETE':
                    icon = "🗑️"
                else:
                    icon = "ℹ️"
                
                # Display the change
                with st.container():
                    cols = st.columns([1, 3, 2])
                    with cols[0]:
                        st.write(f"{icon} {timestamp}")
                    with cols[1]:
                        st.write(f"{change['operation']} on {change['table_name']} (ID: {change['record_id']})")
                    with cols[2]:
                        st.write(f"By: {change['modified_by']}")
                
                # Add a small divider
                st.markdown("---")
    
    # Set up auto-refresh in the sidebar
    with st.sidebar:
        st.subheader("Realtime Updates")
        auto_refresh = st.checkbox("Enable auto-refresh", value=True)
        refresh_interval = st.slider("Refresh interval (seconds)", 5, 60, 15)
        
        if st.button("Manual Refresh"):
            fetch_recent_changes()
            display_changes()
    
    # Start with initial display
    display_changes()
    
    # Store functions in session state for later use
    st.session_state.fetch_changes = fetch_recent_changes
    st.session_state.show_changes = display_changes
    
    # Return functions for auto-refresh logic elsewhere in the app
    return fetch_recent_changes, display_changes

# --- Fetch data with proper pagination to get all records ---
def fetch_all_pump_data():
    all_data = []
    page_size = 1000  # Supabase typically has a limit of 1000 rows per request
    
    # Get total count first
    count_response = supabase.table("pump_selection_data").select("count", count="exact").execute()
    total_count = count_response.count if hasattr(count_response, 'count') else 0
    
    if total_count == 0:
        return pd.DataFrame()
    
    # Show progress
    progress_text = "Fetching data..."
    progress_bar = st.progress(0, text=progress_text)
    
    # Fetch in batches with sorting by DB ID
    for start_idx in range(0, total_count, page_size):
        with st.spinner(f"Loading records {start_idx+1}-{min(start_idx+page_size, total_count)}..."):
            # Order by DB ID to ensure consistent sorting
            response = supabase.table("pump_selection_data").select("*").order('"DB ID"').range(start_idx, start_idx + page_size - 1).execute()
            
            if response.data:
                all_data.extend(response.data)
            
            # Update progress
            progress = min((start_idx + page_size) / total_count, 1.0)
            progress_bar.progress(progress, text=f"{progress_text} ({len(all_data)}/{total_count})")
    
    # Clear progress bar when done
    progress_bar.empty()
    
    return pd.DataFrame(all_data)

# --- Apply filters to the dataframe ---
def apply_filters(df, selected_group, selected_category):
    filtered_df = df.copy()
    
    # Apply Model Group filter
    if selected_group != "All":
        filtered_df = filtered_df[filtered_df['Model Group'] == selected_group]
    
    # Apply Category filter if it exists
    if "Category" in df.columns and selected_category != "All":
        # Use exact case-insensitive matching
        filtered_df = filtered_df[filtered_df["Category"].str.lower() == selected_category.lower()]
    
    return filtered_df

# --- Model Categorization Function ---
def extract_model_group(model):
    if pd.isna(model):
        return "Other"
    model = str(model).strip().upper()
    match = re.search(r'\d+([A-Z]+)\d+', model)
    if match:
        return match.group(1)
    if 'ADL' in model:
        return 'ADL'
    match = re.match(r'([A-Z]+)', model)
    return match.group(1) if match else 'Other'

def insert_pump_data(pump_data, description=None):
    try:
        # Create a copy of the data for safe modification
        clean_data = {}
        
        # First, get the maximum DB ID to generate a new one
        try:
            # Use double quotes around column name with space
            max_id_response = supabase.table("pump_selection_data").select('"DB ID"').order('"DB ID"', desc=True).limit(1).execute()
            if max_id_response.data:
                max_id = max_id_response.data[0]["DB ID"]
                new_id = max_id + 1
            else:
                new_id = 1  # Start from 1 if no records exist
            
            # Add the new ID to the data
            clean_data["DB ID"] = new_id
        except Exception as id_error:
            st.error(f"Error generating DB ID: {id_error}")
            st.error(traceback.format_exc())
            return False, "Could not generate a new DB ID. Please check database permissions."
        
        # Convert and clean each field individually
        for key, value in pump_data.items():
            # Skip empty values for optional fields
            if value == "" or pd.isna(value):
                clean_data[key] = None
                continue
                
            # Fields that should be integers in the database
            if key in ["Frequency (Hz)", "Phase", "Outlet (mm)", "Pass Solid Dia(mm)"]:
                try:
                    # Force integer conversion (truncate decimal)
                    if isinstance(value, float):
                        value = int(value)
                    elif isinstance(value, str):
                        # Remove any decimal part
                        value = int(float(value))
                    clean_data[key] = value
                except ValueError:
                    st.error(f"Cannot convert '{key}: {value}' to integer. Skipping this field.")
                    # Skip this field to avoid errors
                    continue
            
            # For fields that are floats
            elif key in ["Max Head (M)"]:
                try:
                    clean_data[key] = float(value)
                except ValueError:
                    st.error(f"Cannot convert '{key}: {value}' to float. Skipping this field.")
                    # Skip this field to avoid errors
                    continue
                    
            # Everything else is treated as string
            else:
                clean_data[key] = str(value)
        
        # Insert the data
        response = supabase.table("pump_selection_data").insert(clean_data).execute()
        
        # Log the change in the audit trail
        log_database_change(
            table_name="pump_selection_data",
            record_id=new_id,
            operation="INSERT",
            new_data=clean_data,
            description=description or f"Added new pump: {clean_data.get('Model No.', 'Unknown')}"
        )
        
        return True, f"Pump data added successfully with DB ID: {new_id}!"
    except Exception as e:
        st.error(f"Error details for debugging: {str(e)}")
        st.error(traceback.format_exc())
        return False, f"Error adding pump data: {e}"

# Modified update function
def update_pump_data(db_id, pump_data, description=None):
    try:
        # First, fetch the current state of the record
        current_record_response = supabase.table("pump_selection_data").select("*").eq('"DB ID"', db_id).execute()
        
        if not current_record_response.data:
            return False, f"Record with DB ID {db_id} not found."
            
        old_data = current_record_response.data[0]
        
        # Create a copy of the data for safe modification
        clean_data = {}
        
        # Convert and clean each field individually
        for key, value in pump_data.items():
            # Skip DB ID since we don't want to update that
            if key == "DB ID":
                continue
                
            # Handle empty values
            if value == "" or pd.isna(value):
                clean_data[key] = None
            # Try to intelligently convert values based on potential types
            else:
                # Fields that should be integers in the database (based on error)
                if key in ["Frequency (Hz)", "Phase", "Outlet (mm)", "Pass Solid Dia(mm)"]:
                    if isinstance(value, (int, float)) or (isinstance(value, str) and value.replace('.', '', 1).isdigit()):
                        try:
                            # Force integer conversion (truncate decimal)
                            if isinstance(value, float):
                                value = int(value)
                            elif isinstance(value, str):
                                # Remove any decimal part
                                value = int(float(value))
                            clean_data[key] = value
                        except ValueError:
                            st.error(f"Cannot convert '{key}: {value}' to integer. Skipping this field.")
                            # Skip this field to avoid errors
                            continue
                    else:
                        clean_data[key] = None
                
                # For fields that are floats
                elif key in ["Max Head (M)"]:
                    if isinstance(value, (int, float)) or (isinstance(value, str) and value.replace('.', '', 1).isdigit()):
                        try:
                            clean_data[key] = float(value)
                        except ValueError:
                            st.error(f"Cannot convert '{key}: {value}' to float. Skipping this field.")
                            # Skip this field to avoid errors
                            continue
                    else:
                        clean_data[key] = None
                        
                # Everything else is treated as string
                else:
                    clean_data[key] = str(value)
        
        # Remove any problematic fields
        problem_keys = []
        for key, value in list(clean_data.items()):
            single_field = {key: value}
            
            try:
                # Simulate update with just this field
                test_response = supabase.table("pump_selection_data").update(single_field).eq('"DB ID"', db_id).execute()
            except Exception as field_error:
                st.error(f"Field '{key}' failed: {str(field_error)}")
                problem_keys.append(key)
        
        # Remove any problematic fields
        for key in problem_keys:
            if key in clean_data:
                st.warning(f"Removing problematic field '{key}' from update.")
                del clean_data[key]
        
        if not clean_data:
            return False, "No valid fields to update after cleaning data."
        
        # Update with the cleaned data - note the double quotes around DB ID
        response = supabase.table("pump_selection_data").update(clean_data).eq('"DB ID"', db_id).execute()
        
        # Log the change in the audit trail
        log_database_change(
            table_name="pump_selection_data",
            record_id=db_id,
            operation="UPDATE",
            old_data=old_data,
            new_data=clean_data,
            description=description or f"Updated pump: {old_data.get('Model No.', 'Unknown')}"
        )
        
        return True, "Pump data updated successfully!"
    except Exception as e:
        st.error(f"Error details for debugging: {str(e)}")
        st.error(traceback.format_exc())
        return False, f"Error updating pump data: {e}"
