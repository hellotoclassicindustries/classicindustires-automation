import streamlit as st
import pandas as pd
from supabase import create_client, Client

url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

def fetch_raw_ledger_payload():
    try:
        response = supabase.table("staging_ledger") \
            .select("part_number, description, entry_type, ref_challan_no, challan_no, qty_nos") \
            .eq("is_validated", True) \
            .execute()
        return response.data
    except Exception as e:
        st.error(f"Error fetching database values: {str(e)}")
        return []

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
            lot_id = row["challan_no"].strip().upper() # Inward lot number
            
            # Update the global pool counts
            if part not in global_stock:
                global_stock[part] = {"description": desc, "available": 0}
            global_stock[part]["available"] += qty
            
            # Update single lot tracking numbers
            lot_key = (part, lot_id)
            if lot_key not in lot_stock:
                lot_stock[lot_key] = {"description": desc, "available": 0}
            lot_stock[lot_key]["available"] += qty

    # 3. Second Pass: Process dispatches and handle "NO-REF" logic paths safely
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
                # 💡 HYBRID ADAPTIVE FALLBACK RULE: 
                # If an item is marked "NO-REF", the code avoids lot lockouts.
                # It automatically finds the oldest active inward lot for that part number 
                # and subtracts the quantity from there to keep your batch records straight.
                for (lot_part, lot_id) in lot_stock.keys():
                    if lot_part == part and lot_stock[(lot_part, lot_id)]["available"] >= qty:
                        lot_stock[(lot_part, lot_id)]["available"] -= qty
                        break

    # 4. Format and display data tables on screen
    st.subheader("📋 Consolidated Global Part Balances")
    global_rows = []
    for part, details in global_stock.items():
        global_rows.append({
            "Part Number": part,
            "Item Description": details["description"],
            "Net Available Stock (Nos)": details["available"]
        })
    st.dataframe(pd.DataFrame(global_rows), use_container_width=True)
    
    st.markdown("---")
    st.subheader("🔍 Lot-by-Lot Traceability Breakdown")
    lot_rows = []
    for (part, lot_id), details in lot_stock.items():
        lot_rows.append({
            "Part Number": part,
            "Inward Lot Identity": lot_id,
            "Item Description": details["description"],
            "Lot Remaining WIP Balance": details["available"]
        })
    st.dataframe(pd.DataFrame(lot_rows), use_container_width=True)
else:
    st.info("No validated transaction entries are currently available to compute stock numbers.")
