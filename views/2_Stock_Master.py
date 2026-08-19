import streamlit as st
import pandas as pd
from supabase import create_client, Client

# Initialize Secure Supabase Target Connections
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

def fetch_raw_ledger_payload():
    """
    Fetches raw transactional parameters from your Supabase backend.
    """
    try:
        response = supabase.table("staging_ledger") \
            .select("part_number, description, entry_type, ref_challan_no, challan_no, qty_nos") \
            .eq("is_validated", True) \
            .execute()
        return response.data
    except Exception as e:
        st.error(f"Error fetching database values: {str(e)}")
        return []

# Set up Dashboard Grid Layout Presentation
st.set_page_config(page_title="ClassicIndustries | Stock Master", layout="wide")
st.title("📦 Live Work-In-Progress (WIP) Stock Master")
st.markdown("---")

raw_data = fetch_raw_ledger_payload()

if raw_data:
    # 1. Initialize data dictionaries for grouping
    global_stock = {} # Maps Part Number -> Total Warehouse Summary
    lot_stock = {}    # Maps (Part Number, Lot ID) -> Granular History Tracking Matrices

    # 2. Process all incoming inventory lots to establish baseline figures
    for row in raw_data:
        part = row["part_number"].strip().upper()
        desc = row["description"].strip().upper()
        qty = int(row["qty_nos"])
        
        if row["entry_type"].strip().lower() == "inward":
            lot_id = row["challan_no"].strip().upper()  # Inward lot number
            
            # Global Stock Map Setup
            if part not in global_stock:
                global_stock[part] = {"description": desc, "inward": 0, "outward": 0}
            global_stock[part]["inward"] += qty
            
            # Lot-by-Lot Stock Map Setup
            lot_key = (part, lot_id)
            if lot_key not in lot_stock:
                lot_stock[lot_key] = {"description": desc, "inward": 0, "outward": 0}
            lot_stock[lot_key]["inward"] += qty

    # 3. Process dispatches and execute adaptive fallback tracking for "NO-REF" rows
    for row in raw_data:
        if row["entry_type"].strip().lower() == "outward":
            part = row["part_number"].strip().upper()
            qty = int(row["qty_nos"])
            ref_lot = row["ref_challan_no"].strip().upper()
            
            # Record dispatch count on global metric tracks
            if part in global_stock:
                global_stock[part]["outward"] += qty
            
            # Record dispatch count on lot metric tracks
            if ref_lot != "NO-REF" and ref_lot != "SELF":
                lot_key = (part, ref_lot)
                if lot_key not in lot_stock:
                    lot_stock[lot_key] = {"description": row["description"].strip().upper(), "inward": 0, "outward": 0}
                lot_stock[lot_key]["outward"] += qty
            else:
                # HYBRID ADAPTIVE FALLBACK RULE: Deduct from oldest available matching lot pool
                allocated_qty = qty
                for (lot_part, lot_id) in lot_stock.keys():
                    if lot_part == part:
                        available_in_lot = lot_stock[(lot_part, lot_id)]["inward"] - lot_stock[(lot_part, lot_id)]["outward"]
                        if available_in_lot >= allocated_qty:
                            lot_stock[(lot_part, lot_id)]["outward"] += allocated_qty
                            allocated_qty = 0
                            break
                        elif available_in_lot > 0:
                            lot_stock[(lot_part, lot_id)]["outward"] += available_in_lot
                            allocated_qty -= available_in_lot
                
                # If "NO-REF" volume exceeds all active matching pools, place remainder on global tracker fallback
                if allocated_qty > 0 and part in global_stock:
                    virtual_key = (part, "UNASSIGNED OVERFLOW")
                    if virtual_key not in lot_stock:
                        lot_stock[virtual_key] = {"description": row["description"].strip().upper(), "inward": 0, "outward": 0}
                    lot_stock[virtual_key]["outward"] += allocated_qty

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
    df_chart = pd.DataFrame(chart_rows) # FIX: Directly maps to clean, variable-independent chart data list
    
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
                color=["#ff4b4b", "#0068c9"], # Red = Shipped Outward | Blue = Remaining WIP Inventory
                use_container_width=True,
                height=420
            )
        else:
            st.info("No transaction tracking entries are available to plot allocation levels.")
else:
    st.info("No validated transaction entries are currently available to compute stock numbers.")
