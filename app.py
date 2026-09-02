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

# Initialize localized login state variables 
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# Define Your Multi-Page Layout Structure (🚀 ADDED: Forecast Simulation Page)
about_page = st.Page("views/1_About_Us.py", title="Classic Industries Home", icon="🏢", default=True)
stock_page = st.Page("views/2_Stock_Master.py", title="Stock Master Dashboard", icon="📊")
ledger_page = st.Page("views/3_Daily_Ledger.py", title="Daily Transaction Register", icon="📝")
forecast_page = st.Page("views/5_Forecast_Simulation.py", title="Forecast Simulation View", icon="🔮")
guide_page = st.Page("views/4_System_Guide.py", title="System User Guide", icon="📘")

# TRUTH PATTERN: Register all pages cleanly in the navigation loop
pages = [about_page, stock_page, ledger_page, forecast_page, guide_page]

# Run Core Navigation Controller
pg = st.navigation(pages)

# Inject a clean sidebar lock/unlock toggle switch container
with st.sidebar:
    st.markdown("---")
    if st.session_state.authenticated:
        st.success("🔒 Authenticated Session Active")
        if st.button("Log Out of Terminal"):
            st.session_state.authenticated = False
            st.rerun()
    else:
        st.warning("🔑 Restricted Access Panel")
        with st.form("Internal Personnel Authentication Log"):
            input_user = st.text_input("Username:")
            input_pass = st.text_input("Password:", type="password")
            submit_login = st.form_submit_button("Unlock Secure Sheets")
            
            if submit_login:
                # 🚀 THE FIX: Force inputs to lower-case and strip out blank spaces instantly
                clean_input_user = str(input_user).strip().lower()
                clean_input_pass = str(input_pass).strip()
                
                clean_expected_user = str(st.secrets["DASHBOARD_USER"]).strip().lower()
                clean_expected_pass = str(st.secrets["DASHBOARD_PASS"]).strip()
                
                if clean_input_user == clean_expected_user and clean_input_pass == clean_expected_pass:
                    st.session_state.authenticated = True
                    st.success("Access Granted!")
                    st.rerun()
                else:
                    st.error("Invalid corporate credentials.")

# 🔒 RECONCILIATION GATEKEEPER: Added forecast_page to the secure gate group
if not st.session_state.authenticated and pg in [stock_page, ledger_page, forecast_page, guide_page]:
    st.title("🔒 Restricted Corporate Node")
    st.error("Access Denied. This terminal view contains confidential operational ledger values.")
    st.info("💡 Please look at the lower left section of your sidebar menu and input your authorized staff password credentials to unlock this view node.")
else:
    # Run the requested page normally
    pg.run()
