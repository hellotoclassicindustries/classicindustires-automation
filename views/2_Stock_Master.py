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
    global_stock = {} # Maps Part Number -> Total Remaining Physical Pieces
    lot_stock = {}    # Maps (Part Number, Lot ID) -> Remaining Pieces in that specific lot

    # 2. First Pass: Process all incoming inventory lots to build our baseline numbers
    for row in raw_data:
        part = row["part_number"].strip().upper()
        desc = row["description"].strip().upper()
        qty = int(row["qty_nos"])
        
        if row["entry_type"].strip().lower() == "inward":
            lot_id = row["challan_no"].strip().upper()  # Inward lot number (Fix: Python Comment)
            
            # Update the global pool counts
            if part not in global_stock:
                global_stock[part] = {"description": desc, "available": 0}
            global_stock[part]["available"] += qty
            
            # Update single lot tracking numbers
            lot_key = (part, lot_id)
            if lot_key not in lot_stock:
                lot_stock[lot_key] = {"description": desc, "available": 0}
            lot_stock[lot_key]["available"] += qty

    # 3. Second Pass: Process dispatches and handle "NO-REF" logic paths safely via hybrid fallback
    for row in raw_data:
        if row["entry_type"].strip().lower() == "outward":
            part = row["part_number"].strip().upper()
            qty = int(row["qty_nos"])
            ref_lot = row["ref_challan_no"].strip().upper()
            
            # Subtract from our global physical stock count
            if part in global_stock:
                global_stock[part]["available"] -= qty
            
            # Deduct from single lot stocks based on reference availability
            if ref_lot != "NO-REF" and ref_lot != "SELF":
                lot_key = (part, ref_lot)
                if lot_key in lot_stock:
                    lot_stock[lot_key]["available"] -= qty
            else:
                # HYBRID ADAPTIVE FALLBACK RULE: Deduct from oldest available matching part lot (Fix: Python Comment)
                for (lot_part, lot_id) in lot_stock.keys():
                    if lot_part == part and lot_stock[(lot_part, lot_id)]["available"] >= qty:
                        lot_stock[(lot_part, lot_id)]["available"] -= qty
                        break

    # 4. Render Consolidated Global Balances Section
    st.subheader("📋 Consolidated Global Part Balances")
    global_rows = []
    for part, details in global_stock.items():
        global_rows.append({
            "Part Number": part,
            "Item Description": details["description"],
            "Net Available Stock (Nos)": max(0, details["available"])
        })
    st.dataframe(pd.DataFrame(global_rows), use_container_width=True)
    
    st.markdown("---")
    
    # 5. Formulate Dataframe for Lot-by-Lot Traceability & Graphs
    lot_rows = []
    chart_data_rows = []
    
    for (part, lot_id), details in lot_stock.items():
        available_balance = max(0, details["available"])
        
        lot_rows.append({
            "Part Number": part,
            "Inward Lot Identity": lot_id,
            "Item Description": details["description"],
            "Lot Remaining WIP Balance": available_balance
        })
        
        # Format a clean string name for the chart labels
        if available_balance > 0:
            chart_data_rows.append({
                "Lot Reference": f"{part} ({lot_id})",
                "Available Stock": available_balance
            })
            
    df_lots = pd.DataFrame(lot_rows)
    df_chart = pd.DataFrame(chart_data_rows)
    
    # 6. Render Side-by-Side Table and Bar Chart Section using Columns Layout
    st.subheader("🔍 Lot-by-Lot Traceability Breakdown & Stock Allocation Chart")
    
    view_col1, view_col2 = st.columns([1.1, 0.9])
    
    with view_col1:
        st.markdown("**Live Ledger Inventory Matrix**")
        st.dataframe(df_lots, use_container_width=True, height=400)
        
    with view_col2:
        st.markdown("**Lot Remaining WIP Balance Levels**")
        if not df_chart.empty:
            st.bar_chart(
                data=df_chart,
                x="Lot Reference",
                y="Available Stock",
                color="#0068c9",
                use_container_width=True
            )
        else:
            st.info("All scanned component lots have been fully exhausted. Graph is empty.")
else:
    st.info("No validated transaction entries are currently available to compute stock numbers.")
