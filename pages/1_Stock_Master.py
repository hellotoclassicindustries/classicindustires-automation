import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from datetime import datetime, timezone

st.title("📊 Stock Master Balance Ledger")
st.subheader("Aggregated Current Warehouse Inventories & Order Health Status")

# Extract the cached connection setup from session state
supabase = st.session_state.supabase
TABLE_NAME = st.secrets["TABLE_NAME"]

try:
    # 1. Fetch data from your core staging ledger
    ledger_res = supabase.table(TABLE_NAME).select("entry_type, qty_nos, part_number, date, description").execute()
    ledger_records = ledger_res.data

    if ledger_records:
        df_ledger = pd.DataFrame(ledger_records)
        
        # Standardize data types
        df_ledger['qty_nos'] = pd.to_numeric(df_ledger['qty_nos'], errors='coerce').fillna(0).astype(int)
        df_ledger['entry_type'] = df_ledger['entry_type'].astype(str).str.strip().str.lower()
        df_ledger['date'] = pd.to_datetime(df_ledger['date'], errors='coerce')
        df_ledger['description'] = df_ledger['description'].astype(str).str.strip().str.upper()

        # 2. Extract the latest description available for each part number
        desc_mapping = df_ledger.sort_values('date').groupby('part_number')['description'].last().to_dict()

        # 3. Build Core Pivot Aggregation Framework per Part Number
        summary = df_ledger.groupby('part_number').apply(lambda x: pd.Series({
            'Total Inward': x[x['entry_type'] == 'inward']['qty_nos'].sum(),
            'Total Outward': x[x['entry_type'] == 'outward']['qty_nos'].sum(),
            'Current WIP Balance': x[x['entry_type'] == 'inward']['qty_nos'].sum() - x[x['entry_type'] == 'outward']['qty_nos'].sum(),
            'First Arrival': x[x['entry_type'] == 'inward']['date'].min(),
            'Last Updated': x['date'].max()
        }), include_groups=False).reset_index()

        # 4. Apply Descriptions
        summary['description'] = summary['part_number'].map(desc_mapping).fillna("UNKNOWN SPECIFICATION")

        # 5. Compute Status Values based on 5-day arrival logic
        today = pd.Timestamp(datetime.now(timezone.utc).date())
        summary['First Arrival'] = summary['First Arrival'].fillna(summary['Last Updated'])
        
        conditions = [
            (summary['Current WIP Balance'] <= 0),
            ((today - summary['First Arrival'].dt.tz_localize(None)).dt.days > 5)
        ]
        choices = ['Complete', 'Delayed']
        summary['Production Status'] = np.select(conditions, choices, default='In Progress')

        # Format dates for table display
        summary['First Arrival Date'] = summary['First Arrival'].dt.strftime('%Y-%m-%d').fillna("N/A")
        summary['Last Updated Date'] = summary['Last Updated'].dt.strftime('%Y-%m-%d').fillna("N/A")

        # 6. Render Plain-Language KPI Metrics
        kpi1, kpi2, kpi3 = st.columns(3)
        with kpi1:
            st.metric(label="Total Physical Stock on Shop Floor", value=f"{summary['Current WIP Balance'].sum():,} Pcs")
        with kpi2:
            st.metric(label="Distinct Part Types Active", value=f"{len(summary)} Models")
        with kpi3:
            delayed_count = len(summary[summary['Production Status'] == 'Delayed'])
            st.metric(
                label="Overdue Part Types (>5 Days old)", 
                value=f"{delayed_count} Models", 
                delta=f"{delayed_count} Overdue" if delayed_count > 0 else "All Clear", 
                delta_color="inverse"
            )

        st.markdown("---")
        
        # 7. Build the Round Graph (Altair Donut Chart Component)
        st.write("### 🍩 Shop Floor Operational Status Breakdown")
        
        status_counts = summary['Production Status'].value_counts().reset_index()
        status_counts.columns = ['Status', 'Count']
        
        color_scale = alt.Scale(
            domain=['In Progress', 'Complete', 'Delayed'],
            range=['#3498db', '#2ecc71', '#e74c3c'] 
        )
        
        donut_chart = alt.Chart(status_counts).mark_arc(innerRadius=65, stroke='#fff').encode(
            theta=alt.Theta(field="Count", type="quantitative"),
            color=alt.Color(field="Status", type="nominal", scale=color_scale, legend=alt.Legend(title="Batch Status")),
            tooltip=[alt.Tooltip('Status', title='Status'), alt.Tooltip('Count', title='Total Batches')]
        ).properties(width=400, height=300).configure_view(strokeWidth=0)
        
        # FIXED: Explicitly passed '2' into st.columns to prevent LayoutsMixin error
        graph_col, pad_col = st.columns(2)
        with graph_col:
            st.altair_chart(donut_chart, use_container_width=True)

        st.markdown("---")

        # 8. Render Summary Table
        st.write("### 📋 Perfected Current Calculated Stock Summary Table")
        
        ordered_display_df = summary[[
            'part_number', 'description', 'Production Status', 
            'Total Inward', 'Total Outward', 'Current WIP Balance', 
            'First Arrival Date', 'Last Updated Date'
        ]]
        
        st.dataframe(ordered_display_df, use_container_width=True)

    else:
        st.info("Connected to Supabase securely. However, the transaction ledger contains no active rows to calculate balances.")
except Exception as e:
    st.error(f"Failed to query live Stock Master calculations: {str(e)}")
