import streamlit as st
import pandas as pd

st.title("🗂️ Part Configuration Registry")
st.subheader("Authorized Item Master Reference List (Direct Ledger Sync)")

# Extract cached connection string components safely from runtime state
supabase = st.session_state.supabase
TABLE_NAME = st.secrets["TABLE_NAME"]

try:
    # Query your core database entries to compile a reliable list of existing part configurations
    response = supabase.table(TABLE_NAME).select("part_number, description, date").execute()
    records = response.data

    if records:
        df_ledger = pd.DataFrame(records)
        
        # Standardize strings and strip trailing whitespace anomalies
        df_ledger['part_number'] = df_ledger['part_number'].astype(str).str.strip().str.upper()
        df_ledger['description'] = df_ledger['description'].astype(str).str.strip().str.upper()
        df_ledger['date'] = pd.to_datetime(df_ledger['date'], errors='coerce')
        
        # Isolate the single latest description entry for each unique part profile
        registry = df_ledger.sort_values('date').groupby('part_number').agg({
            'description': 'last',
            'date': 'max'
        }).reset_index()
        
        # Rename display column headers to look uniform and professional
        registry.columns = ['Part Number Code', 'Registered Specification / Description', 'Last Seen Active Date']
        registry['Last Seen Active Date'] = registry['Last Seen Active Date'].dt.strftime('%Y-%m-%d').fillna("N/A")

        # Interactive user layout search field
        search_query = st.text_input("🔍 Search Active Inventory Catalogue by Part Code:", "").strip().upper()
        if search_query:
            registry = registry[registry['Part Number Code'].str.contains(search_query, na=False)]

        st.markdown("---")
        st.write(f"Showing **{len(registry)} Distinct Component Layouts** compiled directly from warehouse activity rows.")
        st.dataframe(registry, use_container_width=True, hide_index=True)
    else:
        st.warning("Connected to database safely, but the ledger layout returned no transaction history records to pull details from.")
except Exception as e:
    st.error(f"Failed to query active item catalogue profiles: {str(e)}")
