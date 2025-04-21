import streamlit as st
import extra_streamlit_components as stx
from supabase import create_client

@st.cache_resource
def get_client():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

# CookieManager must only be initialized ONCE
cookie_manager = stx.CookieManager(key="auth_cookie")

def login_form():
    cookie = cookie_manager.get("supabase_session")
    
    with st.form("login_form"):
        st.subheader("🔐 Login to continue")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

        if submitted:
            if not email or not password:
                st.error("Please enter both email and password.")
                return

            supabase = get_client()
            try:
                result = supabase.auth.sign_in_with_password({
                    "email": email,
                    "password": password
                })
                if result.session:
                    # Set session token in cookie
                    cookie_manager.set("supabase_session", result.session.access_token, max_age=3600)
                    st.success("Login successful! Refreshing...")
                    st.experimental_rerun()  # rerun AFTER cookie is set
                else:
                    st.error("Login failed. Check your credentials.")
            except Exception as e:
                st.error("Authentication error.")
                st.exception(e)

def get_user_session():
    token = cookie_manager.get("supabase_session")
    if token and token.get("supabase_session"):
        try:
            supabase = get_client()
            user = supabase.auth.get_user(token["supabase_session"])
            return user.user
        except:
            return None
    return None

def logout():
    cookie_manager.delete("supabase_session")
    st.success("Logged out!")
    st.experimental_rerun()
