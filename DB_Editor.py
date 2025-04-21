import streamlit as st
import pandas as pd
from supabase import create_client, Client
import json

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
            response = supabase.table("pump_selection_data").select("*").order("DB ID").range(start_idx, start_idx + page_size - 1).execute()
            
            if response.data:
                all_data.extend(response.data)
            
            # Update progress
            progress = min((start_idx + page_size) / total_count, 1.0)
            progress_bar.progress(progress, text=f"{progress_text} ({len(all_data)}/{total_count})")
    
    # Clear progress bar when done
    progress_bar.empty()
    
    return pd.DataFrame(all_data)

# --- CRUD Operations ---
def insert_pump_data(pump_data):
    try:
        response = supabase.table("pump_selection_data").insert(pump_data).execute()
        return True, "Pump data added successfully!"
    except Exception as e:
        return False, f"Error adding pump data: {e}"

def update_pump_data(db_id, pump_data):
    try:
        response = supabase.table("pump_selection_data").update(pump_data).eq("DB ID", db_id).execute()
        return True, "Pump data updated successfully!"
    except Exception as e:
        return False, f"Error updating pump data: {e}"

def delete_pump_data(db_id):
    try:
        response = supabase.table("pump_selection_data").delete().eq("DB ID", db_id).execute()
        return True, "Pump data deleted successfully!"
    except Exception as e:
        return False, f"Error deleting pump data: {e}"

# --- Page Configuration ---
st.set_page_config(
    page_title="Pump Selection Data Manager", 
    page_icon="💧", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- App Header ---
st.title("💧 Pump Selection Data Manager")
st.markdown("View, add, edit, and delete pump selection data")

# --- Initialize Supabase Client ---
supabase = init_connection()

# --- Sidebar for actions ---
with st.sidebar:
    st.header("Actions")
    action = st.radio(
        "Choose an action:",
        ["View Data", "Add New Pump", "Edit Pump", "Delete Pump"]
    )
    
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.experimental_rerun()

# --- Main Content Based on Action ---
if action == "View Data":
    try:
        # Fetch data
        df = fetch_all_pump_data()
        
        if df.empty:
            st.info("No data found in 'pump_selection_data'.")
        else:
            # Display data info
            st.success(f"✅ Successfully loaded {len(df)} pump records")
            
            # Add search functionality
            search_term = st.text_input("🔍 Search by pump name:")
            
            if search_term:
                filtered_df = df[df["name"].str.contains(search_term, case=False, na=False)]
                st.write(f"Found {len(filtered_df)} matching pumps")
            else:
                filtered_df = df
            
            # Data Table with pagination controls
            st.subheader("📋 Pump Data Table")
            
            # Add sorting options
            if not filtered_df.empty:
                sort_columns = ["DB ID"] + [col for col in filtered_df.columns if col != "DB ID"]
                sort_column = st.selectbox("Sort by:", sort_columns, index=0)
                sort_order = st.radio("Sort order:", ["Ascending", "Descending"], horizontal=True)
                
                # Apply sorting
                if sort_order == "Ascending":
                    sorted_df = filtered_df.sort_values(by=sort_column)
                else:
                    sorted_df = filtered_df.sort_values(by=sort_column, ascending=False)
            else:
                sorted_df = filtered_df
                
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
                    
    except Exception as e:
        st.error(f"Error: {e}")

elif action == "Add New Pump":
    st.subheader("Add New Pump")
    
    # First, fetch a sample record to determine columns
    try:
        sample_df = fetch_all_pump_data()
        if sample_df.empty:
            st.warning("No existing records found. Please define the fields for your pump data:")
            # Default fields if no existing data
            fields = {
                "name": "",
                "manufacturer": "",
                "flow_rate": 0.0,
                "head_height": 0.0,
                "power": 0.0,
                "efficiency": 0.0,
                "price": 0.0
            }
        else:
            # Get fields from existing data
            fields = {col: "" for col in sample_df.columns}
            # Remove primary key if it exists
            if "DB ID" in fields:
                del fields["DB ID"]
                
        # Create input form for new pump
        with st.form("add_pump_form"):
            new_pump_data = {}
            
            for field, default_value in fields.items():
                if field != "DB ID":  # Skip primary key
                    if isinstance(default_value, (int, float)) or (isinstance(default_value, str) and default_value.replace('.', '', 1).isdigit()):
                        new_pump_data[field] = st.number_input(f"{field.replace('_', ' ').title()}", value=0.0)
                    else:
                        new_pump_data[field] = st.text_input(f"{field.replace('_', ' ').title()}")
            
            submit_button = st.form_submit_button("Add Pump")
            
            if submit_button:
                # Validate required fields
                if not new_pump_data.get("name"):
                    st.error("Pump name is required.")
                else:
                    success, message = insert_pump_data(new_pump_data)
                    if success:
                        st.success(message)
                        # Clear cache to refresh data
                        st.cache_data.clear()
                    else:
                        st.error(message)
    
    except Exception as e:
        st.error(f"Error setting up add form: {e}")

elif action == "Edit Pump":
    st.subheader("Edit Pump")
    
    try:
        # Fetch data to populate selection
        df = fetch_all_pump_data()
        
        if df.empty:
            st.info("No data found to edit.")
        else:
            # Select pump to edit
            pump_options = df["name"].tolist()
            selected_pump_name = st.selectbox("Select pump to edit:", pump_options)
            
            # Get selected pump data
            selected_pump = df[df["name"] == selected_pump_name].iloc[0]
            db_id = selected_pump["DB ID"]
            
            # Create form for editing
            with st.form("edit_pump_form"):
                edited_data = {}
                
                for column in df.columns:
                    if column != "DB ID":  # Skip primary key
                        current_value = selected_pump[column]
                        
                        if isinstance(current_value, (int, float)) or (isinstance(current_value, str) and current_value.replace('.', '', 1).isdigit()):
                            try:
                                numeric_value = float(current_value) if isinstance(current_value, str) else current_value
                                edited_data[column] = st.number_input(f"{column.replace('_', ' ').title()}", value=numeric_value)
                            except:
                                edited_data[column] = st.text_input(f"{column.replace('_', ' ').title()}", value=str(current_value))
                        else:
                            edited_data[column] = st.text_input(f"{column.replace('_', ' ').title()}", value=str(current_value) if pd.notna(current_value) else "")
                
                submit_button = st.form_submit_button("Update Pump")
                
                if submit_button:
                    # Validate required fields
                    if not edited_data.get("name"):
                        st.error("Pump name is required.")
                    else:
                        success, message = update_pump_data(db_id, edited_data)
                        if success:
                            st.success(message)
                            # Clear cache to refresh data
                            st.cache_data.clear()
                        else:
                            st.error(message)
    
    except Exception as e:
        st.error(f"Error setting up edit form: {e}")

elif action == "Delete Pump":
    st.subheader("Delete Pump")
    
    try:
        # Fetch data to populate selection
        df = fetch_all_pump_data()
        
        if df.empty:
            st.info("No data found to delete.")
        else:
            # Select pump to delete
            pump_options = df["name"].tolist()
            selected_pump_name = st.selectbox("Select pump to delete:", pump_options)
            
            # Get selected pump data
            selected_pump = df[df["name"] == selected_pump_name].iloc[0]
            db_id = selected_pump["DB ID"]
            
            # Display pump details
            st.write("Pump Details:")
            details_cols = st.columns(2)
            
            with details_cols[0]:
                st.write(f"**Name:** {selected_pump['name']}")
                st.write(f"**DB ID:** {db_id}")
                
                if "manufacturer" in selected_pump:
                    st.write(f"**Manufacturer:** {selected_pump['manufacturer']}")
            
            with details_cols[1]:
                if "flow_rate" in selected_pump:
                    st.write(f"**Flow Rate:** {selected_pump['flow_rate']} LPM")
                if "head_height" in selected_pump:
                    st.write(f"**Head Height:** {selected_pump['head_height']} m")
            
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

# --- Footer ---
st.markdown("---")
st.markdown("💧 **Pump Selection Data Manager** | Last updated: " + pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"))
