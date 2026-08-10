import streamlit as st
from supabase import create_client, Client

# Set wide page layout to handle multi-column tables cleanly
st.set_page_config(page_title="Classic Industries Portal", layout="wide", page_icon="🏭")

# Initialize and Cache Supabase Engine Network Stack
@st.cache_resource
def init_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

if "supabase" not in st.session_state:
    st.session_state.supabase = init_supabase()

# FIXED: Re-mapped paths to point to 'views/' to terminate the background duplicator bug
pages = [
    st.Page("views/1_About_Us.py", title="Classic Industries Home", icon="🏢", default=True),
    st.Page("views/2_Stock_Master.py", title="Stock Master Dashboard", icon="📊"),
    st.Page("views/3_Daily_Ledger.py", title="Daily Transaction Register", icon="📝"),
    st.Page("views/4_System_Guide.py", title="System User Guide", icon="📘")
]

# Run Core Navigation Controller
pg = st.navigation(pages)
pg.run()
