import streamlit as st
import pandas as pd
from supabase import create_client, Client

# --- Load Supabase credentials from Streamlit secrets ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

# --- Initialize Supabase connection ---
@st.cache_resource
def init_connection():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = init_connection()

# --- Authentication functions ---
def sign_up_user(email, password):
    try:
        supabase.auth.sign_up({"email": email, "password": password})
        return True, "Signup successful. Check your email to confirm."
    except Exception as e:
        return False, str(e)

def login_user(email, password):
    try:
        result = supabase.auth.sign_in_with_password({"email": email, "password": password})
        return True, result
    except Exception as e:
        return False, str(e)

# --- Session setup ---
if "session" not in st.session_state:
    st.session_state.session = None
if "user" not in st.session_state:
    st.session_state.user = None

# --- Login/Signup screen ---
if st.session_state.session is None:
    st.title("🔐 Supabase Login")

    tab1, tab2 = st.tabs(["Login", "Sign Up"])

    with tab1:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Login"):
            success, result = login_user(email, password)
            if success:
                st.session_state.session = result.session
                st.session_state.user = result.user
                st.success("Login successful!")
                st.rerun()
            else:
                st.error(f"Login failed: {result}")

    with tab2:
        email = st.text_input("Email", key="signup_email")
        password = st.text_input("Password", type="password", key="signup_password")
        if st.button("Sign Up"):
            success, msg = sign_up_user(email, password)
            if success:
                st.success(msg)
            else:
                st.error(f"Sign up failed: {msg}")

# --- Main App Content ---
else:
    st.title("🧠 Pump Selection Data Editor")

    # ✅ Replace with your actual table name, exactly as it appears in Supabase (case-sensitive)
    table_name = '"Pump_Selection_Data"'  # Example: quoted to support case-sensitive table names

    try:
        data = supabase.table(table_name).select("*").execute()
        df = pd.DataFrame(data.data)

        if df.empty:
            st.info("No data found in the table.")
        else:
            st.subheader("Edit Pump Selection Data")
            st.write("💡 Click on cells to edit, then press Update below.")
            edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

            if st.button("Update Table"):
                for row in edited_df.to_dict("records"):
                    row_id = row.get("id")
                    if row_id:
                        supabase.table(table_name).update(row).eq("id", row_id).execute()
                st.success("Table updated!")

    except Exception as e:
        st.error(f"Error accessing Supabase table: {e}")

    if st.button("Logout"):
        st.session_state.session = None
        st.session_state.user = None
        st.rerun()
