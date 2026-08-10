import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from datetime import datetime, timezone

st.title("📊 Stock Master Balance Ledger")
st.subheader("Aggregated Current Warehouse Inventories & Lot Health Status")

# Extract the cached connection setup from session state
supabase = st.session_state.supabase
TABLE_NAME = st.secrets["TABLE_NAME"]

try:
    # 1. Fetch transaction history logs from your core staging ledger
    ledger_res = supabase.table(TABLE_NAME).select("entry_type, qty_nos, part_number, challan_no, date, description").execute()
    ledger_records = ledger_res.data

    if ledger_records:
        df_ledger = pd.DataFrame(ledger_records)
        
        # Standardize data types to prevent calculation bugs
        df_ledger['qty_nos'] = pd.to_numeric(df_ledger['qty_nos'], errors='coerce').fillna(0).astype(int)
        df_ledger['entry_type'] = df_ledger['entry_type'].astype(str).str.strip().str.lower()
        df_ledger['date'] = pd.to_datetime(df_ledger['date'], errors='coerce')
        df_ledger['part_number'] = df_ledger['part_number'].astype(str).str.strip().str.upper()
        df_ledger['challan_no'] = df_ledger['challan_no'].astype(str).str.strip().str.upper()
        df_ledger['description'] = df_ledger['description'].astype(str).str.strip().str.upper()

        # 2. Map newest description strings per individual part number
        desc_mapping = df_ledger.sort_values('date').groupby('part_number')['description'].last().to_dict()

        # 3. ADVANCED UPGRADE: Group calculations at the individual Challan Lot level
        summary = df_ledger.groupby(['part_number', 'challan_no']).apply(lambda x: pd.Series({
            'Total Inward': x[x['entry_type'] == 'inward']['qty_nos'].sum(),
            'Total Outward': x[x['entry_type'] == 'outward']['qty_nos'].sum(),
            'Current WIP Balance': x[x['entry_type'] == 'inward']['qty_nos'].sum() - x[x['entry_type'] == 'outward']['qty_nos'].sum(),
            'Lot Arrival Date': x[x['entry_type'] == 'inward']['date'].min(),
            'Last Activity Date': x['date'].max()
        }), include_groups=False).reset_index()

        # Generate Unique, Human-Readable Operational Lot IDs
        summary['Operational Lot ID'] = summary['part_number'] + " — Lot (" + summary['challan_no'] + ")"
        
        # Apply descriptions
        summary['description'] = summary['part_number'].map(desc_mapping).fillna("UNKNOWN SPECIFICATION")

        # 4. Compute Dynamic Status Values based on 5-Day Lot Arrival Deadline
        today = pd.Timestamp(datetime.now(timezone.utc).date())
        summary['Lot Arrival Date'] = summary['Lot Arrival Date'].fillna(summary['Last Activity Date'])
        
        conditions = [
            (summary['Current WIP Balance'] <= 0),
            ((today - summary['Lot Arrival Date'].dt.tz_localize(None)).dt.days > 5)
        ]
        choices = ['Complete', 'Delayed']
        summary['Lot Production Status'] = np.select(conditions, choices, default='In Progress')

        # Format dates neatly for displaying in panels
        summary['Lot Arrival'] = summary['Lot Arrival Date'].dt.strftime('%Y-%m-%d').fillna("N/A")
        summary['Last Activity'] = summary['Last Activity Date'].dt.strftime('%Y-%m-%d').fillna("N/A")

        # 5. Render Clear Plain-Language KPI Metrics
        kpi1, kpi2, kpi3 = st.columns(3)
        with kpi1:
            st.metric(label="Total Physical Stock on Shop Floor", value=f"{summary['Current WIP Balance'].sum():,} Pcs")
        with kpi2:
            st.metric(label="Total Unique Shipments / Lots Active", value=f"{len(summary)} Batches")
        with kpi3:
            delayed_count = len(summary[summary['Lot Production Status'] == 'Delayed'])
            st.metric(
                label="Overdue Batches (>5 Days old)", 
                value=f"{delayed_count} Lots", 
                delta=f"{delayed_count} Delayed" if delayed_count > 0 else "All Clear", 
                delta_color="inverse"
            )

        st.markdown("---")
        
        # 6. Render Side-by-Side Donut and Breakdown Matrix Layout
        st.write("### 🍩 Shop Floor Operational Status Breakdown (Grouped by Lots)")
        
        status_counts = summary['Lot Production Status'].value_counts().reset_index()
        status_counts.columns = ['Status', 'Total Active Lots']
        
        color_scale = alt.Scale(
            domain=['In Progress', 'Complete', 'Delayed'],
            range=['#3498db', '#2ecc71', '#e74c3c'] 
        )
        
        donut_chart = alt.Chart(status_counts).mark_arc(innerRadius=65, outerRadius=110, stroke='#fff').encode(
            theta=alt.Theta(field="Total Active Lots", type="quantitative"),
            color=alt.Color(field="Status", type="nominal", scale=color_scale, legend=alt.Legend(title="Lot Status")),
            tooltip=[alt.Tooltip('Status', title='Status'), alt.Tooltip('Total Active Lots', title='Total Active Lots')]
        ).properties(width=320, height=260).configure_view(strokeWidth=0)
        
        graph_col, data_summary_col = st.columns([1.2, 1])
        
        with graph_col:
            st.altair_chart(donut_chart, use_container_width=True)
            
        with data_summary_col:
            st.markdown("<br><br>", unsafe_allow_html=True)
            st.write("**Real-time Lot Status Count Matrix:**")
            st.dataframe(status_counts, use_container_width=True, hide_index=True)

        st.markdown("---")

        # 7. Render Upgraded "Current Calculated Stock Summary Table"
        st.write("### 📋 Perfected Lot-by-Lot Calculated Stock Summary Table")
        
        # Re-arrange table columns to emphasize Lot IDs and isolate delays immediately
        ordered_display_df = summary[[
            'Operational Lot ID', 'part_number', 'description', 'Lot Production Status', 
            'Total Inward', 'Total Outward', 'Current WIP Balance', 
            'Lot Arrival', 'Last Activity'
        ]].sort_values(by=['Lot Production Status', 'Current WIP Balance'], ascending=[True, False])
        
        st.dataframe(ordered_display_df, use_container_width=True, hide_index=True)

    else:
        st.info("Connected to Supabase securely. However, the transaction ledger contains no active rows to calculate balances.")
except Exception as e:
    st.error(f"Failed to query live Stock Master calculations: {str(e)}")
