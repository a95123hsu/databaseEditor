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
import traceback
import bcrypt
import uuid
import os
import json
from datetime import datetime, timedelta
import pytz  # Added for timezone support

from login import login_form, get_user_session, logout
from language import setup_language_selector, get_text, load_translations

taiwan_tz = pytz.timezone('Asia/Taipei')

# --- Set up language selector ---
if 'translations' not in st.session_state:
    st.session_state.translations = load_translations()

# Set up the language selector in the sidebar
active_lang = setup_language_selector()

# Check login session
user = get_user_session()
if not user:
    login_form()
    st.stop()

# Optional: Add logout button to sidebar
with st.sidebar:
    if st.button(f"🚪 {get_text('logout')}"):
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
        
        # Prepare the audit record using Taiwan timezone
        audit_record = {
            "id": str(uuid.uuid4()),
            "table_name": table_name,
            "record_id": record_id,
            "operation": operation,
            "old_data": json.dumps(clean_old_data) if clean_old_data else None,
            "new_data": json.dumps(clean_new_data) if clean_new_data else None,
            "modified_by": user_email,
            "modified_at": datetime.now(taiwan_tz).isoformat(),  # Use Taiwan timezone
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
        st.session_state.last_check = datetime.now(taiwan_tz)  # Use Taiwan timezone
    
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
            
            # Update last check time using Taiwan timezone
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
            st.subheader(get_text("live_database_activity"))
            
            if not st.session_state.last_changes:
                st.info(get_text("no_recent_activity"))
                return
            
            for change in st.session_state.last_changes:
                # Create a clean timestamp with Taiwan time
                try:
                    # Parse the timestamp and convert to Taiwan time if needed
                    dt = pd.to_datetime(change['modified_at'])
                    if dt.tz is None:
                        # If timestamp has no timezone info, assume it's UTC and convert to Taiwan
                        dt = dt.tz_localize('UTC').tz_convert('Asia/Taipei')
                    elif dt.tz.zone != 'Asia/Taipei':
                        # If it has timezone info but not Taiwan, convert it
                        dt = dt.tz_convert('Asia/Taipei')
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
                
                # Display the change
                with st.container():
                    cols = st.columns([1, 3, 2])
                    with cols[0]:
                        st.write(f"{icon} {timestamp}")
                    with cols[1]:
                        st.write(f"{change['operation']} on {change['table_name']} (ID: {change['record_id']})")
                    with cols[2]:
                        st.write(f"{get_text('by')}: {change['modified_by']}")
                
                # Add a small divider
                st.markdown("---")
    
    # Set up auto-refresh in the sidebar
    with st.sidebar:
        st.subheader(get_text("realtime_updates"))
        auto_refresh = st.checkbox(get_text("enable_auto_refresh"), value=True)
        refresh_interval = st.slider(get_text("refresh_interval"), 5, 60, 15)
        
        if st.button(get_text("manual_refresh")):
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
            return False, get_text("could_not_generate_db_id")
        
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
        
        return True, get_text("pump_data_added", new_id)
    except Exception as e:
        st.error(f"Error details for debugging: {str(e)}")
        st.error(traceback.format_exc())
        return False, get_text("error_adding_pump", e)

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
        
        return True, get_text("pump_data_updated")
    except Exception as e:
        st.error(f"Error details for debugging: {str(e)}")
        st.error(traceback.format_exc())
        return False, get_text("error_updating_pump", e)

# Modified delete function
def delete_pump_data(db_id, description=None):
    try:
        # First, fetch the current state of the record to save in history
        current_record_response = supabase.table("pump_selection_data").select("*").eq('"DB ID"', db_id).execute()
        
        if not current_record_response.data:
            return False, f"Record with DB ID {db_id} not found."
            
        old_data = current_record_response.data[0]
        
        # Note the double quotes around DB ID
        response = supabase.table("pump_selection_data").delete().eq('"DB ID"', db_id).execute()
        
        # Log the deletion in the audit trail
        log_database_change(
            table_name="pump_selection_data",
            record_id=db_id,
            operation="DELETE",
            old_data=old_data,
            description=description or f"Deleted pump: {old_data.get('Model No.', 'Unknown')}"
        )
        
        return True, get_text("pump_data_deleted")
    except Exception as e:
        st.error(f"Error details for debugging: {str(e)}")
        st.error(traceback.format_exc())
        return False, get_text("error_deleting_pump", e)

# New function for bulk delete
def bulk_delete_pumps(db_ids, description=None):
    """
    Delete multiple pump records at once
    
    Parameters:
    - db_ids: List of DB IDs to delete
    - description: Optional description of the bulk delete operation
    
    Returns:
    - success: Boolean indicating if all deletions were successful
    - message: Status message
    - success_count: Number of successfully deleted records
    - error_count: Number of failed deletions
    """
    success_count = 0
    error_count = 0
    error_messages = []
    
    # Create a progress bar
    progress_text = get_text("deleting_records")
    progress_bar = st.progress(0, text=progress_text)
    
    # Process each ID
    for idx, db_id in enumerate(db_ids):
        try:
            # Fetch the current record for audit trail
            current_record_response = supabase.table("pump_selection_data").select("*").eq('"DB ID"', db_id).execute()
            
            if not current_record_response.data:
                error_count += 1
                error_messages.append(f"Record with DB ID {db_id} not found.")
                continue
                
            old_data = current_record_response.data[0]
            model_no = old_data.get('Model No.', 'Unknown')
            
            # Delete the record
            response = supabase.table("pump_selection_data").delete().eq('"DB ID"', db_id).execute()
            
            # Log in audit trail
            log_database_change(
                table_name="pump_selection_data",
                record_id=db_id,
                operation="DELETE",
                old_data=old_data,
                description=description or f"Bulk deleted pump: {model_no}"
            )
            
            success_count += 1
            
            # Update progress
            progress = (idx + 1) / len(db_ids)
            progress_bar.progress(progress, text=f"{progress_text} ({idx+1}/{len(db_ids)})")
            
        except Exception as e:
            error_count += 1
            error_messages.append(f"Error deleting DB ID {db_id}: {str(e)}")
    
    # Clear progress bar
    progress_bar.empty()
    
    # Create result message
    if error_count == 0:
        return True, get_text("deleted_all_successfully", success_count), success_count, error_count
    else:
        error_details = "\n".join(error_messages[:5])
        if len(error_messages) > 5:
            error_details += f"\n... and {len(error_messages) - 5} more errors."
        
        message = get_text("deleted_with_errors", success_count, error_count) + f"\n{error_details}"
        return success_count > 0, message, success_count, error_count

# --- App Header ---
st.title(f"💧 {get_text('app_title')}")
st.markdown(get_text('app_description'))
st.info(f"{get_text('current_time')}: {datetime.now(taiwan_tz).strftime('%Y-%m-%d %H:%M:%S')}")

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
    st.error(f"Error fetching data: {e}")
    st.error(traceback.format_exc())
    df = pd.DataFrame()

# --- Sidebar for actions and filters ---
with st.sidebar:
    st.header(get_text("actions"))
    action = st.radio(
        get_text("choose_action"),
        [get_text("view_data"), get_text("add_new_pump"), get_text("edit_pump"), get_text("delete_pump"), get_text("bulk_delete")]
    )
    
    if not df.empty:
        st.header(get_text("filters"))
        
        # Model Group Filter
        all_option = get_text("all_option")
        model_groups = [all_option] + sorted(df['Model Group'].unique().tolist())
        selected_group = st.selectbox(get_text("filter_by_model_group"), model_groups)
        
        # Category Filter (if exists)
        if "Category" in df.columns:
            # Get unique non-empty categories
            categories = [c for c in df["Category"].unique() if c and c.strip() and c.lower() not in ["nan", "none"]]
            categories = [all_option] + sorted(categories)
            selected_category = st.selectbox(get_text("filter_by_category"), categories)
        else:
            selected_category = all_option
    else:
        selected_group = all_option
        selected_category = all_option
    
    if st.button(f"🔄 {get_text('refresh_data')}"):
        st.cache_data.clear()
        st.rerun()

# --- Main Content Based on Action ---
if action == get_text("view_data"):
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
            
            # Update the refresh message with Taiwan time
            refresh_placeholder.info(f"{get_text('last_checked')}: {datetime.now(taiwan_tz).strftime('%H:%M:%S')}")
    
    try:
        if df.empty:
            st.info(get_text("no_data_found"))
        else:
            # Display data info
            st.success(f"✅ {get_text('loaded_records', len(df))}")
            
            # Apply filters
            filtered_df = apply_filters(df, selected_group, selected_category)
            
            # Show filter results
            if selected_group != all_option:
                st.write(f"{get_text('filter_by_model_group')}: {selected_group}")
            if selected_category != all_option:
                st.write(f"{get_text('filter_by_category')}: {selected_category} ({get_text('matching')} {len(filtered_df)} {get_text('records')})")
            
            # Add search functionality
            search_term = st.text_input(f"🔍 {get_text('search_by_model')}")
            
            if search_term:
                filtered_df = filtered_df[filtered_df["Model No."].astype(str).str.contains(search_term, case=False, na=False)]
                st.write(f"{get_text('found')} {len(filtered_df)} {get_text('matching_pumps')}")
            
            if filtered_df.empty:
                st.info(get_text("no_match"))
            else:
                # Data Table with pagination controls
                st.subheader(f"📋 {get_text('pump_data_table')}")
                
                # Add sorting options
                sort_columns = ["Model Group", "DB ID"] + [col for col in filtered_df.columns if col not in ["DB ID", "Model Group"]]
                sort_column = st.selectbox(get_text("sort_by"), sort_columns, index=0)
                sort_order = st.radio(get_text("sort_order"), [get_text("ascending"), get_text("descending")], horizontal=True)
                
                # Apply sorting
                if sort_order == get_text("ascending"):
                    sorted_df = filtered_df.sort_values(by=sort_column)
                else:
                    sorted_df = filtered_df.sort_values(by=sort_column, ascending=False)
                
                # Show row count selection
                rows_per_page = st.selectbox(get_text("rows_per_page"), [10, 25, 50, 100, get_text("all_option")], index=1)
                
                if rows_per_page == get_text("all_option"):
                    st.dataframe(sorted_df, use_container_width=True)
                else:
                    # Manual pagination
                    total_rows = len(sorted_df)
                    total_pages = (total_rows + rows_per_page - 1) // rows_per_page if rows_per_page != get_text("all_option") else 1
                    
                    if total_pages > 0:
                        page = st.number_input(get_text("page"), min_value=1, max_value=total_pages, value=1)
                        start_idx = (page - 1) * rows_per_page
                        end_idx = min(start_idx + rows_per_page, total_rows)
                        
                        st.dataframe(sorted_df.iloc[start_idx:end_idx], use_container_width=True)
                        st.write(get_text("showing_rows", start_idx+1, end_idx, total_rows))
                    else:
                        st.info(get_text("no_data_to_display"))
                
                # Show summary by group
                st.subheader(f"📊 {get_text('model_group_summary')}")
                group_counts = filtered_df['Model Group'].value_counts().reset_index()
                group_counts.columns = [get_text('model_group'), get_text('count')]
                st.dataframe(group_counts, use_container_width=True)
                    
    except Exception as e:
        st.error(f"Error: {e}")
        st.error(traceback.format_exc())

elif action == get_text("add_new_pump"):
    st.subheader(get_text("add_new_pump"))
    
    # Define fields based on your table structure
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
    
    # Create input form for new pump
    with st.form("add_pump_form"):
        new_pump_data = {}
        
        # Model No. is required
        new_pump_data["Model No."] = st.text_input(f"Model No. *", help=get_text("required_field"))
        
        # Show predicted model group based on input
        if new_pump_data["Model No."]:
            predicted_group = extract_model_group(new_pump_data["Model No."])
            st.info(get_text("predicted_model_group", predicted_group))
        
        # Create columns for better layout
        col1, col2 = st.columns(2)
        
        with col1:
            new_pump_data["Frequency (Hz)"] = st.number_input("Frequency (Hz)", value=50, step=1)
            new_pump_data["Phase"] = st.number_input("Phase", value=3, step=1)
            new_pump_data["HP"] = st.text_input("HP")
            new_pump_data["Power(KW)"] = st.text_input("Power(KW)")
            new_pump_data["Outlet (mm)"] = st.number_input("Outlet (mm)", value=0, step=1)
            new_pump_data["Outlet (inch)"] = st.text_input("Outlet (inch)")
        
        with col2:
            new_pump_data["Pass Solid Dia(mm)"] = st.number_input("Pass Solid Dia(mm)", value=0, step=1)
            new_pump_data["Max Flow (LPM)"] = st.text_input("Max Flow (LPM)")
            new_pump_data["Max Head (M)"] = st.number_input("Max Head (M)", value=0.0)
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
        change_description = st.text_area(get_text("change_description"), placeholder=get_text("change_description_placeholder"))
        
        submit_button = st.form_submit_button(get_text("add_pump_button"))
        
        if submit_button:
            # Validate required fields
            if not new_pump_data.get("Model No."):
                st.error(get_text("model_no_required"))
            else:
                success, message = insert_pump_data(new_pump_data, description=change_description)
                if success:
                    st.success(message)
                    # Clear cache to refresh data
                    st.cache_data.clear()
                else:
                    st.error(message)

elif action == get_text("edit_pump"):
    st.subheader(get_text("edit_pump"))
    st.caption(f"{get_text('current_time')}: {datetime.now(taiwan_tz).strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        if df.empty:
            st.info(get_text("no_data_found"))
        else:
            # Apply the same filters as in View Data
            filtered_df = apply_filters(df, selected_group, selected_category)
            
            # Show filter results
            if selected_group != all_option:
                st.write(f"{get_text('filter_by_model_group')}: {selected_group}")
            if selected_category != all_option:
                st.write(f"{get_text('filter_by_category')}: {selected_category} ({get_text('matching')} {len(filtered_df)} {get_text('records')})")
                
            if filtered_df.empty:
                st.info(get_text("no_match"))
            else:
                # Use Model No. for pump identification based on your table structure
                id_column = "Model No."
                
                # Select pump to edit
                pump_options = filtered_df[id_column].astype(str).tolist()
                selected_pump_id = st.selectbox(get_text("select_pump_edit", id_column), pump_options)
                
                # Get selected pump data
                selected_pump = filtered_df[filtered_df[id_column].astype(str) == selected_pump_id].iloc[0]
                db_id = selected_pump["DB ID"]
                
                # Show current Model Group
                current_group = extract_model_group(selected_pump_id)
                st.info(get_text("current_model_group", current_group))
                
                # Create form for editing
                with st.form("edit_pump_form"):
                    edited_data = {}
                    
                    # Create columns for better layout
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        for column in ["Model No.", "Frequency (Hz)", "Phase", "HP", "Power(KW)", "Outlet (mm)", "Outlet (inch)"]:
                            if column in df.columns:
                                current_value = selected_pump[column]
                                
                                if pd.isna(current_value):
                                    # Handle NaN values
                                    if column in ["Frequency (Hz)", "Phase", "Outlet (mm)"]:
                                        edited_data[column] = st.number_input(f"{column}", value=0, step=1)
                                    else:
                                        edited_data[column] = st.text_input(f"{column}", value="")
                                elif isinstance(current_value, (int, float)) and column in ["Frequency (Hz)", "Phase", "Outlet (mm)"]:
                                    edited_data[column] = st.number_input(f"{column}", value=int(current_value), step=1)
                                elif isinstance(current_value, str) and column not in ["Frequency (Hz)", "Phase", "Outlet (mm)"]:
                                    edited_data[column] = st.text_input(f"{column}", value=current_value)
                                else:
                                    try:
                                        if column in ["Frequency (Hz)", "Phase", "Outlet (mm)"]:
                                            edited_data[column] = st.number_input(f"{column}", value=int(float(current_value)), step=1)
                                        else:
                                            edited_data[column] = st.text_input(f"{column}", value=str(current_value))
                                    except:
                                        edited_data[column] = st.text_input(f"{column}", value=str(current_value))
                    
                    with col2:
                        for column in ["Pass Solid Dia(mm)", "Max Flow (LPM)", "Max Head (M)", "Max Head (ft)", "Category", "Product Link"]:
                            if column in df.columns:
                                current_value = selected_pump[column]
                                
                                if pd.isna(current_value) or str(current_value).lower() in ["nan", "none", ""]:
                                    # Handle NaN values
                                    if column in ["Pass Solid Dia(mm)"]:
                                        edited_data[column] = st.number_input(f"{column}", value=0, step=1)
                                    elif column in ["Max Head (M)"]:
                                        edited_data[column] = st.number_input(f"{column}", value=0.0)
                                    elif column == "Category":
                                        # Get unique non-empty categories
                                        categories = [c for c in df["Category"].unique() if c and c.strip() and c.lower() not in ["nan", "none"]]
                                        categories = [""] + sorted(categories)
                                        edited_data[column] = st.selectbox(f"{column}", categories)
                                    else:
                                        edited_data[column] = st.text_input(f"{column}", value="")
                                elif column == "Category":
                                    # Get unique non-empty categories
                                    categories = [c for c in df["Category"].unique() if c and c.strip() and c.lower() not in ["nan", "none"]]
                                    categories = [""] + sorted(categories)
                                    edited_data[column] = st.selectbox(f"{column}", categories, index=categories.index(current_value) if current_value in categories else 0)
                                elif isinstance(current_value, (int, float)) and column in ["Pass Solid Dia(mm)"]:
                                    edited_data[column] = st.number_input(f"{column}", value=int(current_value), step=1)
                                elif isinstance(current_value, (int, float)) and column in ["Max Head (M)"]:
                                    edited_data[column] = st.number_input(f"{column}", value=float(current_value))
                                elif isinstance(current_value, str) and column not in ["Pass Solid Dia(mm)", "Max Head (M)"]:
                                    edited_data[column] = st.text_input(f"{column}", value=current_value)
                                else:
                                    try:
                                        if column in ["Pass Solid Dia(mm)"]:
                                            edited_data[column] = st.number_input(f"{column}", value=int(float(current_value)), step=1)
                                        elif column in ["Max Head (M)"]:
                                            edited_data[column] = st.number_input(f"{column}", value=float(current_value))
                                        else:
                                            edited_data[column] = st.text_input(f"{column}", value=str(current_value))
                                    except:
                                        edited_data[column] = st.text_input(f"{column}", value=str(current_value))
                    
                    # Add change description
                    change_description = st.text_area(get_text("change_description"), 
                                                    placeholder=get_text("edit_change_description_placeholder"))
                    
                    submit_button = st.form_submit_button(get_text("update_pump_button"))
                    
                    if submit_button:
                        success, message = update_pump_data(db_id, edited_data, description=change_description)
                        if success:
                            st.success(message)
                            # Show new Model Group if Model No. was changed
                            if edited_data["Model No."] != selected_pump_id:
                                new_group = extract_model_group(edited_data["Model No."])
                                st.info(get_text("new_model_group", new_group))
                            # Clear cache to refresh data
                            st.cache_data.clear()
                        else:
                            st.error(message)
    
    except Exception as e:
        st.error(f"Error setting up edit form: {e}")
        st.error(traceback.format_exc())  # This will show the detailed error in development

elif action == get_text("delete_pump"):
    st.subheader(get_text("delete_pump"))
    st.caption(f"{get_text('current_time')}: {datetime.now(taiwan_tz).strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        if df.empty:
            st.info(get_text("no_data_found"))
        else:
            # Apply the same filters as in View Data
            filtered_df = apply_filters(df, selected_group, selected_category)
            
            # Show filter results
            if selected_group != all_option:
                st.write(f"{get_text('filter_by_model_group')}: {selected_group}")
            if selected_category != all_option:
                st.write(f"{get_text('filter_by_category')}: {selected_category} ({get_text('matching')} {len(filtered_df)} {get_text('records')})")
                
            if filtered_df.empty:
                st.info(get_text("no_match"))
            else:
                # Use Model No. for pump identification based on your table structure
                id_column = "Model No."
                
                # Select pump to delete
                pump_options = filtered_df[id_column].astype(str).tolist()
                selected_pump_id = st.selectbox(get_text("select_pump_delete", id_column), pump_options)
                
                # Get selected pump data
                selected_pump = filtered_df[filtered_df[id_column].astype(str) == selected_pump_id].iloc[0]
                db_id = selected_pump["DB ID"]
                
                # Show current Model Group
                current_group = extract_model_group(selected_pump_id)
                st.info(f"{get_text('model_group')}: {current_group}")
                
                # Display pump details
                st.write(f"{get_text('pump_details')}:")
                details_cols = st.columns(2)
                
                with details_cols[0]:
                    st.write(f"**DB ID:** {db_id}")
                    st.write(f"**{get_text('model_no')}:** {selected_pump['Model No.']}")
                    
                    if "Category" in selected_pump:
                        st.write(f"**{get_text('category')}:** {selected_pump['Category']}")
                    
                    if "HP" in selected_pump:
                        st.write(f"**HP:** {selected_pump['HP']}")
                    
                    if "Power(KW)" in selected_pump:
                        st.write(f"**{get_text('power')}:** {selected_pump['Power(KW)']} KW")
                
                with details_cols[1]:
                    if "Max Flow (LPM)" in selected_pump:
                        st.write(f"**{get_text('max_flow')}:** {selected_pump['Max Flow (LPM)']} LPM")
                    
                    if "Max Head (M)" in selected_pump:
                        st.write(f"**{get_text('max_head')}:** {selected_pump['Max Head (M)']} m")
                    
                    if "Outlet (mm)" in selected_pump:
                        st.write(f"**{get_text('outlet')}:** {selected_pump['Outlet (mm)']} mm")
                    
                    if "Frequency (Hz)" in selected_pump:
                        st.write(f"**{get_text('frequency')}:** {selected_pump['Frequency (Hz)']} Hz")
                
                # Add delete reason
                delete_reason = st.text_area(get_text("reason_for_deletion"),
                                         placeholder=get_text("delete_reason_placeholder"))
                
                # Confirm deletion
                st.warning(f"⚠️ {get_text('delete_confirmation')}")
                confirm_delete = st.button(get_text("confirm_delete"))
                
                if confirm_delete:
                    success, message = delete_pump_data(db_id, description=delete_reason)
                    if success:
                        st.success(message)
                        # Clear cache to refresh data
                        st.cache_data.clear()
                    else:
                        st.error(message)
    
    except Exception as e:
        st.error(f"Error setting up delete form: {e}")
        st.error(traceback.format_exc())  # This will show the detailed error in development

# Add Bulk Delete Feature
elif action == get_text("bulk_delete"):
    st.subheader(f"🗑️ {get_text('bulk_delete_title')}")
    st.caption(f"{get_text('current_time')}: {datetime.now(taiwan_tz).strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        if df.empty:
            st.info(get_text("no_data_found"))
        else:
            # Apply the same filters as in View Data
            filtered_df = apply_filters(df, selected_group, selected_category)
            
            # Show filter results
            if selected_group != all_option:
                st.write(f"{get_text('filter_by_model_group')}: {selected_group}")
            if selected_category != all_option:
                st.write(f"{get_text('filter_by_category')}: {selected_category} ({get_text('matching')} {len(filtered_df)} {get_text('records')})")
            
            # Show count of filtered records
            st.info(get_text("current_filter_showing", len(filtered_df)))
            
            if filtered_df.empty:
                st.info(get_text("no_match"))
            else:
                st.markdown(f"### 🔍 {get_text('select_records_to_delete')}")
                
                # Selection method options
                selection_method = st.radio(
                    get_text("select_deletion_method"), 
                    [get_text("by_category"), get_text("by_model_group"), get_text("manual_selection")]
                )
                
                if selection_method == get_text("by_category"):
                    # Delete by Category
                    if "Category" in filtered_df.columns:
                        # Get unique non-empty categories from filtered data
                        categories = [c for c in filtered_df["Category"].unique() if c and c.strip() and c.lower() not in ["nan", "none", ""]]
                        categories.sort()
                        
                        if not categories:
                            st.warning(get_text("no_categories_found"))
                        else:
                            selected_category_to_delete = st.selectbox(get_text("select_category_to_delete"), categories)
                            
                            # Count records in the selected category
                            category_df = filtered_df[filtered_df["Category"].str.lower() == selected_category_to_delete.lower()]
                            record_count = len(category_df)
                            
                            st.warning(f"⚠️ {get_text('about_to_delete_category', record_count, selected_category_to_delete)}")
                            
                            # Display sample records
                            with st.expander(get_text("preview_records", min(5, record_count), record_count)):
                                st.dataframe(category_df.head(5)[["DB ID", "Model No.", "Category"]])
                            
                            # Get DB IDs to delete
                            db_ids_to_delete = category_df["DB ID"].tolist()
                    else:
                        st.error("Category column not found in the data. Please choose another deletion method.")
                        db_ids_to_delete = []
                
                elif selection_method == get_text("by_model_group"):
                    # Delete by Model Group
                    if "Model Group" in filtered_df.columns:
                        # Get unique model groups from filtered data
                        model_groups = sorted(filtered_df["Model Group"].unique().tolist())
                        
                        if not model_groups:
                            st.warning(get_text("no_model_groups_found"))
                        else:
                            selected_group_to_delete = st.selectbox(get_text("select_model_group_to_delete"), model_groups)
                            
                            # Count records in the selected model group
                            group_df = filtered_df[filtered_df["Model Group"] == selected_group_to_delete]
                            record_count = len(group_df)
                            
                            st.warning(f"⚠️ {get_text('about_to_delete_group', record_count, selected_group_to_delete)}")
                            
                            # Display sample records
                            with st.expander(get_text("preview_records", min(5, record_count), record_count)):
                                st.dataframe(group_df.head(5)[["DB ID", "Model No.", "Model Group"]])
                            
                            # Get DB IDs to delete
                            db_ids_to_delete = group_df["DB ID"].tolist()
                    else:
                        st.error("Model Group column not found in the data. Please choose another deletion method.")
                        db_ids_to_delete = []
                
                else:  # Manual Selection
                    # Allow manual selection of records from a dataframe
                    st.write(get_text("select_pumps_to_delete"))
                    
                    # Add search to narrow down results
                    search_term = st.text_input(f"🔍 {get_text('search_by_model')}")
                    
                    display_df = filtered_df.copy()
                    if search_term:
                        display_df = display_df[display_df["Model No."].astype(str).str.contains(search_term, case=False, na=False)]
                        st.write(f"{get_text('found')} {len(display_df)} {get_text('matching_pumps')}")
                    
                    # Check if we have too many records to display for manual selection
                    if len(display_df) > 100:
                        st.warning(f"⚠️ {get_text('too_many_records', len(display_df))}")
                    else:
                        # Create a multiselect with model numbers for selection
                        # First, create a list of options with formatted strings for better selection
                        selection_options = []
                        for _, row in display_df.iterrows():
                            model_no = row.get("Model No.", "Unknown")
                            category = row.get("Category", "") if "Category" in row else ""
                            db_id = row.get("DB ID", "")
                            selection_text = f"{model_no} (ID: {db_id})"
                            if category:
                                selection_text += f" - {category}"
                            selection_options.append(selection_text)
                        
                        # Allow selection from the list
                        if selection_options:
                            selected_items = st.multiselect(get_text("select_pumps_to_delete"), selection_options)
                            
                            # Extract DB IDs from selected items
                            db_ids_to_delete = []
                            if selected_items:
                                for item in selected_items:
                                    # Extract DB ID from selection text using regex
                                    match = re.search(r"ID: (\d+)", item)
                                    if match:
                                        db_id = int(match.group(1))
                                        db_ids_to_delete.append(db_id)
                        else:
                            st.info(get_text("no_pumps_match"))
                            db_ids_to_delete = []
                
                # Add delete reason
                if 'db_ids_to_delete' in locals() and db_ids_to_delete:
                    delete_reason = st.text_area(get_text("reason_for_deletion"),
                                            placeholder=get_text("bulk_delete_reason_placeholder"))
                    
                    # Confirm deletion
                    st.warning(f"⚠️ {get_text('deletion_warning', len(db_ids_to_delete))}")
                    confirm_delete = st.button(get_text("confirm_bulk_delete"))
                    
                    if confirm_delete:
                        success, message, success_count, error_count = bulk_delete_pumps(db_ids_to_delete, description=delete_reason)
                        if success:
                            st.success(message)
                            # Show success/error counts
                            if error_count > 0:
                                st.info(get_text("deleted_with_errors", success_count, error_count))
                            # Clear cache to refresh data
                            st.cache_data.clear()
                        else:
                            st.error(message)
                else:
                    st.info(get_text("please_select_records"))
    
    except Exception as e:
        st.error(f"Error setting up bulk delete form: {e}")
        st.error(traceback.format_exc())  # This will show the detailed error in development

# --- Footer ---
st.markdown("---")
st.markdown(f"💧 **{get_text('app_title')}** | {get_text('last_updated')}: " + datetime.now(taiwan_tz).strftime("%Y-%m-%d %H:%M:%S"))
