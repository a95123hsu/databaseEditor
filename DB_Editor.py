import streamlit as st
import pandas as pd
from supabase import create_client, Client
import re
import traceback
from login import login_form, get_user_session, logout
import bcrypt
import uuid
import os

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

# --- CRUD Operations ---
def insert_pump_data(pump_data):
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
            st.write(f"Generated new DB ID: {new_id}")
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
        
        # Show the data being sent to Supabase
        st.write("Sending the following data to Supabase:")
        st.write(clean_data)
        
        # Insert the data
        response = supabase.table("pump_selection_data").insert(clean_data).execute()
        return True, f"Pump data added successfully with DB ID: {new_id}!"
    except Exception as e:
        st.error(f"Error details for debugging: {str(e)}")
        st.error(traceback.format_exc())
        return False, f"Error adding pump data: {e}"

def update_pump_data(db_id, pump_data):
    try:
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
            
        # Test each field individually to find any remaining problematic ones
        problem_keys = []
        for key, value in list(clean_data.items()):  # Use list() to create a copy of keys for safe iteration
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
        return True, "Pump data updated successfully!"
    except Exception as e:
        st.error(f"Error details for debugging: {str(e)}")
        st.error(traceback.format_exc())
        return False, f"Error updating pump data: {e}"

def delete_pump_data(db_id):
    try:
        # Note the double quotes around DB ID
        response = supabase.table("pump_selection_data").delete().eq('"DB ID"', db_id).execute()
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
        
        submit_button = st.form_submit_button("Add Pump")
        
        if submit_button:
            # Validate required fields
            if not new_pump_data.get("Model No."):
                st.error("Model No. is required.")
            else:
                success, message = insert_pump_data(new_pump_data)
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
                    
                    submit_button = st.form_submit_button("Update Pump")
                    
                    if submit_button:
                        success, message = update_pump_data(db_id, edited_data)
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
                
                # Confirm deletion
                st.warning("⚠️ Warning: This action cannot be undone!")
                confirm_delete = st.button("Confirm Delete")
                
                if confirm_delete:
                    success, message = delete_pump_data(db_id)
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
