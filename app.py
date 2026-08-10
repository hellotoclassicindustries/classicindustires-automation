import streamlit as st
import pandas as pd
from supabase import create_client, Client

# Set wide page layout to handle multi-column tables cleanly
st.set_page_config(page_title="Classic Industries — Ledger Dashboard", layout="wide")

# Fetch operational credentials securely from Streamlit Secrets Manager
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
TABLE_NAME = st.secrets["TABLE_NAME"]

# Initialize and cache our official connection layout
@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = init_supabase()

st.title("🏭 Classic Industries — Staging Ledger")
st.subheader("Live Operational Monitoring Engine")

try:
    # 1. Fetch live production logs from the backend database node
    response = supabase.table(TABLE_NAME).select("*").execute()
    raw_data = response.data

    if raw_data:
        # 2. Parse payload arrays into a clean Pandas dataframe structure
        df = pd.DataFrame(raw_data)
        
        # Standardize numeric types and text formatting safely
        df['qty_nos'] = pd.to_numeric(df['qty_nos'], errors='coerce').fillna(0).astype(int)
        df['entry_type'] = df['entry_type'].astype(str).str.strip()
        
        # 3. Dynamic Aggregation Engine Metrics 
        inward_total = int(df[df['entry_type'].str.lower() == 'inward']['qty_nos'].sum())
        outward_total = int(df[df['entry_type'].str.lower() == 'outward']['qty_nos'].sum())
        wip_balance = inward_total - outward_total
        
        # 4. Render Live Summary Metric Display Blocks
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(label="Total Items Received (Inward)", value=f"{inward_total:,} Pcs")
        with col2:
            st.metric(label="Total Items Returned (Outward)", value=f"{outward_total:,} Pcs")
        with col3:
            st.metric(
                label="Current Shop Floor Balance (WIP)", 
                value=f"{wip_balance:,} Pcs",
                delta=f"{wip_balance} Net Remaining",
                delta_color="normal" if wip_balance >= 0 else "inverse"
            )
            
        st.markdown("---")
        
        # 5. Native Interface Controls
        tab1, tab2 = st.tabs(["🔍 Comprehensive Database Row Register", "📊 Quick Filter & Export Toolkit"])
        
        with tab1:
            st.write("### Live Transaction Tracking Registry")
            st.dataframe(df, use_container_width=True)
            
        with tab2:
            st.write("### Operational Filter Controls")
            
            # Filter rows dynamically on screen by unique item part configuration rows
            unique_parts = sorted(df['part_number'].dropna().unique().tolist())
            selected_part = st.selectbox("Isolate Register Rows by Part Number:", ["All Active Parts"] + unique_parts)
            
            filtered_df = df if selected_part == "All Active Parts" else df[df['part_number'] == selected_part]
            
            if selected_part != "All Active Parts":
                st.write(f"Showing localized rows for Part Config: `{selected_part}`")
                st.dataframe(filtered_df, use_container_width=True)
            
            # Instant CSV Download Action Block
            csv_data = filtered_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Export Filtered Sheet View to CSV File",
                data=csv_data,
                file_name="classic_industries_filtered_ledger.csv",
                mime="text/csv"
            )
    else:
        st.info("Connected to database successfully. Table 'staging_ledger' contains no active transaction records.")

except Exception as e:
    st.error(f"❌ Direct Database Tracking Interrupted: {str(e)}")
