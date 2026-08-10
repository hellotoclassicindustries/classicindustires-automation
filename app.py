import streamlit as st
import pandas as pd
import altair as alt
import requests

# Initialize wide page layout for investor presentation
st.set_page_config(page_title="Classic Industries | Production Portal", layout="wide")

# ==========================================
# UNIVERSAL IPv4 HTTP REST API DATA INGESTOR
# ==========================================
SUPABASE_BASE_URL = "https://bvxhuhjpdfsbtiaxjfph.supabase.co"
SUPABASE_KEY = "sb_publishable_wA5y_LaH1Z8ZZsD564jZ4w_4QAwPolu"
SUPABASE_REST_URL = f"{SUPABASE_BASE_URL}/rest/v1/staging_ledger"

@st.cache_data(ttl=2)  # Fast 2-second cache refresh loop for live data tracking
def load_database_via_http():
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.get(SUPABASE_REST_URL, headers=headers, timeout=10)
        if response.status_code == 200:
            return pd.DataFrame(response.json())
        else:
            st.error(f"Cloud REST API returned an error status: {response.status_code}")
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Network proxy transmission timeout. Trace: {str(e)}")
        return pd.DataFrame()

df_ledger = load_database_via_http()

# ==========================================
# EXECUTIVE METRICS BAR
# ==========================================
st.title("🏭 Classic Industries × REVENT Production Portal")
st.subheader("Live Operational Tracking, Employee Allocation & Job Progress Engine")
st.markdown("---")

if not df_ledger.empty:
    df_ledger.columns = [str(col).strip().lower() for col in df_ledger.columns]
    
    inward_vol = df_ledger[df_ledger['entry_type'].astype(str).str.lower() == 'inward']['qty_nos'].sum()
    outward_vol = df_ledger[df_ledger['entry_type'].astype(str).str.lower() == 'outward']['qty_nos'].sum()
else:
    inward_vol, outward_vol = 0, 0

wip_floor_balance = inward_vol - outward_vol

m1, m2, m3 = st.columns(3)
with m1:
    st.metric("Total Items Received (Inward)", f"{int(inward_vol):,} Pcs")
with m2:
    st.metric("Total Items Returned (Outward)", f"{int(outward_vol):,} Pcs")
with m3:
    st.metric("Current Shop Floor Balance (WIP)", f"{int(wip_floor_balance):,} Pcs", delta_color="inverse")

st.markdown("---")

# ==========================================
# CONTROL SYSTEM TAB INTERFACE
# ==========================================
tab_inv, tab_audit = st.tabs(["📊 Inventory Balance Summary", "🔍 Comprehensive Lot Audit Register"])

with tab_inv:
    st.header("📊 Current Stock Balance by Component Node")
    
    if not df_ledger.empty and (inward_vol > 0 or outward_vol > 0):
        in_grp = df_ledger[df_ledger['entry_type'].astype(str).str.lower() == 'inward'].groupby('part_number')['qty_nos'].sum().reset_index(name='Inward')
        out_grp = df_ledger[df_ledger['entry_type'].astype(str).str.lower() == 'outward'].groupby('part_number')['qty_nos'].sum().reset_index(name='Outward')
        bal_df = pd.merge(in_grp, out_grp, on='part_number', how='outer').fillna(0)
        bal_df['Current Stock'] = bal_df['Inward'] - bal_df['Outward']
        
        inv_chart = alt.Chart(bal_df).mark_bar(color='#17becf').encode(
            x=alt.X('Current Stock:Q', title='Quantity on Floor (Nos)'),
            y=alt.Y('part_number:N', sort='-x', title='Part Number'),
            tooltip=['part_number', 'Current Stock']
        ).properties(height=300)
        st.altair_chart(inv_chart, use_container_width=True)
        
        st.dataframe(
            bal_df[['part_number', 'Inward', 'Outward', 'Current Stock']].rename(columns={
                'part_number': 'Part Number', 'Inward': 'Total Inward', 'Outward': 'Total Outward', 'Current Stock': 'Current Stock'
            }).sort_values(by='Current Stock', ascending=False),
            use_container_width=True, hide_index=True
        )
    else:
        st.info("The production metrics matrix has a net zero balance. Sync rows from your Google Sheet to stream statistics.")

with tab_audit:
    st.header("🔍 Comprehensive Database Row Register")
    if not df_ledger.empty:
        st.dataframe(df_ledger.astype(str), use_container_width=True, hide_index=True)
    else:
        st.info("No transaction tracking rows available inside the cloud table view.")

