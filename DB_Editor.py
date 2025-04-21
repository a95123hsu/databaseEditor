import streamlit as st
from st_supabase_connection import SupabaseConnection

st.set_page_config(page_title="🐾 Pet Viewer", layout="centered")

# Title
st.title("🐾 Pet Owners Viewer")

# Connect to Supabase
conn = st.connection("supabase", type=SupabaseConnection)

# Query data from your Supabase table
try:
    rows = conn.query("*", table="mytable", ttl="10m").execute()
    data = rows.data

    if not data:
        st.info("No data found in 'mytable'. Add some rows in Supabase.")
    else:
        st.subheader("📋 Raw Table Data")
        st.dataframe(data, use_container_width=True)

        st.subheader("🎉 Fun Format")
        for row in data:
            name = row.get("name", "Unknown")
            pet = row.get("pet", "🐾")
            st.write(f"**{name}** has a :{pet}:")
except Exception as e:
    st.error(f"Error fetching data: {e}")
