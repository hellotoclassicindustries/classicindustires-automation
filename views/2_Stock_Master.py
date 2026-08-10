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
    with st.spinner("Calculating real-time FIFO Batch allocations..."):
        # Fetch data while excluding any items marked FALSE or unchecked
        response = (
            supabase.table("staging_ledger")
            .select("*")
            .eq("is_validated", True)  # <-- Soft-delete protection filter active
            .order("date", desc=False)  # Chronological sort order is critical for FIFO tracking
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
        
        # Split datasets cleanly into chronological transaction flows
        inward_df = df[df["entry_type"].str.lower() == "inward"].copy()
        outward_df = df[df["entry_type"].str.lower() == "outward"].copy()
        
        # Global metric variables
        current_wip_stock = inward_df["qty_nos"].sum() - outward_df["qty_nos"].sum()
                # --------------------------------------------------------------------------
        # 🧠 FIFO BATCH ALLOCATION ENGINE: TRACK DELIVERED VS REMAINING
        # --------------------------------------------------------------------------
        # Step A: Build the independent Inward Lot Queues per Part Number
        part_lot_queues = {}
        lot_counters = {} # Tracks whether it is Lot-1, Lot-2, etc. per Part Number
        
        for _, in_row in inward_df.iterrows():
            part = in_row["part_number"]
            challan = in_row["challan_no"]
            desc = in_row["description"] or "INDUSTRIAL CASTING PROFILE"
            qty = int(in_row["qty_nos"])
            arrival_date = in_row["date"]
            
            if part not in part_lot_queues:
                part_lot_queues[part] = []
                lot_counters[part] = 0
                
            lot_counters[part] += 1
            lot_label = f"Lot-{lot_counters[part]}"
            
            # Map structural batch tracking profile properties into active memory queues
            part_lot_queues[part].append({
                "lot_id": lot_label,
                "challan_no": challan,
                "part_number": part,
                "description": desc,
                "date": arrival_date,
                "inward_total": qty,
                "delivered": 0,
                "remaining": qty
            })
            
        # Step B: Burn Down Lot Queues Chronologically using Outward Dispatches (FIFO)
        for _, out_row in outward_df.iterrows():
            out_part = out_row["part_number"]
            out_qty = int(out_row["qty_nos"])
            
            if out_part in part_lot_queues:
                # Loop chronologically through available lots for this specific component part
                for lot in part_lot_queues[out_part]:
                    if out_qty <= 0:
                        break
                        
                    available_pool = lot["remaining"]
                    if available_pool > 0:
                        if out_qty >= available_pool:
                            # Complete burn down: Lot is entirely delivered and closed out
                            lot["delivered"] += available_pool
                            lot["remaining"] = 0
                            out_qty -= available_pool
                        else:
                            # Partial fulfillment extraction
                            lot["delivered"] += out_qty
                            lot["remaining"] -= out_qty
                            out_qty = 0
                            
        # Step C: Flatten Memory Objects into an Operational Analysis Dataframe
        flattened_records = []
        current_time = datetime.now()
        
        for part, lots in part_lot_queues.items():
            for lot in lots:
                # Compute floor duration metrics to trigger aging status alerts
                days_on_floor = (current_time - lot["date"]).days
                
                if lot["remaining"] <= 0:
                    status = "Completed"
                elif days_on_floor > 5:
                    status = "Delayed / Overdue"
                else:
                    status = "In Progress"
                
                # UPDATED: Reconstructed the exact target structural string naming sequence
                combined_lot_code = f"{lot['lot_id']}_{lot['part_number']}_{lot['challan_no']}"
                    
                flattened_records.append({
                    "Lot Code": combined_lot_code, # <-- Maps clean combined tracker string
                    "Part Number": lot["part_number"],
                    "Part Description": lot["description"],
                    "Challan Number (B)": lot["challan_no"],
                    "Arrival Date": lot["date"].strftime("%Y-%m-%d"),
                    "Inward Total": lot["inward_total"],
                    "Delivered (Nos)": lot["delivered"],
                    "Remaining Stock": lot["remaining"],
                    "Floor Age": days_on_floor,
                    "Status": status
                })
                
        df_fifo_ledger = pd.DataFrame(flattened_records)
        # Calculate summary tiles counts based on FIFO tracking arrays
        in_progress_count = len(df_fifo_ledger[df_fifo_ledger["Status"] == "In Progress"])
        completed_count = len(df_fifo_ledger[df_fifo_ledger["Status"] == "Completed"])
        delayed_count = len(df_fifo_ledger[df_fifo_ledger["Status"] == "Delayed / Overdue"])
        
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
                delta=f"{delayed_count} Alerts" if delayed_count > 0 else None, 
                delta_color="inverse"
            )
            
        st.markdown("###")
        
        # --------------------------------------------------------------------------
        # 📈 LIFECYCLE DONUT COMPOSITION MATRIX CHART
        # --------------------------------------------------------------------------
        st.subheader("🍩 Manufacturing FIFO Lots Lifecycle Matrix")
        
        status_summary = df_fifo_ledger.groupby("Status").size().reset_index(name="Lot Count")
        donut_chart = (
            alt.Chart(status_summary)
            .mark_arc(innerRadius=65, stroke="#fff")
            .encode(
                theta=alt.Theta(field="Lot Count", type="quantitative"),
                color=alt.Color(
                    field="Status", 
                    type="nominal", 
                    scale=alt.Scale(
                        domain=["In Progress", "Completed", "Delayed / Overdue"],
                        range=["#3498db", "#2ecc71", "#e74c3c"]  # Blue, Green, Red
                    )
                ),
                tooltip=["Status", "Lot Count"]
            )
            .properties(width=400, height=320)
        )
        
        st.altair_chart(donut_chart, use_container_width=True)
        st.markdown("---")
        
        # --------------------------------------------------------------------------
        # 🔍 DYNAMIC MULTI-MAPPED FIFO LEDGER DATA MATRIX
        # --------------------------------------------------------------------------
        st.subheader("📋 FIFO Lot Tracking Ledger")
        st.caption("Real-time batch depletion grid detailing exact counts delivered and remaining per sequential lot channel")
        
        # Interactive Search Filter Dropdown
        filter_status = st.selectbox(
            "🔎 Filter View by Lifecycle Status", 
            ["All Records", "In Progress Only", "Completed Only", "Delayed / Overdue Only"]
        )
        
        if filter_status == "In Progress Only":
            df_display = df_fifo_ledger[df_fifo_ledger["Status"] == "In Progress"]
        elif filter_status == "Completed Only":
            df_display = df_fifo_ledger[df_fifo_ledger["Status"] == "Completed"]
        elif filter_status == "Delayed / Overdue Only":
            df_display = df_fifo_ledger[df_fifo_ledger["Status"] == "Delayed / Overdue"]
        else:
            df_display = df_fifo_ledger
            
        # Display the fully-mapped interactive data frame layout grid
        st.dataframe(
            df_display.sort_values(by=["Part Number", "Lot Code"], ascending=[True, True]), 
            use_container_width=True, 
            hide_index=True,
            column_order=[
                "Lot Code", "Part Number", "Part Description", "Challan Number (B)", 
                "Arrival Date", "Inward Total", "Delivered (Nos)", "Remaining Stock", 
                "Floor Age", "Status"
            ],
            column_config={
                "Inward Total": st.column_config.NumberColumn(format="%d"),
                "Delivered (Nos)": st.column_config.NumberColumn(format="%d"),
                "Remaining Stock": st.column_config.NumberColumn(format="%d"),
                "Floor Age": st.column_config.NumberColumn(format="%d Days")
            }
        )

except Exception as e:
    st.error(f"🚨 Network exception running FIFO calculations: {str(e)}")
