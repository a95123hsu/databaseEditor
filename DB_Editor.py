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
        user_id = user.get('id', 'anonymous') if user else 'anonymous'
        user_email = user.get('email', 'unknown') if user else 'unknown'
        
        # Prepare the audit record
        audit_record = {
            "id": str(uuid.uuid4()),
            "table_name": table_name,
            "record_id": record_id,
            "operation": operation,
            "old_data": json.dumps(old_data) if old_data else None,
            "new_data": json.dumps(new_data) if new_data else None,
            "modified_by": user_email,
            "modified_at": datetime.utcnow().isoformat(),
            "description": description
        }
        
        # Insert into audit_trail table
        response = supabase.table("audit_trail").insert(audit_record).execute()
        
        # Log success for debugging
        print(f"Audit trail entry created for {operation} on {table_name} (ID: {record_id})")
        return True
    except Exception as e:
        st.error(f"Failed to create audit trail entry: {e}")
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
        st.session_state.last_check = datetime.now()
    
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
            
            # Update last check time
            st.session_state.last_check = datetime.now()
            
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
                # Create a clean timestamp
                try:
                    timestamp = datetime.fromisoformat(change['modified_at'].replace('Z', '+00:00')).strftime('%H:%M:%S')
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
        
        return True, "Pump data deleted successfully!"
    except Exception as e:
        st.error(f"Error details for debugging: {str(e)}")
        st.error(traceback.format_exc())
        return False, f"Error deleting pump data: {e}"

# --- App Header ---
st.title("💧 Pump Selection Data Manager")
st.markdown("View, add, edit, and delete pump selection data")

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
    
    if st.button("🔄 Refresh Data"):
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
            refresh_placeholder.info(f"Last checked for updates: {datetime.now().strftime('%H:%M:%S')}")
    
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
            search_term = st.text_input("🔍 Search by Model No.:")
            
            if search_term:
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
                    st.dataframe(sorted_df, use_container_width=True)
                else:
                    # Manual pagination
                    total_rows = len(sorted_df)
                    total_pages = (total_rows + rows_per_page - 1) // rows_per_page if rows_per_page != "All" else 1
                    
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
        st.error(f"Error: {e}")
        st.error(traceback.format_exc())

elif action == "Add New Pump":
    st.subheader("Add New Pump")
    
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
        new_pump_data["Model No."] = st.text_input("Model No. *", help="Required field")
        
        # Show predicted model group based on input
        if new_pump_data["Model No."]:
            predicted_group = extract_model_group(new_pump_data["Model No."])
            st.info(f"Predicted Model Group: {predicted_group}")
        
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
        change_description = st.text_area("Change Description (optional)", placeholder="Why are you adding this pump?")
        
        submit_button = st.form_submit_button("Add Pump")
        
        if submit_button:
            # Validate required fields
            if not new_pump_data.get("Model No."):
                st.error("Model No. is required.")
            else:
                success, message = insert_pump_data(new_pump_data, description=change_description)
                if success:
                    st.success(message)
                    # Clear cache to refresh data
                    st.cache_data.clear()
                else:
                    st.error(message)

elif action == "Edit Pump":
    st.subheader("Edit Pump")
    
    try:
        if df.empty:
            st.info("No data found to edit.")
        else:
            # Apply the same filters as in View Data
            filtered_df = apply_filters(df, selected_group, selected_category)
            
            # Show filter results
            if selected_group != "All":
                st.write(f"Filtered by Model Group: {selected_group}")
            if selected_category != "All":
                st.write(f"Filtered by Category: {selected_category} (matching {len(filtered_df)} records)")
                
            if filtered_df.empty:
                st.info("No pumps match your filter criteria.")
            else:
                # Use Model No. for pump identification based on your table structure
                id_column = "Model No."
                
                # Select pump to edit
                pump_options = filtered_df[id_column].astype(str).tolist()
                selected_pump_id = st.selectbox(f"Select pump to edit (by {id_column}):", pump_options)
                
                # Get selected pump data
                selected_pump = filtered_df[filtered_df[id_column].astype(str) == selected_pump_id].iloc[0]
                db_id = selected_pump["DB ID"]
                
                # Show current Model Group
                current_group = extract_model_group(selected_pump_id)
                st.info(f"Current Model Group: {current_group}")
                
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
                    change_description = st.text_area("Change Description (optional)", 
                                                    placeholder="Describe why you're updating this pump...")
                    
                    submit_button = st.form_submit_button("Update Pump")
                    
                    if submit_button:
                        success, message = update_pump_data(db_id, edited_data, description=change_description)
                        if success:
                            st.success(message)
                            # Show new Model Group if Model No. was changed
                            if edited_data["Model No."] != selected_pump_id:
                                new_group = extract_model_group(edited_data["Model No."])
                                st.info(f"New Model Group: {new_group}")
                            # Clear cache to refresh data
                            st.cache_data.clear()
                        else:
                            st.error(message)
    
    except Exception as e:
        st.error(f"Error setting up edit form: {e}")
        st.error(traceback.format_exc())  # This will show the detailed error in development

elif action == "Delete Pump":
    st.subheader("Delete Pump")
    
    try:
        if df.empty:
            st.info("No data found to delete.")
        else:
            # Apply the same filters as in View Data
            filtered_df = apply_filters(df, selected_group, selected_category)
            
            # Show filter results
            if selected_group != "All":
                st.write(f"Filtered by Model Group: {selected_group}")
            if selected_category != "All":
                st.write(f"Filtered by Category: {selected_category} (matching {len(filtered_df)} records)")
                
            if filtered_df.empty:
                st.info("No pumps match your filter criteria.")
            else:
                # Use Model No. for pump identification based on your table structure
                id_column = "Model No."
                
                # Select pump to delete
                pump_options = filtered_df[id_column].astype(str).tolist()
                selected_pump_id = st.selectbox(f"Select pump to delete (by {id_column}):", pump_options)
                
                # Get selected pump data
                selected_pump = filtered_df[filtered_df[id_column].astype(str) == selected_pump_id].iloc[0]
                db_id = selected_pump["DB ID"]
                
                # Show current Model Group
                current_group = extract_model_group(selected_pump_id)
                st.info(f"Model Group: {current_group}")
                
                # Display pump details
                st.write("Pump Details:")
                details_cols = st.columns(2)
                
                with details_cols[0]:
                    st.write(f"**DB ID:** {db_id}")
                    st.write(f"**Model No.:** {selected_pump['Model No.']}")
                    
                    if "Category" in selected_pump:
                        st.write(f"**Category:** {selected_pump['Category']}")
                    
                    if "HP" in selected_pump:
                        st.write(f"**HP:** {selected_pump['HP']}")
                    
                    if "Power(KW)" in selected_pump:
                        st.write(f"**Power:** {selected_pump['Power(KW)']} KW")
                
                with details_cols[1]:
                    if "Max Flow (LPM)" in selected_pump:
                        st.write(f"**Max Flow:** {selected_pump['Max Flow (LPM)']} LPM")
                    
                    if "Max Head (M)" in selected_pump:
                        st.write(f"**Max Head:** {selected_pump['Max Head (M)']} m")
                    
                    if "Outlet (mm)" in selected_pump:
                        st.write(f"**Outlet:** {selected_pump['Outlet (mm)']} mm")
                    
                    if "Frequency (Hz)" in selected_pump:
                        st.write(f"**Frequency:** {selected_pump['Frequency (Hz)']} Hz")
                
                # Add delete reason
                delete_reason = st.text_area("Reason for deletion (optional)",
                                         placeholder="Why are you deleting this pump?")
                
                # Confirm deletion
                st.warning("⚠️ Warning: This action cannot be undone!")
                confirm_delete = st.button("Confirm Delete")
                
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

# --- Footer ---
st.markdown("---")
st.markdown("💧 **Pump Selection Data Manager** | Last updated: " + pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"))
