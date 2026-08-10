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
        
        # Clean text components 
        df['part_number'] = df['part_number'].astype(str).str.strip().str.upper()
        df['challan_no'] = df['challan_no'].astype(str).str.strip().str.upper()
        df['entry_type'] = df['entry_type'].astype(str).str.strip()

        # Isolate by Unique Part Number to narrow things down quickly
        unique_parts = sorted(df['part_number'].dropna().unique().tolist())
        selected_part = st.selectbox("🎯 Isolate Ledger Rows by Unique Part Code Layout:", ["Show All Managed Parts"] + unique_parts)
        
        # Isolate by Unique Challan Number
        unique_lots = sorted(df['challan_no'].dropna().unique().tolist())
        selected_lot = st.selectbox("📦 Filter Specific Delivery Challan No / Lot ID:", ["Show All Active Transaction Lots"] + unique_lots)

        # Apply filtering strings based on dashboard selections
        filtered_df = df
        if selected_part != "Show All Managed Parts":
            filtered_df = filtered_df[filtered_df['part_number'] == selected_part]
        if selected_lot != "Show All Active Transaction Lots":
            filtered_df = filtered_df[filtered_df['challan_no'] == selected_lot]
        
        st.markdown("---")
        st.write(f"### Historical Transaction Audit Trail Matrix ({len(filtered_df)} Rows Located)")
        
        # Arrange column order so reading looks natural
        display_cols = ['date', 'entry_type', 'challan_no', 'part_number', 'qty_nos', 'vehicle_no', 'gross_total', 'hsn_code']
        existing_display_cols = [c for c in display_cols if c in filtered_df.columns]
        
        st.dataframe(filtered_df[existing_display_cols], use_container_width=True, hide_index=True)
    else:
        st.info("The production ledger is empty. No operational historical lots have been registered yet.")
except Exception as e:
    st.error(f"Lot Tracking Audit Interrupt Error: {str(e)}")
