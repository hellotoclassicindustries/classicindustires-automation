import streamlit as st
from supabase import create_client, Client

st.set_page_config(page_title="Foundry Friends Portal", layout="wide", page_icon="🏭")

# Initialize and Cache Supabase Engine Network Stack
@st.cache_resource
def init_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

if "supabase" not in st.session_state:
    st.session_state.supabase = init_supabase()

# Declare Revised Clean Multi-Page Architecture Blueprint
pages = [
    st.Page("pages/1_About_Us.py", title="Foundry Friends Home", icon="🏢", default=True),
    st.Page("pages/2_Stock_Master.py", title="Stock Master Dashboard", icon="📊"),
    st.Page("pages/3_Daily_Ledger.py", title="Daily Transaction Register", icon="📝")
]

# Run Core Navigation Controller
pg = st.navigation(pages)
pg.run()
