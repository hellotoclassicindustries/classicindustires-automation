import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, date, timedelta

# Initialize Secure Supabase Target Connections
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# --- ⚙️ CONFIGURATION CONSTANT ---
# Set the average weight of one single piece in kilograms (kg) here.
PIECE_WEIGHT_KG = 0.5  

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
st.title("📦 Partwise WIP Balance & Fulfillment Dashboard")
st.markdown("---")

raw_data = fetch_raw_ledger_payload()

if raw_data:
    part_timeline_logs = []
    sample_assets = {}

    # Unified Processing Loop
    for row in raw_data:
        part = str(row["part_number"]).strip().upper()
        desc = str(row["description"]).strip().upper()
        qty = int(row["qty_nos"])
        entry_type = row["entry_type"].strip().lower()
        
        # Calculate Tonnage (Pieces * Weight in kg / 1000)
        weight_tons = round((qty * PIECE_WEIGHT_KG) / 1000.0, 4)
        
        # Isolate permanent reference sample room assets
        is_strict_sample = (entry_type == "inward" and qty == 1)
        if is_strict_sample:
            part_upper = part.upper()
            lot_id = str(row["challan_no"]).strip().upper() if row["challan_no"] else "UNKNOWN"
            
            if part_upper not in sample_assets:
                sample_assets[part_upper] = {"description": f"{desc}-SAMPLE", "qty": 0, "tons": 0.0, "challans": set()}
            sample_assets[part_upper]["qty"] += qty
            sample_assets[part_upper]["tons"] += weight_tons
            sample_assets[part_upper]["challans"].add(lot_id)
            continue 

        try:
            # Safely parse date formats
            clean_date_str = str(row["date"]).split(" ")[0].strip()
            row_date = datetime.strptime(clean_date_str, "%Y-%m-%d").date()
        except:
            row_date = date.today()

        part_timeline_logs.append({
            "Date": row_date, 
            "Part Number": part, 
            "Item Description": desc,
            "Type": entry_type, 
            "Quantity": qty, 
            "Weight (Tons)": weight_tons,
            "Challan No": str(row["challan_no"]).strip().upper() if row["challan_no"] else "N/A"
        })
           # Dashboard Control Filters Layer Panel
    st.subheader("🔍 Master Performance Tally Query Panel")
    f_col1, f_col2, f_col3 = st.columns(3)
    with f_col1:
        unique_parts = sorted(df_timeline["Part Number"].unique().tolist()) if not df_timeline.empty else []
        selected_parts = st.multiselect("🔢 Filter by Specific Part Numbers:", options=unique_parts, placeholder="All Active SKUs")
    with f_col2:
        unique_descs = sorted(df_timeline["Item Description"].unique().tolist()) if not df_timeline.empty else []
        selected_descs = st.multiselect("⚙️ Filter by Component Descriptions:", options=unique_descs, placeholder="All Descriptions")
    with f_col3:
        current_run_date = date.today()
        default_start_date = current_run_date - timedelta(days=7)
        selected_date_range = st.date_input("📆 Select Evaluation Window:", [default_start_date, current_run_date])

    # Execute Engine Filtering Rule Set Logic
    df_filtered = df_timeline.copy()
    if selected_parts:
        df_filtered = df_filtered[df_filtered["Part Number"].isin(selected_parts)]
    if selected_descs:
        df_filtered = df_filtered[df_filtered["Item Description"].isin(selected_descs)]
    if isinstance(selected_date_range, (list, tuple)) and len(selected_date_range) == 2:
        start_date, end_date = selected_date_range
        df_filtered = df_filtered[(df_filtered["Date"] >= start_date) & (df_filtered["Date"] <= end_date)]

    # ⚖️ OVERALL TOTAL TONNAGE METRIC CARDS LAYER
    st.markdown("---")
    st.subheader("⚖️ Overall Tonnage Summary (All Selected Items)")
    
    if not df_filtered.empty:
        total_tons_inward = df_filtered[df_filtered["Type"] == "inward"]["Weight (Tons)"].sum()
        total_tons_outward = df_filtered[df_filtered["Type"] == "outward"]["Weight (Tons)"].sum()
        net_tons_wip = max(0.0, total_tons_inward - total_tons_outward)
        
        m_col1, m_col2, m_col3 = st.columns(3)
        m_col1.metric(label="Overall Total Tons Inward", value=f"{total_tons_inward:.4f} MT")
        m_col2.metric(label="Overall Total Tons Outward", value=f"{total_tons_outward:.4f} MT")
        m_col3.metric(label="Overall Net WIP Tons Balance", value=f"{net_tons_wip:.4f} MT")
    else:
        st.info("No transaction data available inside filter choices to calculate weights.")
 
    df_timeline = pd.DataFrame(part_timeline_logs)
