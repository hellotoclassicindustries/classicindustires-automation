import streamlit as st
import pandas as pd

st.title("📝 Daily Transaction Register")
st.subheader("Chronological Cloud Ledger Audit Log View")

# Access the cached database connection from session state
supabase = st.session_state.supabase
TABLE_NAME = st.secrets["TABLE_NAME"]

try:
    # 1. Fetch entire transactional database rows
    response = supabase.table(TABLE_NAME).select("*").execute()
    records = response.data

    if records:
        df_ledger = pd.DataFrame(records)
        
        # Standardize text and case styles across critical lookup variables
        df_ledger['part_number'] = df_ledger['part_number'].astype(str).str.strip().str.upper()
        df_ledger['challan_no'] = df_ledger['challan_no'].astype(str).str.strip().str.upper()
        df_ledger['entry_type'] = df_ledger['entry_type'].astype(str).str.strip()
        df_ledger['qty_nos'] = pd.to_numeric(df_ledger['qty_nos'], errors='coerce').fillna(0).astype(int)
        
        # Sort values chronologically with the newest logs pinned directly to row #1
        if 'date' in df_ledger.columns:
            df_ledger['date'] = pd.to_datetime(df_ledger['date'], errors='coerce')
            df_ledger = df_ledger.sort_values(by='date', ascending=False)
            df_ledger['date'] = df_ledger['date'].dt.strftime('%Y-%m-%d').fillna("N/A")

        # 2. Interactive Multi-Column Search Filters
        col1, col2 = st.columns(2)
        with col1:
            search_part = st.text_input("🔍 Filter Register Rows by Part Code:", "").strip().upper()
        with col2:
            search_challan = st.text_input("📦 Filter Register Rows by Challan Identifier:", "").strip().upper()
            
        if search_part:
            df_ledger = df_ledger[df_ledger['part_number'].str.contains(search_part, na=False)]
        if search_challan:
            df_ledger = df_ledger[df_ledger['challan_no'].str.contains(search_challan, na=False)]

        st.markdown("---")
        st.write(f"Showing **{len(df_ledger)} Synchronized Production Lines** saved in the cloud table matrix.")
        
        # 3. Prioritize column grid display order matching blueprint fields exactly
        display_cols = ['date', 'entry_type', 'challan_no', 'part_number', 'qty_nos', 'vehicle_no', 'gross_total', 'hsn_code']
        existing_cols = [c for c in display_cols if c in df_ledger.columns]
        
        # Output polished data frame layout
        st.dataframe(df_ledger[existing_cols], use_container_width=True, hide_index=True)
        
        # 4. Clean CSV Spreadsheet Data Export Action Panel
        csv_data = df_ledger[existing_cols].to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Export Tabular Registry View to CSV Spreadsheet",
            data=csv_data,
            file_name="foundry_friends_daily_register.csv",
            mime="text/csv"
        )
    else:
        st.warning("Connected to database safely, but the ledger layout returned no transaction history records.")
except Exception as e:
    st.error(f"Failed to query active item catalogue profiles: {str(e)}")
