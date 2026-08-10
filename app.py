import streamlit as st
from supabase import create_client, Client

st.set_page_config(page_title="Classic Industries Operations", layout="wide", page_icon="🏭")

# Initialize and Cache Supabase Engine
@st.cache_resource
def init_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

if "supabase" not in st.session_state:
    st.session_state.supabase = init_supabase()

# Declare Multi-Page Configuration Blueprint
pages = [
    st.Page("pages/1_Stock_Master.py", title="Stock Master Dashboard", icon="📊", default=True),
    st.Page("pages/2_Item_Master.py", title="Item Master Registry", icon="🗂️"),
    st.Page("pages/3_Lot_Status.py", title="Lot-by-Lot Part Status", icon="🔍")
]

# Run Core Navigation Controller
pg = st.navigation(pages)
pg.run()
