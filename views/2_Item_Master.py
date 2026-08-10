import streamlit as st
import pandas as pd

st.title("🗂️ Part Configuration Registry")
st.subheader("Authorized Item Master Reference List (Direct Ledger Sync)")

# Extract cached connection string components safely from runtime state
supabase = st.session_state.supabase
TABLE_NAME = st.secrets["TABLE_NAME"]

try:
    # 1. Query the primary transaction columns including the description and target parameters
    response = supabase.table(TABLE_NAME).select("part_number, description, date").execute()
    records = response.data

    if records:
        df_ledger = pd.DataFrame(records)
        
        # Standardize string entries and strip trailing whitespace anomalies
        df_ledger['part_number'] = df_ledger['part_number'].astype(str).str.strip().str.upper()
        df_ledger['description'] = df_ledger['description'].astype(str).str.strip().str.upper()
        df_ledger['date'] = pd.to_datetime(df_ledger['date'], errors='coerce')
        
        # 2. Extract the newest text configuration available for each individual part number
        registry = df_ledger.sort_values('date').groupby('part_number').agg({
            'description': 'last',
            'date': 'max'
        }).reset_index()

        # 3. AUTOMATED STRUCTURAL Fallback Weight Extraction Engine
        # This scans description metadata text structures to locate assigned piece weights dynamically.
        # If no numeric pattern matches, it logs a clean fallback status.
        def extract_embedded_weight(text):
            import re
            cleaned_text = str(text).upper()
            # Match standard patterns like: "12.5 KG", "0.450KG", "8KG", "500G"
            weight_match = re.search(r'(\d+(?:\.\d+)?)\s*(KG|G|KILOGRAM|GRAM)', cleaned_text)
            if weight_match:
                value, unit = weight_match.groups()
                return f"{value} {unit}"
            return "Pending Verification"

        registry['Calculated Component Weight'] = registry['description'].apply(extract_embedded_weight)
        
        # Rename display column headers to look uniform and professional
        registry.columns = [
            'Part Number Code', 
            'Registered Specification / Description', 
            'Last Seen Active Date',
            'Component Weight Profiling'
        ]
        
        registry['Last Seen Active Date'] = registry['Last Seen Active Date'].dt.strftime('%Y-%m-%d').fillna("N/A")

        # 4. Interactive layout configuration search engine
        search_query = st.text_input("🔍 Search Active Inventory Catalogue by Part Code:", "").strip().upper()
        if search_query:
            registry = registry[registry['Part Number Code'].str.contains(search_query, na=False)]

        st.markdown("---")
        st.write(f"Showing **{len(registry)} Distinct Component Layouts** compiled directly from warehouse activity rows.")
        
        # Display the table with weight context variables cleanly structured
        st.dataframe(
            registry[['Part Number Code', 'Registered Specification / Description', 'Component Weight Profiling', 'Last Seen Active Date']], 
            use_container_width=True, 
            hide_index=True
        )
    else:
        st.warning("Connected to database safely, but the ledger layout returned no transaction history records to pull details from.")
except Exception as e:
    st.error(f"Failed to query active item catalogue profiles: {str(e)}")
