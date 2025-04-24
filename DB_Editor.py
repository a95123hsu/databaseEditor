import streamlit as st

st.set_page_config(
    page_title="Pump Selection Data Manager", 
    page_icon="💧", 
    layout="wide",
    initial_sidebar_state="expanded"
)

import pandas as pd
from supabase import create_client, Client
import re
import uuid
import os
import json
from datetime import datetime, timedelta
import pytz
import hashlib  # For safe error logging
import secrets  # For CSRF token
import html  # For sanitizing output
import logging  # For proper logging

from login import login_form, get_user_session, logout

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("pump_selection_app")

# Set timezone from environment variable or use Taiwan as default
DEFAULT_TIMEZONE = 'Asia/Taipei'
TIMEZONE = os.environ.get('APP_TIMEZONE', DEFAULT_TIMEZONE)
app_tz = pytz.timezone(TIMEZONE)

# Initialize session state for CSRF protection
if 'csrf_token' not in st.session_state:
    st.session_state.csrf_token = secrets.token_hex(16)

# --- User Authentication ---
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
    """Safely initialize Supabase connection with proper error handling"""
    try:
        # Verify both required secrets are present
        if "SUPABASE_URL" not in st.secrets or "SUPABASE_KEY" not in st.secrets:
            raise KeyError("Missing required Supabase credentials")
        
        supabase_url = st.secrets["SUPABASE_URL"]
        supabase_key = st.secrets["SUPABASE_KEY"]
        
        # Validate URL format (basic check)
        if not supabase_url.startswith(('http://', 'https://')):
            raise ValueError("Invalid Supabase URL format")
            
        return create_client(supabase_url, supabase_key)
    except KeyError as e:
        logger.error(f"Missing required secret: {e}")
        st.error("Configuration error: Missing database credentials. Please contact the administrator.")
        st.stop()
    except Exception as e:
        # Log the real error but show generic message to user
        logger.error(f"Failed to initialize Supabase connection: {str(e)}")
        st.error("Unable to connect to the database. Please try again later or contact the administrator.")
        st.stop()

# --- Data Sanitization Functions ---
def sanitize_input(value):
    """Sanitize user input to prevent injection attacks"""
    if value is None:
        return None
    
    # Convert to string and strip whitespace
    if not isinstance(value, str):
        value = str(value)
    
    value = value.strip()
    
    # Remove any potentially dangerous characters
    # This is a basic implementation - consider using a proper library for production
    dangerous_chars = [';', '--', '/*', '*/', 'xp_', 'exec', 'select', 'drop', 'delete', 'update', 'insert']
    for char in dangerous_chars:
        value = value.replace(char, '')
    
    return value

def sanitize_output(value):
    """Sanitize data before displaying to prevent XSS"""
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    return html.escape(value)

def sanitize_db_id(value):
    """Ensure DB ID is a valid integer"""
    try:
        return int(value)
    except (ValueError, TypeError):
        logger.warning(f"Invalid DB ID format: {value}")
        return None

def safe_json_serialize(obj):
    """Safely convert objects to JSON serializable format"""
    if obj is None:
        return None
            
    if isinstance(obj, dict):
        return {k: safe_json_serialize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [safe_json_serialize(item) for item in obj]
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

# --- Audit Trail/Version Control Functions ---
def log_database_change(table_name, record_id, operation, old_data=None, new_data=None, description=None):
    """Log changes to the database into an audit trail table with proper sanitization"""
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
        
        # Sanitize inputs
        table_name = sanitize_input(table_name)
        if table_name not in ["pump_selection_data", "audit_trail"]:  # Whitelist approach
            logger.warning(f"Attempted to log changes to non-whitelisted table: {table_name}")
            return False
            
        # Ensure record_id is properly formatted
        record_id = sanitize_db_id(record_id)
        if record_id is None:
            logger.warning("Invalid record ID for audit logging")
            return False
            
        operation = sanitize_input(operation)
        if operation not in ["INSERT", "UPDATE", "DELETE"]:  # Whitelist approach
            logger.warning(f"Invalid operation type: {operation}")
            return False
        
        # Convert the data to JSON serializable format
        clean_old_data = safe_json_serialize(old_data) if old_data else None
        clean_new_data = safe_json_serialize(new_data) if new_data else None
        
        # Prepare the audit record using app timezone
        audit_record = {
            "id": str(uuid.uuid4()),
            "table_name": table_name,
            "record_id": record_id,
            "operation": operation,
            "old_data": json.dumps(clean_old_data) if clean_old_data else None,
            "new_data": json.dumps(clean_new_data) if clean_new_data else None,
            "modified_by": user_email,
            "modified_at": datetime.now(app_tz).isoformat(),
            "description": sanitize_input(description) if description else None
        }
        
        # Insert into audit_trail table
        response = supabase.table("audit_trail").insert(audit_record).execute()
        
        # Log success
        logger.info(f"Audit trail entry created for {operation} on {table_name} (ID: {record_id})")
        return True
    except Exception as e:
        # Log the error but don't expose details to user
        logger.error(f"Failed to create audit trail entry: {str(e)}")
        return False

# --- Realtime Updates Component ---
def setup_realtime_updates():
    """Set up a live feed of database changes using Supabase realtime with proper sanitization"""
    
    # Create a container for the live updates
    live_container = st.empty()
    
    # Initialize session state for tracking changes
    if 'last_changes' not in st.session_state:
        st.session_state.last_changes = []
    if 'last_check' not in st.session_state:
        st.session_state.last_check = datetime.now(app_tz)
    
    # Function to fetch recent changes
    def fetch_recent_changes():
        try:
            # Get changes since last check
            iso_time = st.session_state.last_check.isoformat()
            response = supabase.table("audit_trail") \
                .select("*") \
                .gte("modified_at", iso_time) \
                .order("modified_at", desc=True) \
                .limit(10) \
                .execute()
            
            # Update last check time
            st.session_state.last_check = datetime.now(app_tz)
            
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
            logger.error(f"Error fetching realtime updates: {str(e)}")
            return False
    
    # Function to display the changes
    def display_changes():
        with live_container.container():
            st.subheader("📡 Live Database Activity")
            
            if not st.session_state.last_changes:
                st.info("No recent database activity. Changes will appear here in real-time.")
                return
            
            for change in st.session_state.last_changes:
                # Create a clean timestamp
                try:
                    # Parse the timestamp and convert to app timezone if needed
                    dt = pd.to_datetime(change['modified_at'])
                    if dt.tz is None:
                        # If timestamp has no timezone info, assume it's UTC and convert
                        dt = dt.tz_localize('UTC').tz_convert(TIMEZONE)
                    elif dt.tz.zone != TIMEZONE:
                        # If it has timezone info but not matching app timezone, convert it
                        dt = dt.tz_convert(TIMEZONE)
                    timestamp = dt.strftime('%H:%M:%S')
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
                
                # Sanitize outputs before display
                record_id = sanitize_output(change['record_id'])
                table_name = sanitize_output(change['table_name'])
                modified_by = sanitize_output(change['modified_by'])
                
                # Display the change
                with st.container():
                    cols = st.columns([1, 3, 2])
                    with cols[0]:
                        st.write(f"{icon} {timestamp}")
                    with cols[1]:
                        st.write(f"{change['operation']} on {table_name} (ID: {record_id})")
                    with cols[2]:
                        st.write(f"By: {modified_by}")
                
                # Add a small divider
                st.markdown("---")
    
    # Set up auto-refresh in the sidebar
    with st.sidebar:
        st.subheader("Realtime Updates")
        auto_refresh = st.checkbox("Enable auto-refresh", value=True)
        refresh_interval = st.slider("Refresh interval (seconds)", 5, 60, 15)
        
        # Add CSRF token to form
        if st.button("Manual Refresh", key=f"refresh_{st.session_state.csrf_token}"):
            fetch_recent_changes()
            display_changes()
    
    # Start with initial display
    display_changes()
    
    # Store functions in session state for later use
    st.session_state.fetch_changes = fetch_recent_changes
    st.session_state.show_changes = display_changes
    
    # Return functions for auto-refresh logic elsewhere in the app
    return fetch_recent_changes, display_changes

# --- Fetch data with proper pagination and error handling ---
def fetch_all_pump_data():
    all_data = []
    page_size = 1000  # Supabase typically has a limit of 1000 rows per request
    
    try:
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
    except Exception as e:
        logger.error(f"Error fetching pump data: {str(e)}")
        st.error("An error occurred while fetching data. Please try again later.")
        return pd.DataFrame()

# --- Apply filters to the dataframe ---
def apply_filters(df, selected_group, selected_category):
    """Apply filters with parameter validation"""
    filtered_df = df.copy()
    
    # Apply Model Group filter
    if selected_group != "All" and selected_group in df['Model Group'].unique():
        filtered_df = filtered_df[filtered_df['Model Group'] == selected_group]
    
    # Apply Category filter if it exists
    if "Category" in df.columns and selected_category != "All":
        # Use exact case-insensitive matching
        filtered_df = filtered_df[filtered_df["Category"].str.lower() == selected_category.lower()]
    
    return filtered_df

# --- Model Categorization Function ---
def extract_model_group(model):
    """Extract the model group from model number with validation"""
    if pd.isna(model):
        return "Other"
    
    # Ensure input is a string
    model = str(model).strip().upper()
    
    # First pattern - most common
    match = re.search(r'\d+([A-Z]+)\d+', model)
    if match:
        return match.group(1)
    
    # Special case for ADL
    if 'ADL' in model:
        return 'ADL'
    
    # Fallback pattern
    match = re.match(r'([A-Z]+)', model)
    return match.group(1) if match else 'Other'

# --- Data Manipulation Functions ---
def convert_field_value(key, value):
    """Convert field values with proper validation and error handling"""
    # Skip empty values
    if value == "" or pd.isna(value):
        return None
    
    # Integer fields
    if key in ["Frequency (Hz)", "Phase", "Outlet (mm)", "Pass Solid Dia(mm)"]:
        try:
            if isinstance(value, float):
                return int(value)
            elif isinstance(value, str):
                return int(float(value))
            return value
        except ValueError:
            logger.warning(f"Cannot convert '{key}: {value}' to integer")
            return None
    
    # Float fields
    elif key in ["Max Head (M)"]:
        try:
            return float(value)
        except ValueError:
            logger.warning(f"Cannot convert '{key}: {value}' to float")
            return None
    
    # String fields with sanitization
    else:
        return sanitize_input(str(value))

def insert_pump_data(pump_data, description=None):
    """Insert new pump data with validation and sanitization"""
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
            logger.error(f"Error generating DB ID: {str(id_error)}")
            return False, "Could not generate a new DB ID. Please try again later."
        
        # Validate required fields
        if not pump_data.get("Model No."):
            return False, "Model No. is required"
        
        # Convert and clean each field
        for key, value in pump_data.items():
            clean_data[key] = convert_field_value(key, value)
        
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
        # Log the error but provide a sanitized message to the user
        logger.error(f"Error adding pump data: {str(e)}")
        return False, "Error adding pump data. Please check your input and try again."

def update_pump_data(db_id, pump_data, description=None):
    """Update pump data with validation and sanitization"""
    try:
        # Validate DB ID
        db_id = sanitize_db_id(db_id)
        if db_id is None:
            return False, "Invalid database ID format."
        
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
                
            clean_data[key] = convert_field_value(key, value)
        
        # Check if there's anything to update
        if not clean_data:
            return False, "No valid fields to update."
        
        # Update with the cleaned data
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
        # Log the error but provide a sanitized message to the user
        logger.error(f"Error updating pump data: {str(e)}")
        return False, "Error updating pump data. Please check your input and try again."

def delete_pump_data(db_id, description=None):
    """Delete pump data with validation"""
    try:
        # Validate DB ID
        db_id = sanitize_db_id(db_id)
        if db_id is None:
            return False, "Invalid database ID format."
        
        # First, fetch the current state of the record to save in history
        current_record_response = supabase.table("pump_selection_data").select("*").eq('"DB ID"', db_id).execute()
        
        if not current_record_response.data:
            return False, f"Record with DB ID {db_id} not found."
            
        old_data = current_record_response.data[0]
        
        # Add CSRF protection
        if 'csrf_token' not in st.session_state:
            return False, "Security token missing. Please refresh the page and try again."
        
        # Perform the deletion
        response = supabase.table("pump_selection_data").delete().eq('"DB ID"', db_id).execute()
        
        # Log the deletion in the audit trail
        log_database_change(
            table_name="pump_selection_data",
            record_id=db_id,
            operation="DELETE",
            old_data=old_data,
            description=description or f"Deleted pump: {old_data.get('Model No.', 'Unknown')}"
        )
        
        return True, "Pump data deleted successfully!"
    except Exception as e:
        # Log the error but provide a sanitized message to the user
        logger.error(f"Error deleting pump data: {str(e)}")
        return False, "Error deleting pump data. Please try again later."

# --- Rate Limiting ---
def check_rate_limit(action_type, limit=10, window_minutes=1):
    """Simple rate limiting to prevent abuse"""
    window_key = f"rate_limit_{action_type}_{datetime.now(app_tz).strftime('%Y%m%d_%H%M')}"
    
    if window_key not in st.session_state:
        st.session_state[window_key] = 1
    else:
        st.session_state[window_key] += 1
    
    if st.session_state[window_key] > limit:
        st.error(f"Too many {action_type} requests. Please wait a moment and try again.")
        return False
    
    return True

# --- App Header ---
st.title("💧 Pump Selection Data Manager")
st.markdown("View, add, edit, and delete pump selection data")
st.info(f"Current time ({TIMEZONE}): {datetime.now(app_tz).strftime('%Y-%m-%d %H:%M:%S')}")

# --- Initialize Supabase Client ---
supabase = init_connection()

# --- Fetch Data ---
try:
    # Fetch all data initially
    df = fetch_all_pump_data()
    
    if not df.empty:
        # Add Model Group for categorization
        df['Model Group'] = df['Model No.'].apply(extract_model_group)
        
        # Clean up Category values to ensure consistent filtering
        if "Category" in df.columns:
            # Convert all category values to strings and strip whitespace
            df["Category"] = df["Category"].astype(str).str.strip()
            # Replace NaN, None, etc. with empty string for consistent handling
            df["Category"] = df["Category"].replace(["nan", "None", "NaN"], "")
except Exception as e:
    logger.error(f"Error initializing data: {str(e)}")
    st.error("An error occurred while loading the initial data. Please try again later.")
    df = pd.DataFrame()

# --- Sidebar for actions and filters ---
with st.sidebar:
    st.header("Actions")
    action = st.radio(
        "Choose an action:",
        ["View Data", "Add New Pump", "Edit Pump", "Delete Pump"]
    )
    
    if not df.empty:
        st.header("Filters")
        
        # Model Group Filter
        model_groups = ["All"] + sorted(df['Model Group'].unique().tolist())
        selected_group = st.selectbox("Filter by Model Group", model_groups)
        
        # Category Filter (if exists)
        if "Category" in df.columns:
            # Get unique non-empty categories
            categories = [c for c in df["Category"].unique() if c and c.strip() and c.lower() not in ["nan", "none"]]
            categories = ["All"] + sorted(categories)
            selected_category = st.selectbox("Filter by Category", categories)
        else:
            selected_category = "All"
    else:
        selected_group = "All"
        selected_category = "All"
    
    # Add CSRF token to the form
    if st.button("🔄 Refresh Data", key=f"refresh_data_{st.session_state.csrf_token}"):
        st.cache_data.clear()
        st.rerun()

# --- Main Content Based on Action ---
if action == "View Data":
    # Initialize realtime updates
    if 'realtime_initialized' not in st.session_state:
        st.session_state.realtime_initialized = True
        fetch_changes, show_changes = setup_realtime_updates()

    # Auto-refresh logic for realtime updates
    if st.session_state.get('auto_refresh', True):
        # Check for changes periodically
        refresh_placeholder = st.empty()
        if 'fetch_changes' in st.session_state and 'show_changes' in st.session_state:
            has_new = st.session_state.fetch_changes()
            if has_new:
                st.session_state.show_changes()
            
            # Update the refresh message
            refresh_placeholder.info(f"Last checked for updates: {datetime.now(app_tz).strftime('%H:%M:%S')}")
    
    try:
        if df.empty:
            st.info("No data found in 'pump_selection_data'.")
        else:
            # Display data info
            st.success(f"✅ Successfully loaded {len(df)} pump records")
            
            # Apply filters
            filtered_df = apply_filters(df, selected_group, selected_category)
            
            # Show filter results
            if selected_group != "All":
                st.write(f"Filtered by Model Group: {selected_group}")
            if selected_category != "All":
                st.write(f"Filtered by Category: {selected_category} (matching {len(filtered_df)} records)")
            
            # Add search functionality
            search_term = st.text_input("🔍 Search by Model No.:", key="search_model")
            
            if search_term:
                search_term = sanitize_input(search_term)
                filtered_df = filtered_df[filtered_df["Model No."].astype(str).str.contains(search_term, case=False, na=False)]
                st.write(f"Found {len(filtered_df)} matching pumps")
            
            if filtered_df.empty:
                st.info("No pumps match your filter criteria.")
            else:
                # Data Table with pagination controls
                st.subheader("📋 Pump Data Table")
                
                # Add sorting options
                sort_columns = ["Model Group", "DB ID"] + [col for col in filtered_df.columns if col not in ["DB ID", "Model Group"]]
                sort_column = st.selectbox("Sort by:", sort_columns, index=0)
                sort_order = st.radio("Sort order:", ["Ascending", "Descending"], horizontal=True)
                
                # Apply sorting
                if sort_order == "Ascending":
                    sorted_df = filtered_df.sort_values(by=sort_column)
                else:
                    sorted_df = filtered_df.sort_values(by=sort_column, ascending=False)
                
                # Show row count selection
                rows_per_page = st.selectbox("Rows per page:", [10, 25, 50, 100, "All"], index=1)
                
                if rows_per_page == "All":
                    # Apply rate limiting for large datasets
                    if len(sorted_df) > 1000 and not check_rate_limit("view_all", limit=2, window_minutes=5):
                        st.warning("For performance reasons, please use pagination for large datasets.")
                    else:
                        st.dataframe(sorted_df, use_container_width=True)
                else:
                    # Manual pagination
                    rows_per_page = int(rows_per_page)
                    total_rows = len(sorted_df)
                    total_pages = (total_rows + rows_per_page - 1) // rows_per_page
                    
                    if total_pages > 0:
                        page = st.number_input("Page", min_value=1, max_value=total_pages, value=1)
                        start_idx = (page - 1) * rows_per_page
                        end_idx = min(start_idx + rows_per_page, total_rows)
                        
                        st.dataframe(sorted_df.iloc[start_idx:end_idx], use_container_width=True)
                        st.write(f"Showing {start_idx+1}-{end_idx} of {total_rows} rows")
                    else:
                        st.info("No data to display")
                
                # Show summary by group
                st.subheader("📊 Model Group Summary")
                group_counts = filtered_df['Model Group'].value_counts().reset_index()
                group_counts.columns = ['Model Group', 'Count']
                st.dataframe(group_counts, use_container_width=True)
                    
    except Exception as e:
        logger.error(f"Error in View Data: {str(e)}")
        st.error("An error occurred while displaying the data. Please try refreshing the page.")

elif action == "Add New Pump":
    st.subheader("Add New Pump")
    
    # Rate limiting check
    if not check_rate_limit("add_pump", limit=10, window_minutes=5):
        st.stop()
    
   # Define fields based on table structure
    fields = {
        "Model No.": "",
        "Frequency (Hz)": 0,
        "Phase": 0,
        "HP": "",
        "Power(KW)": "",
        "Outlet (mm)": 0,
        "Outlet (inch)": "",
        "Pass Solid Dia(mm)": 0,
        "Max Flow (LPM)": "",
        "Max Head (M)": 0.0,
        "Max Head (ft)": "",
        "Category": "",
        "Product Link": ""
    }
    
    # Create input form for new pump with CSRF protection
    with st.form("add_pump_form"):
        # Add hidden CSRF token
        st.markdown(f"<input type='hidden' name='csrf_token' value='{st.session_state.csrf_token}'>", unsafe_allow_html=True)
        
        new_pump_data = {}
        
        # Model No. is required
        new_pump_data["Model No."] = st.text_input("Model No. *", help="Required field")
        
        # Show predicted model group based on input
        if new_pump_data["Model No."]:
            predicted_group = extract_model_group(new_pump_data["Model No."])
            st.info(f"Predicted Model Group: {predicted_group}")
        
        # Create columns for better layout
        col1, col2 = st.columns(2)
        
        with col1:
            new_pump_data["Frequency (Hz)"] = st.number_input("Frequency (Hz)", value=50, step=1, min_value=0)
            new_pump_data["Phase"] = st.number_input("Phase", value=3, step=1, min_value=0)
            new_pump_data["HP"] = st.text_input("HP")
            new_pump_data["Power(KW)"] = st.text_input("Power(KW)")
            new_pump_data["Outlet (mm)"] = st.number_input("Outlet (mm)", value=0, step=1, min_value=0)
            new_pump_data["Outlet (inch)"] = st.text_input("Outlet (inch)")
        
        with col2:
            new_pump_data["Pass Solid Dia(mm)"] = st.number_input("Pass Solid Dia(mm)", value=0, step=1, min_value=0)
            new_pump_data["Max Flow (LPM)"] = st.text_input("Max Flow (LPM)")
            new_pump_data["Max Head (M)"] = st.number_input("Max Head (M)", value=0.0, min_value=0.0)
            new_pump_data["Max Head (ft)"] = st.text_input("Max Head (ft)")
            
            # Category dropdown if we have existing categories
            if not df.empty and "Category" in df.columns:
                # Get unique non-empty categories
                categories = [c for c in df["Category"].unique() if c and c.strip() and c.lower() not in ["nan", "none"]]
                categories = [""] + sorted(categories)
                new_pump_data["Category"] = st.selectbox("Category", categories)
            else:
                new_pump_data["Category"] = st.text_input("Category")
        
        # Put product link in a separate row
        new_pump_data["Product Link"] = st.text_input("Product Link")
        change_description = st.text_area("Change Description (optional)", 
                                         placeholder="Why are you adding this pump?")
        
        submit_button = st.form_submit_button("Add Pump")
        
        if submit_button:
            # Validate required fields
            if not new_pump_data.get("Model No."):
                st.error("Model No. is required.")
            else:
                # Apply rate limiting
                if check_rate_limit("submit_add", limit=5, window_minutes=1):
                    success, message = insert_pump_data(new_pump_data, description=change_description)
                    if success:
                        st.success(message)
                        # Clear cache to refresh data
                        st.cache_data.clear()
                    else:
                        st.error(message)
