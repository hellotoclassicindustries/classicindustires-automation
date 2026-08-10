import streamlit as st
import pandas as pd

st.title("🔍 Lot-by-Lot Part Status Engine")
st.subheader("Granular Delivery Batch and Audit Line Items")

supabase = st.session_state.supabase
TABLE_NAME = st.secrets["TABLE_NAME"]

try:
    response = supabase.table(TABLE_NAME).select("*").execute()
    data = response.data

    if data:
        df = pd.DataFrame(data)
        
        # Isolate by Challan Number
        unique_lots = sorted(df['challan_no'].dropna().unique().tolist())
        selected_lot = st.selectbox("🎯 Target a Specific Challan No / Lot ID to Audit:", ["Show All Active Lots"] + unique_lots)

        filtered_df = df if selected_lot == "Show All Active Lots" else df[df['challan_no'] == selected_lot]
        
        # Render Targeted Breakdown Statistics
        st.markdown("---")
        st.write(f"### Registry Log View: `{selected_lot}`")
        st.dataframe(filtered_df, use_container_width=True)
    else:
        st.info("The production ledger is empty. No historical lots are active.")
except Exception as e:
    st.error(f"Lot Tracking Interrupt Error: {str(e)}")
