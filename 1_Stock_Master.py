import streamlit as st
import pandas as pd

st.title("📊 Stock Master Balance Ledger")
st.subheader("Aggregated Current Warehouse Inventories")

supabase = st.session_state.supabase
TABLE_NAME = st.secrets["TABLE_NAME"]

try:
    response = supabase.table(TABLE_NAME).select("entry_type, qty_nos, part_number").execute()
    records = response.data

    if records:
        df = pd.DataFrame(records)
        df['qty_nos'] = pd.to_numeric(df['qty_nos'], errors='coerce').fillna(0).astype(int)
        df['entry_type'] = df['entry_type'].astype(str).str.strip().str.lower()

        # Build Pivot Data Frame summarizing metrics per individual part number
        summary = df.groupby('part_number').apply(lambda x: pd.Series({
            'Total Inward': x[x['entry_type'] == 'inward']['qty_nos'].sum(),
            'Total Outward': x[x['entry_type'] == 'outward']['qty_nos'].sum(),
            'Current WIP Balance': x[x['entry_type'] == 'inward']['qty_nos'].sum() - x[x['entry_type'] == 'outward']['qty_nos'].sum()
        })).reset_index()

        # Display Top level summaries
        kpi1, kpi2 = st.columns(2)
        kpi1.metric("Total Items Managed", f"{summary['Current WIP Balance'].sum():,} Pcs")
        kpi2.metric("Active Working Part Configurations", len(summary))

        st.markdown("---")
        st.write("### Current Calculated Stock Summary Table")
        st.dataframe(summary, use_container_width=True)
    else:
        st.info("No transaction lines found to calculate master inventory levels.")
except Exception as e:
    st.error(f"Error fetching Stock Master metrics: {str(e)}")
