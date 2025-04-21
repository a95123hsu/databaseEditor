import streamlit as st
import pandas as pd
from supabase import create_client
import re
import traceback
import time
from datetime import datetime, timedelta
import extra_streamlit_components as stx

# --- Page Configuration ---
st.set_page_config(
    page_title="Pump Selection Data Manager", 
    page_icon="💧", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Cookie Manager ---
def get_cookie_manager():
    return stx.CookieManager()

cookie_manager = get_cookie_manager()

# --- Initialize Session Variables ---
def initialize_auth_session():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user_info" not in st.session_state:
        st.session_state.user_info = None
    if "auth_token" not in st.session_state:
        st.session_state.auth_token = None

initialize_auth_session()

# --- Authentication Functions ---
def login(email, password):
    try:
        supabase_url = st.secrets["SUPABASE_URL"]
        supabase_key = st.secrets["SUPABASE_KEY"]
        supabase_client = create_client(supabase_url, supabase_key)
        auth_response = supabase_client.auth.sign_in_with_password({"email": email, "password": password})
        
        st.session_state.authenticated = True
        st.session_state.user_info = auth_response.user
        st.session_state.auth_token = auth_response.session.access_token
        
        expires = (datetime.now() + timedelta(hours=1)).timestamp()
        cookie_manager.set("auth_token", auth_response.session.access_token, expires=expires)
        
        return True, "Login successful"
    except Exception as e:
        return False, f"Login failed: {str(e)}"

def logout():
    st.session_state.authenticated = False
    st.session_state.user_info = None
    st.session_state.auth_token = None
    cookie_manager.delete("auth_token")
    st.rerun()

def check_auth():
    if st.session_state.authenticated and st.session_state.auth_token:
        return True
    
    auth_token = cookie_manager.get("auth_token")
    if auth_token:
        try:
            supabase_url = st.secrets["SUPABASE_URL"]
            supabase_key = st.secrets["SUPABASE_KEY"]
            supabase_client = create_client(supabase_url, supabase_key)
            user = supabase_client.auth.get_user(auth_token)
            
            st.session_state.authenticated = True
            st.session_state.user_info = user.user
            st.session_state.auth_token = auth_token
            
            return True
        except:
            cookie_manager.delete("auth_token")
            return False
    return False

# --- Show Login Page If Not Authenticated ---
if not check_auth():
    st.title("🔐 Login to Pump Selection Data Manager")
    email = st.text_input("Email", placeholder="Enter your email")
    password = st.text_input("Password", type="password", placeholder="Enter your password")
    login_btn = st.button("Login")

    if login_btn:
        success, message = login(email, password)
        if success:
            st.success(message)
            time.sleep(1)
            st.rerun()
        else:
            st.error(message)
    st.stop()

# --- Show Logged In User Info + Logout ---
with st.sidebar:
    if st.session_state.user_info:
        st.markdown(f"**Logged in as:** {st.session_state.user_info.email}")
        if st.button("Logout"):
            logout()

# --- Initialize Supabase Client After Login ---
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

# --- Now continue with your app logic here ---
# For example:
st.title("💧 Pump Selection Data Manager")
st.write("Welcome! You are now logged in and can access the pump database.")

# --- You can now safely fetch, view, add, edit, and delete data ---
# Load your `fetch_all_pump_data()` and related CRUD functions here...
# You can paste your previous full app logic below this comment.
