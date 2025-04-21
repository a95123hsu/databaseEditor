def insert_pump_data(pump_data):
    try:
        # Create a copy of the data for safe modification
        clean_data = {}
        
        # First, get the maximum DB ID to generate a new one
        try:
            max_id_response = supabase.table("pump_selection_data").select("DB ID").order("DB ID", desc=True).limit(1).execute()
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
        import traceback
        st.error(traceback.format_exc())
        return False, f"Error adding pump data: {e}"
