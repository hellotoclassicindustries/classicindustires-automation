import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, date

# Initialize Secure Supabase Target Connections
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

def fetch_raw_ledger_payload():
    """
    Fetches validated ledger records from your Supabase staging database backend.
    """
    try:
        response = supabase.table("staging_ledger") \
            .select("date, part_number, description, entry_type, ref_challan_no, challan_no, qty_nos, remarks_notes") \
            .eq("is_validated", True) \
            .order("date", desc=False) \
            .execute()
        return response.data
    except Exception as e:
        st.error(f"Error fetching database values: {str(e)}")
        return []

# Set up Dashboard Grid Presentation Layout
st.set_page_config(page_title="ClassicIndustries | Stock Master", layout="wide")
st.title("📦 Live Work-In-Progress (WIP) Stock Master Dashboard")
st.markdown("---")

raw_data = fetch_raw_ledger_payload()

if raw_data:
    global_stock = {}     # Tracks running balances per production SKU
    lot_stock = {}        # Tracks batch-level details chronologically
    sample_assets = {}    # Maps Part Number -> Total Permanent Reference Collection Items
    inward_sequence = []  # Tracks arrival timeline for FIFO sorting

    # PASS 1: Log all Inward deliveries chronologically and separate active stock from permanent samples
    for row in raw_data:
        part = str(row["part_number"]).strip().upper()
        desc = str(row["description"]).strip().upper()
        qty = int(row["qty_nos"])
        remarks = str(row["remarks_notes"]).strip().upper()
        
        if row["entry_type"].strip().lower() == "inward":
            lot_id = row["challan_no"].strip().upper()
            
            # 🔬 PERMANENT REFERENCE ASSET ISOLATION TRACK GATE
            if "SAMPLE" in remarks or "PTO" in remarks:
                if part not in sample_assets:
                    sample_assets[part] = {"description": desc, "qty": 0, "challans": set()}
                sample_assets[part]["qty"] += qty
                sample_assets[part]["challans"].add(lot_id)
                continue 
                
            # Regular Production Material Routing Tracks
            if part not in global_stock:
                global_stock[part] = {"description": desc, "inward": 0, "outward": 0}
            global_stock[part]["inward"] += qty
            
            lot_key = (part, lot_id)
            if lot_key not in lot_stock:
                lot_stock[lot_key] = {"description": desc, "inward": 0, "outward": 0, "date": row["date"]}
                inward_sequence.append(lot_key)
            lot_stock[lot_key]["inward"] += qty

    # PASS 2: Deduct outward dispatches (Production material allocation only)
    for row in raw_data:
        if row["entry_type"].strip().lower() == "outward":
            part = str(row["part_number"]).strip().upper()
            qty = int(row["qty_nos"])
            ref_lot_str = row["ref_challan_no"].strip().upper()
            
            if part in global_stock:
                global_stock[part]["outward"] += qty
                
            allocated_qty = qty
            
            if ref_lot_str not in ["NO-REF", "SELF", "NONE"] and "&" not in ref_lot_str:
                lot_key = (part, ref_lot_str)
                if lot_key in lot_stock:
                    lot_stock[lot_key]["outward"] += allocated_qty
                    allocated_qty = 0
            
            if allocated_qty > 0:
                for lot_key in inward_sequence:
                    if lot_key == part:
                        available_in_batch = lot_stock[lot_key]["inward"] - lot_stock[lot_key]["outward"]
                        
                        if available_in_batch >= allocated_qty:
                            lot_stock[lot_key]["outward"] += allocated_qty
                            allocated_qty = 0
                            break
                        elif available_in_batch > 0:
                            lot_stock[lot_key]["outward"] += available_in_batch
                            allocated_qty -= available_in_batch
                
                if allocated_qty > 0:
                    overflow_key = (part, "UNASSIGNED OVERFLOW")
                    if overflow_key not in lot_stock:
                        lot_stock[overflow_key] = {"description": row["description"].strip().upper(), "inward": 0, "outward": 0, "date": row["date"]}
                    lot_stock[overflow_key]["outward"] += allocated_qty
        # Formulate Structured Raw Dataframe Arrays
    global_rows = []
    for part, details in global_stock.items():
        net_bal = details["inward"] - details["outward"]
        global_rows.append({
            "Part Number": part,
            "Item Description": details["description"],
            "Total Inward Received (Nos)": details["inward"],
            "Total Outward Shipped (Nos)": details["outward"],
            "Net Available Stock (Nos)": max(0, net_bal)
        })
    df_global_raw = pd.DataFrame(global_rows)

    lot_rows = []
    chart_rows = []
    for (part, lot_id), details in lot_stock.items():
        net_lot_bal = details["inward"] - details["outward"]
        display_bal = max(0, net_lot_bal)
        
        # 💡 FIXED: Enforces strict string-to-date object parsing for the table matrix rows
        try:
            if isinstance(details["date"], str):
                row_date = datetime.strptime(details["date"].split(" ")[0].strip(), "%Y-%m-%d").date()
            elif isinstance(details["date"], (datetime, date)):
                row_date = details["date"]
            else:
                row_date = date.today()
        except Exception as date_err:
            row_date = date.today()
            
        lot_rows.append({
            "Date": row_date,
            "Part Number": part,
            "Inward Lot Identity/Challan": lot_id,
            "Item Description": details["description"],
            "Original Inward (Nos)": details["inward"],
            "Delivered Outward (Nos)": details["outward"],
            "Lot Remaining WIP Balance": display_bal
        })
        
        if details["inward"] > 0 or details["outward"] > 0:
            lot_label = f"{part} (Lot: {lot_id})"
            chart_rows.append({"Date": row_date, "Part Number": part, "Item Description": details["description"], "Lot Reference": lot_label, "Metric Type": "Delivered Shipped (Nos)", "Quantity": details["outward"]})
            chart_rows.append({"Date": row_date, "Part Number": part, "Item Description": details["description"], "Lot Reference": lot_label, "Metric Type": "Remaining WIP Stock (Nos)", "Quantity": display_bal})
            
    df_lots_raw = pd.DataFrame(lot_rows)
    df_chart_raw = pd.DataFrame(chart_rows)

    sample_rows = []
    for part, details in sample_assets.items():
        sample_rows.append({
            "Part Number": part,
            "Item Description": details["description"],
            "Total Pieces Retained (Nos)": details["qty"],
            "Origin Challan References": ", ".join(list(details["challans"]))
        })
    df_samples_raw = pd.DataFrame(sample_rows)

    # 🎛️ CENTRAL MASTER CONTROL PANEL (ONE FILTER SYSTEM TARGETING ALL SECTIONS)
    st.subheader("🔍 Master Inventory Query & Filter Panel")
    st.markdown("_Select your criteria here to filter ALL tables, charts, and matrices at once:_")
    
    f_col1, f_col2, f_col3 = st.columns(3)
    with f_col1:
        unique_parts = sorted(df_lots_raw["Part Number"].unique().tolist()) if not df_lots_raw.empty else []
        selected_parts = st.multiselect("🔢 Select Target Part Numbers:", options=unique_parts, placeholder="All Active SKUs")
    with f_col2:
        unique_descs = sorted(df_lots_raw["Item Description"].unique().tolist()) if not df_lots_raw.empty else []
        selected_descs = st.multiselect("⚙️ Select Component Descriptions:", options=unique_descs, placeholder="All Descriptions")
    with f_col3:
        all_dates = df_lots_raw["Date"].tolist() if not df_lots_raw.empty else [date.today()]
        min_date, max_date = min(all_dates), max(all_dates)
        selected_date_range = st.date_input("📆 Filter by Transaction Timeline:", [min_date, max_date], min_value=min_date, max_value=max_date)

    # ⚡ APPLICATION ENGINE FOR UNIFIED DATA FILTERING
    df_global_filtered = df_global_raw.copy()
    df_samples_filtered = df_samples_raw.copy()
    df_chart_filtered = df_chart_raw.copy()
    df_lots_filtered = df_lots_raw.copy()

    # Apply part filters globally
    if selected_parts:
        if not df_global_filtered.empty: df_global_filtered = df_global_filtered[df_global_filtered["Part Number"].isin(selected_parts)]
        if not df_samples_filtered.empty: df_samples_filtered = df_samples_filtered[df_samples_filtered["Part Number"].isin(selected_parts)]
        df_chart_filtered = df_chart_filtered[df_chart_filtered["Part Number"].isin(selected_parts)]
        df_lots_filtered = df_lots_filtered[df_lots_filtered["Part Number"].isin(selected_parts)]
        
    # Apply text description filters globally
    if selected_descs:
        if not df_global_filtered.empty: df_global_filtered = df_global_filtered[df_global_filtered["Item Description"].isin(selected_descs)]
        if not df_samples_filtered.empty: df_samples_filtered = df_samples_filtered[df_samples_filtered["Item Description"].isin(selected_descs)]
        df_chart_filtered = df_chart_filtered[df_chart_filtered["Item Description"].isin(selected_descs)]
        df_lots_filtered = df_lots_filtered[df_lots_filtered["Item Description"].isin(selected_descs)]

    # 💡 SAFE DATETIME PARSING FILTER FOR UNIVERSAL SYNCHRONIZATION
    if isinstance(selected_date_range, (list, tuple)) and len(selected_date_range) == 2:
        start_date, end_date = selected_date_range
        if not df_lots_filtered.empty:
            df_lots_filtered = df_lots_filtered[(df_lots_filtered["Date"] >= start_date) & (df_lots_filtered["Date"] <= end_date)]
        if not df_chart_filtered.empty:
            df_chart_filtered = df_chart_filtered[(df_chart_filtered["Date"] >= start_date) & (df_chart_filtered["Date"] <= end_date)]

    # 📋 OUTPUT PANEL 1: Global Summary
    st.markdown("---")
    st.subheader("📋 Consolidated Global Production Part Balances")
    if not df_global_filtered.empty:
        st.dataframe(df_global_filtered, use_container_width=True)
    else:
        st.info("No global summary matches your selected filter criteria.")
    
    # 🔬 OUTPUT PANEL 2: Permanent Reference Asset Register
    st.markdown("---")
    st.subheader("🔬 Permanent Reference Sample Collection (Retained Assets)")
    if not df_samples_filtered.empty:
        st.dataframe(df_samples_filtered, use_container_width=True)
    else:
        st.info("No reference sample tokens match your selected filter criteria.")
        
    # 📊 OUTPUT PANEL 3: Dynamic Visual Graph
    st.markdown("---")
    st.subheader("📊 Lot Stock Allocation Levels (Delivered vs Remaining)")
    if not df_chart_filtered.empty:
        chart_pivot = df_chart_filtered.pivot(index="Lot Reference", columns="Metric Type", values="Quantity").fillna(0)
        st.bar_chart(data=chart_pivot, color=["#0068c9", "#29b573"], use_container_width=True, height=380)
    else:
        st.info("No graphical bars match your selected filter criteria.")
        
    # 🔍 OUTPUT PANEL 4: Granular Material Ledger Matrix
    st.markdown("---")
    st.subheader("🔍 Lot-by-Lot Traceability Breakdown Matrix Ledger")
    if not df_lots_filtered.empty:
        st.dataframe(df_lots_filtered, use_container_width=True, height=400)
    else:
        st.info("No granular batch records match your selected filter criteria.")

else:
    st.info("No validated transaction entries are currently available to compute stock numbers.")
