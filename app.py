import streamlit as st
from supabase import create_client, Client

# Page layout configuration
st.set_page_config(page_title="Classic Industries Dashboard", layout="wide")

# Fetch production credentials securely from Streamlit Secret Container
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
TABLE_NAME = st.secrets["TABLE_NAME"]

# Initialize and cache official Supabase client
@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = init_supabase()

st.title("🏭 Classic Industries — Production Sync")
st.subheader("Database Schema and Sync Validation Panel")

try:
    # Query ALL columns using a wildcard (*) to locate the 22 rows
    response = supabase.table(TABLE_NAME).select("*").execute()
    data = response.data
    
    # Core operational metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="Total Database Rows Located", value=f"{len(data)} Rows")
    with col2:
        st.metric(label="Targeted Supabase Node", value=TABLE_NAME)
    with col3:
        st.metric(label="Cloud Connection Link", value="Direct (Secure API)")
        
    st.markdown("---")
    
    # Tabular UI Controller
    tab1, tab2 = st.tabs(["📊 Live Database Inspect Engine", "📝 Blueprint Metadata Context"])
    
    with tab1:
        if data:
            st.success("🎉 Data streaming successfully! Check the column headers below to fix the calculations:")
            st.dataframe(data, use_container_width=True)
        else:
            st.warning(f"Connected to Supabase securely, but table '{TABLE_NAME}' appears to be empty.")
            st.info("Ensure your Google Sheet pipeline is currently pushing to the correct target project.")
            
    with tab2:
        st.info("These are your active blueprint parameters stored in Advanced Settings Secrets:")
        st.markdown(f"""
        * **Project Endpoint:** `{SUPABASE_URL}`
        * **Table Node Name:** `{TABLE_NAME}`
        * **Expected Infrastructure Elements:** `date`, `entry_type`, `challan_no`, `part_number`, `qty_nos`, `vehicle_no`, `gross_total`, `hsn_code`
        """)

except Exception as e:
    st.error(f"❌ Direct Database Tracking Interrupted: {str(e)}")
    st.markdown("""
    **Troubleshooting Steps:**
    1. Verify your credentials in **Advanced Settings -> Secrets** are exactly correct.
    2. Ensure your Supabase database allows public tracking requests on the targeted table node.
    """)
