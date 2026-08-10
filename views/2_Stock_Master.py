import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime

# 🔒 RECONCILIATION FIREWALL: Ensure session is authenticated before rendering
if not st.session_state.get("authenticated", False):
    st.title("🔒 Restricted Corporate Node")
    st.error("Access Denied. This terminal view contains confidential operational values.")
    st.info("💡 Please use the sidebar authentication panel to log in first.")
    st.stop()

# Grab the live, cached database network stack from global state
supabase = st.session_state.supabase

st.title("📊 Stock Master Balance Ledger")
st.caption("Classic Industries — Foundry Friends & Finishers Division")
st.markdown("---")

# --------------------------------------------------------------------------
# 📡 DATA PIPELINE LAYER: FETCH SECURE ACTIVE METRICS FROM CLOUD
# --------------------------------------------------------------------------
try:
    with st.spinner("Extracting real-time floor inventory profiles..."):
        # Fetch data while excluding any items marked FALSE or unchecked
        response = (
            supabase.table("staging_ledger")
            .select("*")
            .eq("is_validated", True)  # <-- Soft-delete protection filter active
            .execute()
        )
        
    raw_data = response.data
    df = pd.DataFrame(raw_data)
    
    if df.empty:
        st.info("ℹ️ No active inventory ledger metrics currently recorded on the shop floor.")
    else:
        # Standardize data parameters
        df["qty_nos"] = pd.to_numeric(df["qty_nos"], errors="coerce").fillna(0)
        df["date"] = pd.to_datetime(df["date"])
        
        # Calculate dynamic physical WIP balances
        inward_total = df[df["entry_type"].str.lower() == "inward"]["qty_nos"].sum()
        outward_total = df[df["entry_type"].str.lower() == "outward"]["qty_nos"].sum()
        current_wip_stock = inward_total - outward_total
        
        # --------------------------------------------------------------------------
        # 🧠 IN PROGRESS VS COMPLETED VS DELAYED AGING LOGIC (LOT-BY-LOT)
        # --------------------------------------------------------------------------
        batch_groups = df.groupby("challan_no")
        batch_records = []
        
        # Reference point fixed to current date execution constraints
        current_time = datetime.now()
        
        for challan_no, group in batch_groups:
            in_qty = group[group["entry_type"].str.lower() == "inward"]["qty_nos"].sum()
            out_qty = group[group["entry_type"].str.lower() == "outward"]["qty_nos"].sum()
            lot_balance = in_qty - out_qty
            
            # Extract target component code profiles linked to this specific lot
            associated_parts = ", ".join(group["part_number"].dropna().unique())
            
            # Identify original arrival date of the lot
            earliest_date = group["date"].min()
            days_on_floor = (current_time - earliest_date).days
            
            # Determine precise manufacturing state boundaries
            if lot_balance <= 0:
                status = "Completed"
            elif days_on_floor > 5:
                status = "Delayed / Overdue"
            else:
                status = "In Progress"
                
            batch_records.append({
                "Challan No": challan_no,
                "Associated Parts": associated_parts,
                "Inward Qty": in_qty,
                "Outward Qty": out_qty,
                "Current WIP": lot_balance,
                "Days on Floor": days_on_floor,
                "Status": status
            })
            
        df_batches = pd.DataFrame(batch_records)
        
        # Aggregate metrics for high-utility summary tiles
        in_progress_count = len(df_batches[df_batches["Status"] == "In Progress"])
        completed_count = len(df_batches[df_batches["Status"] == "Completed"])
        delayed_count = len(df_batches[df_batches["Status"] == "Delayed / Overdue"])
        
        # --------------------------------------------------------------------------
        # 🏢 HIGH-CONTRAST HEADLINE KPI TILES
        # --------------------------------------------------------------------------
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        with kpi1:
            st.metric(label="Total WIP Stock (Nos)", value=f"{int(current_wip_stock):,}")
        with kpi2:
            st.metric(label="In Progress Lots", value=in_progress_count)
        with kpi3:
            st.metric(label="Completed Lots", value=completed_count)
        with kpi4:
            st.metric(
                label="Overdue (>5 Days) Lots", 
                value=delayed_count, 
                delta=f"{delayed_count} Critical Alerts" if delayed_count > 0 else None, 
                delta_color="inverse"
            )
            
        st.markdown("###")
        
        # --------------------------------------------------------------------------
        # 📈 LIFECYCLE COMPOSITION MATRIX CHART
        # --------------------------------------------------------------------------
        st.subheader("🍩 Manufacturing Lots Lifecycle Matrix")
        
        status_summary = df_batches.groupby("Status").size().reset_index(name="Lot Count")
        
        donut_chart = (
            alt.Chart(status_summary)
            .mark_arc(innerRadius=65, stroke="#fff")
            .encode(
                theta=alt.Theta(field="Lot Count", type="quantitative", title="Total Batches"),
                color=alt.Color(
                    field="Status", 
                    type="nominal", 
                    title="Lot Lifecycle State",
                    scale=alt.Scale(
                        domain=["In Progress", "Completed", "Delayed / Overdue"],
                        range=["#3498db", "#2ecc71", "#e74c3c"] # Blue, Green, Red
                    )
                ),
                tooltip=["Status", "Lot Count"]
            )
            .properties(width=400, height=320)
        )
        
        st.altair_chart(donut_chart, use_container_width=True)
        st.markdown("---")
        
        # --------------------------------------------------------------------------
        # 🔍 DYNAMIC LOT-BY-LOT INTERACTIVE FILTERS
        # --------------------------------------------------------------------------
        st.subheader("📋 Production Lot Tracking Ledger")
        st.caption("Real-time lot-by-lot tracking, lifecycle parameters, and material balances")
        
        # Search panel engine allowing workers to sort or filter records on the fly
        filter_status = st.selectbox(
            "🔎 Filter View by Lifecycle Status", 
            ["All Records", "In Progress Only", "Completed Only", "Delayed / Overdue Only"]
        )
        
        if filter_status == "In Progress Only":
            df_display = df_batches[df_batches["Status"] == "In Progress"]
        elif filter_status == "Completed Only":
            df_display = df_batches[df_batches["Status"] == "Completed"]
        elif filter_status == "Delayed / Overdue Only":
            df_display = df_batches[df_batches["Status"] == "Delayed / Overdue"]
        else:
            df_display = df_batches
            
        # Display the complete lot-by-lot tracking matrix cleanly formatted
        st.dataframe(
            df_display.sort_values(by="Days on Floor", ascending=False), 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Inward Qty": st.column_config.NumberColumn(format="%d"),
                "Outward Qty": st.column_config.NumberColumn(format="%d"),
                "Current WIP": st.column_config.NumberColumn(format="%d"),
                "Days on Floor": st.column_config.NumberColumn(format="%d Days"),
                "Status": st.column_config.TextColumn(help="Calculated based on 5-day cycle thresholds")
            }
        )

except Exception as e:
    st.error(f"🚨 Network exception fetching aging data profiles from Supabase: {str(e)}")
