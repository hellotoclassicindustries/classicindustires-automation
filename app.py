import streamlit as st

# ============================================================================
# 1. INITIALIZE PROJECT CONFIGURATION & APP STATE PROFILE
# ============================================================================
st.set_page_config(
    page_title="Classic Industries Portal",
    page_icon="🏭",
    layout="wide"
)

# Initialize background authentication session states
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

# ============================================================================
# 2. RENDER USER AUTHENTICATION SCREEN FOR UNVERIFIED CONSOLES
# ============================================================================
def render_login_screen():
    """Renders a locked login gate panel matching your exact workspace layout."""
    st.title("🔒 Classic Industries Plant Operations Login")
    st.markdown("---")
    
    col_l1, col_l2, col_l3 = st.columns([1, 2, 1])
    
    with col_l2:
        st.markdown(
            "<div style='background-color: #f8f9fa; padding: 25px; border-radius: 8px; border-left: 5px solid #c00000;'>"
            "<h3 style='margin-top:0;'>Restricted Access Administration Panel</h3>"
            "Please provide valid administrative credentials to unlock floor management modules."
            "</div>", 
            unsafe_allow_html=True
        )
        st.markdown("<br>", unsafe_allow_html=True)
        
        user_input = st.text_input("Username:", key="auth_user")
        pass_input = st.text_input("Password:", type="password", key="auth_pass")
        
        if st.button("Unlock Secure Sheets & Simulators", use_container_width=True):
            # Extract variables dynamically from your Streamlit Cloud Secrets TOML container
            expected_user = st.secrets["DASHBOARD_USER"]
            expected_pass = st.secrets["DASHBOARD_PASS"]
            
            if user_input == expected_user and pass_input == expected_pass:
                st.session_state["authenticated"] = True
                st.success("✅ Credentials Verified! Unlocking system layout...")
                st.rerun()
            else:
                st.error("❌ Invalid Username or Password string. Access Denied.")

# ============================================================================
# 3. CORE MULTI-PAGE NAVIGATION ROUTER LAYOUT
# ============================================================================
# Define ALL available site views using st.Page objects
page_home = st.Page("views/1_About_Us.py", title="Classic Industries Home", icon="🏢")
page_stock = st.Page("views/2_Stock_Master.py", title="Stock Master Dashboard", icon="📊")
page_ledger = st.Page("views/3_Daily_Ledger.py", title="Daily Transaction Register", icon="📝")
page_forecast = st.Page("views/5_Forecast_Simulation.py", title="Forecast Simulation View", icon="🔮")
page_guide = st.Page("views/4_System_Guide.py", title="System User Guide", icon="📘")

# 🧠 THE STRATEGY FIX: Dynamically re-map the menu list depending on the state
if not st.session_state["authenticated"]:
    # If the console is locked, register an isolated page mapping so st.navigation can run smoothly
    pg = st.navigation([st.Page(render_login_screen, title="System Authorization Gate", icon="🔒")])
else:
    # If user successfully authenticates, populate your full plant operations links list
    pg = st.navigation({
        "Plant Management Menu": [page_home, page_stock, page_ledger, page_forecast, page_guide]
    })

# Run the navigation engine seamlessly with zero left-hand side assignment errors!
pg.run()
