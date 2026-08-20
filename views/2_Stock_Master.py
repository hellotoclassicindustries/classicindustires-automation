import streamlit as st
import pandas as pd
from supabase import create_client, Client

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
            
            # 🔬 1. PERMANENT REFERENCE ASSET ISOLATION TRACK GATE
            if "SAMPLE" in remarks or "PTO" in remarks:
                if part not in sample_assets:
                    sample_assets[part] = {"description": desc, "qty": 0, "challans": set()}
                sample_assets[part]["qty"] += qty
                sample_assets[part]["challans"].add(lot_id)
                continue # Bypasses commercial inventory balances completely!
                
            # 2. Regular Production Material Routing Tracks
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

    # SECTION 1: Consolidated Global Production Balances Table
    st.subheader("📋 Consolidated Global Production Part Balances")
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
    if global_rows:
        st.dataframe(pd.DataFrame(global_rows), use_container_width=True)
    else:
        st.info("No active production balances logged in the system.")
    
    st.markdown("---")
    
    # SECTION 2: 🔬 Permanent Reference Sample Collection (Retained Factory Assets)
    st.subheader("🔬 Permanent Reference Sample Collection (Retained Assets)")
    st.markdown("_These items are preserved inside the facility archives for future reference and are isolated from production totals._")
    sample_rows = []
    for part, details in sample_assets.items():
        sample_rows.append({
            "Part Number": part,
            "Item Description": details["description"],
            "Total Pieces Retained (Nos)": details["qty"],
            "Origin Challan References": ", ".join(list(details["challans"]))
        })
    if sample_rows:
        st.dataframe(pd.DataFrame(sample_rows), use_container_width=True)
    else:
        st.info("No permanent sample tokens are currently logged in the facility archives.")
        
    st.markdown("---")
    
    # SECTION 3: 🔍 Full-Width Stacked Chart Allocation Display Visualization
    st.subheader("📊 Lot Stock Allocation Allocation Levels (Delivered vs Remaining)")
    
    lot_rows = []
    chart_rows = []
    
    for (part, lot_id), details in lot_stock.items():
        net_lot_bal = details["inward"] - details["outward"]
        display_bal = max(0, net_lot_bal)
        
        lot_rows.append({
            "Part Number": part,
            "Inward Lot Identity": lot_id,
            "Item Description": details["description"],
            "Original Inward (Nos)": details["inward"],
            "Delivered Outward (Nos)": details["outward"],
            "Lot Remaining WIP Balance": display_bal
        })
        
        if details["inward"] > 0 or details["outward"] > 0:
            lot_label = f"{part} (Lot: {lot_id})"
            chart_rows.append({"Lot Reference": lot_label, "Metric Type": "Delivered Shipped (Nos)", "Quantity": details["outward"]})
            chart_rows.append({"Lot Reference": lot_label, "Metric Type": "Remaining WIP Stock (Nos)", "Quantity": display_bal})
            
    df_lots = pd.DataFrame(lot_rows)
    df_chart = pd.DataFrame(chart_rows)
    
    if not df_chart.empty:
        chart_pivot = df_chart.pivot(index="Lot Reference", columns="Metric Type", values="Quantity").fillna(0)
        # 🚀 100% HORIZONTAL SPACE: The chart expands to take up the full screen width, giving text labels plenty of room!
        st.bar_chart(
            data=chart_pivot,
            color=["#29b573", "#0068c9" ], # Blueprint Green = Shipped | Operational Blue = Remaining Stock
            use_container_width=True,
            height=380
        )
    else:
        st.info("No active production transaction logs available to plot charting metrics.")
        
    st.markdown("---")
    
    # SECTION 4: Full-Width Lot-by-Lot Traceability Data Matrix Table
    st.subheader("🔍 Lot-by-Lot Traceability Breakdown Matrix Ledger")
    st.dataframe(df_lots, use_container_width=True, height=400)

else:
    st.info("No validated transaction entries are currently available to compute stock numbers.")
