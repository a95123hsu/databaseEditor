import streamlit as st
from supabase import create_client, Client
import pandas as pd

# Load credentials securely
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

@st.cache_resource
def init_connection():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = init_connection()

# --- Login System ---
def login_user(email, password):
    try:
        result = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        return result.user is not None, result
    except Exception as e:
        return False, str(e)

# Session state for login
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 Supabase Login")

    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        success, result = login_user(email, password)
        if success:
            st.session_state.logged_in = True
            st.session_state.user = result.user
            st.success("Login successful!")
            st.experimental_rerun()
        else:
            st.error(f"Login failed: {result}")
else:
    st.title("📊 Supabase Table Editor")

    table_name = "my_table"  # Replace with your table name

    try:
        data = supabase.table(table_name).select("*").execute()
        df = pd.DataFrame(data.data)

        st.subheader("Table Data")
        edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

        if st.button("Update Table"):
            for row in edited_df.to_dict("records"):
                row_id = row.get("id")  # Ensure your table has an 'id' column
                if row_id:
                    supabase.table(table_name).update(row).eq("id", row_id).execute()
            st.success("Table updated!")

    except Exception as e:
        st.error(f"Error fetching or updating data: {e}")

    if st.button("Logout"):
        st.session_state.logged_in = False
        st.experimental_rerun()
