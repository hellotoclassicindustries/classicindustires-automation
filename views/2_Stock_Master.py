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
            .select("date, part_number, description, entry_type, ref_challan_no, challan_no, qty_nos") \
            .eq("is_validated", True) \
            .order("date", desc=False) \
            .execute()
        return response.data
    except Exception as e:
        st.error(f"Error fetching database values: {str(e)}")
        return []

# Set up Dashboard Grid Presentation Layout
st.set_page_config(page_title="ClassicIndustries | Stock Master", layout="wide")
st.title("📦 Live Work-In-Progress (WIP) Stock Master")
st.markdown("---")

raw_data = fetch_raw_ledger_payload()

if raw_data:
    global_stock = {}  # Tracks net running balances per SKU
    lot_stock = {}     # Key: (part_number, lot_id) -> Tracks histories chronologically
    inward_sequence = [] # Tracks the exact arrival timeline of incoming lots for FIFO sorting

    # PASS 1: Log all Inward deliveries chronologically to establish our baselines
    for row in raw_data:
        part = row["part_number"].strip().upper()
        desc = row["description"].strip().upper()
        qty = int(row["qty_nos"])
        
        if row["entry_type"].strip().lower() == "inward":
            lot_id = row["challan_no"].strip().upper()
            
            # Populate Global Summary Map
            if part not in global_stock:
                global_stock[part] = {"description": desc, "inward": 0, "outward": 0}
            global_stock[part]["inward"] += qty
            
            # Populate Granular Lot Record Map
            lot_key = (part, lot_id)
            if lot_key not in lot_stock:
                lot_stock[lot_key] = {"description": desc, "inward": 0, "outward": 0, "date": row["date"]}
                inward_sequence.append(lot_key)
            lot_stock[lot_key]["inward"] += qty

    # PASS 2: Deduct dispatches, automatically routing inconsistent lot links via FIFO
    for row in raw_data:
        if row["entry_type"].strip().lower() == "outward":
            part = row["part_number"].strip().upper()
            qty = int(row["qty_nos"])
            ref_lot_str = row["ref_challan_no"].strip().upper()
            
            # Log dispatch securely on global metrics tracking lines
            if part in global_stock:
                global_stock[part]["outward"] += qty
                
            allocated_qty = qty
            
            # Sub-Path A: Check for a clear single lot match
            if ref_lot_str not in ["NO-REF", "SELF", "NONE"] and "&" not in ref_lot_str:
                lot_key = (part, ref_lot_str)
                if lot_key in lot_stock:
                    lot_stock[lot_key]["outward"] += allocated_qty
                    allocated_qty = 0
            
            # Sub-Path B: FIFO Routing for composite records containing ampersands, typos, or "NO-REF"
            if allocated_qty > 0:
                for lot_key in inward_sequence:
                    if lot_key[0] == part: # Match by Part Number
                        available_in_batch = lot_stock[lot_key]["inward"] - lot_stock[lot_key]["outward"]
                        
                        if available_in_batch >= allocated_qty:
                            lot_stock[lot_key]["outward"] += allocated_qty
                            allocated_qty = 0
                            break
                        elif available_in_batch > 0:
                            lot_stock[lot_key]["outward"] += available_in_batch
                            allocated_qty -= available_in_batch
                
                # If an outward entry exceeds all known inward records, log the remainder to a virtual overflow row
                if allocated_qty > 0:
                    overflow_key = (part, "UNASSIGNED OVERFLOW")
                    if overflow_key not in lot_stock:
                        lot_stock[overflow_key] = {"description": row["description"].strip().upper(), "inward": 0, "outward": 0, "date": row["date"]}
                    lot_stock[overflow_key]["outward"] += allocated_qty

    # 4. Render Consolidated Global Balances Section Table
    st.subheader("📋 Consolidated Global Part Balances")
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
    st.dataframe(pd.DataFrame(global_rows), use_container_width=True)
    
    st.markdown("---")
    
    # 5. Formulate Structured Dataframes for Traceability Matrices and Colorful Charting
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
            lot_label = f"{part} ({lot_id})"
            chart_rows.append({"Lot Reference": lot_label, "Metric Type": "Delivered Shipped (Nos)", "Quantity": details["outward"]})
            chart_rows.append({"Lot Reference": lot_label, "Metric Type": "Remaining WIP Stock (Nos)", "Quantity": display_bal})
            
    df_lots = pd.DataFrame(lot_rows)
    df_chart = pd.DataFrame(chart_rows)
    
    # 6. Side-by-Side Table Matrix and Stacked Segment Chart Presentation Layout
    st.subheader("🔍 Lot-by-Lot Traceability Breakdown & Stock Allocation Chart")
    
    view_col1, view_col2 = st.columns([1.1, 0.9])
    
    with view_col1:
        st.markdown("**Live Ledger Inventory Matrix**")
        st.dataframe(df_lots, use_container_width=True, height=450)
        
    with view_col2:
        st.markdown("**Lot Allocation Segments (Shipped vs Remaining)**")
        if not df_chart.empty:
            chart_pivot = df_chart.pivot(index="Lot Reference", columns="Metric Type", values="Quantity").fillna(0)
            
            st.bar_chart(
                data=chart_pivot,
                color=["#29b573","#0068c9"], # Green = Shipped Outward | Blue = Remaining WIP Inventory
                use_container_width=True,
                height=420
            )
        else:
            st.info("No transaction tracking entries are available to plot allocation levels.")
else:
    st.info("No validated transaction entries are currently available to compute stock numbers.")
