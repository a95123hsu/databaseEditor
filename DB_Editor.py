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

# --- Page Configuration ---
st.set_page_config(
    page_title="Pump Selection Data", 
    page_icon="💧", 
    layout="wide"
)

# --- App Header ---
st.title("💧 Pump Selection Data Viewer")
st.markdown("View and analyze your complete pump selection dataset")

# --- Initialize Supabase Client ---
supabase = init_connection()

# --- Main Content ---
try:
    # Add a refresh button
    if st.button("🔄 Refresh Data"):
        st.experimental_rerun()
    
    # Fetch all data with pagination
    df = fetch_all_pump_data()
    
    if df.empty:
        st.info("No data found in 'pump_selection_data'.")
    else:
        # Display data info
        st.success(f"✅ Successfully loaded {len(df)} pump records")
        
        # Create tabs for different views
        tab1, tab2 = st.tabs(["Data Table", "Summary View"])
        
        with tab1:
            # Add search functionality
            search_term = st.text_input("🔍 Search by pump name:")
            
            if search_term:
                filtered_df = df[df["name"].str.contains(search_term, case=False, na=False)]
                st.write(f"Found {len(filtered_df)} matching pumps")
            else:
                filtered_df = df
            
            # Data Table with pagination controls
            st.subheader("📋 Raw Data Table")
            
            # Add sorting options
            if not filtered_df.empty:
                # Use DB ID as the default sort column, then offer other columns
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
        
        with tab2:
            # Summary View
            st.subheader("🔍 Pump Summary")
            
            # Add manufacturer filter if available
            if "manufacturer" in df.columns:
                manufacturers = sorted(df["manufacturer"].dropna().unique())
                selected_manufacturer = st.selectbox("Filter by manufacturer:", ["All"] + list(manufacturers))
                
                if selected_manufacturer != "All":
                    summary_df = df[df["manufacturer"] == selected_manufacturer]
                else:
                    summary_df = df
            else:
                summary_df = df
            
            # Limit number of cards shown
            max_cards = st.slider("Number of pumps to display:", 5, 50, 10)
            
            # Display summary cards for each pump
            for index, row in summary_df.head(max_cards).iterrows():
                name = row.get("name", f"Pump #{index}")
                flow = row.get("flow_rate", "N/A")
                head = row.get("head_height", "N/A")
                
                with st.expander(f"{name}"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown(f"- **Flow Rate:** {flow} LPM")
                        st.markdown(f"- **Head Height:** {head} m")
                    
                    with col2:
                        # Display additional fields
                        for col in df.columns:
                            if col not in ["name", "flow_rate", "head_height"] and pd.notna(row.get(col)):
                                st.markdown(f"- **{col.replace('_', ' ').title()}:** {row.get(col)}")
            
            if len(summary_df) > max_cards:
                st.info(f"Showing {max_cards} out of {len(summary_df)} pumps. Adjust the slider to see more.")
        
except Exception as e:
    st.error(f"Error fetching data: {e}")
    st.info("Please check your connection to Supabase.")
    
# --- Footer ---
st.markdown("---")
st.markdown("💧 **Pump Selection Data Viewer** | Last updated: " + pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"))
