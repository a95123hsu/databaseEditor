import pandas as pd
import streamlit as st
from supabase import create_client
import uuid
from datetime import datetime
import pytz

def import_csv_to_supabase(csv_file_path, supabase_client):
    """
    Import CSV data to Supabase database
    """
    try:
        # Read CSV file
        df = pd.read_csv(csv_file_path)
        
        st.write(f"Found {len(df)} records in CSV file")
        st.write("Sample of CSV data:")
        st.dataframe(df.head())
        
        # Clean and prepare data
        success_count = 0
        error_count = 0
        errors = []
        
        taiwan_tz = pytz.timezone('Asia/Taipei')
        
        # Process each row
        for index, row in df.iterrows():
            try:
                # Prepare record for Supabase
                record = {}
                
                for column in df.columns:
                    value = row[column]
                    
                    # Handle NaN values
                    if pd.isna(value):
                        record[column] = None
                    # Handle specific data type conversions
                    elif column in ["Frequency_Hz", "Phase", "Outlet (mm)", "Pass Solid Dia(mm)"]:
                        # Convert to integer
                        try:
                            record[column] = int(float(value)) if value != '' else None
                        except (ValueError, TypeError):
                            record[column] = None
                    elif column in ["Max Head (M)", "Head Rated/M", "Q Rated/LPM"]:
                        # Convert to float
                        try:
                            record[column] = float(value) if value != '' else None
                        except (ValueError, TypeError):
                            record[column] = None
                    else:
                        # Keep as string
                        record[column] = str(value) if value != '' else None
                
                # Insert into Supabase
                response = supabase_client.table("pump_selection_data").insert(record).execute()
                success_count += 1
                
                # Show progress
                if success_count % 50 == 0:
                    st.write(f"Processed {success_count} records...")
                
            except Exception as e:
                error_count += 1
                errors.append(f"Row {index + 2}: {str(e)}")  # +2 because of 0-indexing and header
                
                if len(errors) <= 10:  # Only show first 10 errors
                    st.error(f"Error in row {index + 2}: {str(e)}")
        
        # Summary
        st.success(f"Import completed!")
        st.write(f"Successfully imported: {success_count} records")
        if error_count > 0:
            st.warning(f"Errors: {error_count} records")
            if len(errors) > 10:
                st.write(f"... and {len(errors) - 10} more errors")
        
        return success_count, error_count, errors
        
    except Exception as e:
        st.error(f"Failed to import CSV: {str(e)}")
        return 0, 1, [str(e)]

def main():
    """
    Simple Streamlit app to import CSV
    """
    st.title("🚀 CSV to Supabase Importer")
    st.write("Import your pump data CSV file into Supabase database")
    
    # Supabase connection
    try:
        supabase_url = st.secrets["SUPABASE_URL"]
        supabase_key = st.secrets["SUPABASE_KEY"]
        supabase = create_client(supabase_url, supabase_key)
        st.success("✅ Connected to Supabase")
    except Exception as e:
        st.error(f"Failed to connect to Supabase: {e}")
        st.stop()
    
    # File uploader
    uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
    
    if uploaded_file is not None:
        # Save uploaded file temporarily
        csv_path = f"/tmp/uploaded_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        with open(csv_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        st.write("CSV file uploaded successfully!")
        
        # Preview data
        df_preview = pd.read_csv(csv_path)
        st.write(f"Found {len(df_preview)} rows and {len(df_preview.columns)} columns")
        
        with st.expander("Preview data"):
            st.dataframe(df_preview.head(10))
        
        # Import button
        if st.button("🚀 Start Import", type="primary"):
            with st.spinner("Importing data..."):
                success, errors, error_list = import_csv_to_supabase(csv_path, supabase)
    
    # Alternative: Use local file path
    st.markdown("---")
    st.subheader("Or import from local file path")
    
    local_path = st.text_input("Enter CSV file path:", 
                              placeholder="c:\\path\\to\\your\\pump_data.csv")
    
    if local_path and st.button("Import from local path"):
        with st.spinner("Importing data..."):
            success, errors, error_list = import_csv_to_supabase(local_path, supabase)

if __name__ == "__main__":
    main()