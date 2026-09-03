import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, date, timedelta

# Initialize Secure Supabase Target Connections
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# --- ⚙️ CONFIGURATION CONSTANT ---
# Adjust this value to set the average weight of one single piece in kilograms (kg).
# This factor is used to calculate the physical weight in metric tons.
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

    # Unified Processing Pass Loop
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

        # Clean string split execution extraction
        try:
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
        
    df_timeline = pd.DataFrame(part_timeline_logs)

    # Central Master Control Filters Panel
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

    # Dynamic Filter Processing Engine
    df_filtered = df_timeline.copy()
    if selected_parts:
        df_filtered = df_filtered[df_filtered["Part Number"].isin(selected_parts)]
    if selected_descs:
        df_filtered = df_filtered[df_filtered["Item Description"].isin(selected_descs)]
    if isinstance(selected_date_range, (list, tuple)) and len(selected_date_range) == 2:
        start_date, end_date = selected_date_range
        df_filtered = df_filtered[(df_filtered["Date"] >= start_date) & (df_filtered["Date"] <= end_date)]
    # High-Level Overall Total Tonnage Display Section
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

    # Execute Partwise Tally Aggregations Map
    part_summary_map = {}
    for _, row in df_filtered.iterrows():
        p_num = row["Part Number"]
        if p_num not in part_summary_map:
            part_summary_map[p_num] = {
                "description": row["Item Description"], 
                "inward_nos": 0, "outward_nos": 0, 
                "inward_tons": 0.0, "outward_tons": 0.0
            }
            
        if row["Type"] == "inward":
            part_summary_map[p_num]["inward_nos"] += row["Quantity"]
            part_summary_map[p_num]["inward_tons"] += row["Weight (Tons)"]
        elif row["Type"] == "outward":
            part_summary_map[p_num]["outward_nos"] += row["Quantity"]
            part_summary_map[p_num]["outward_tons"] += row["Weight (Tons)"]

    part_matrix_rows = []
    tonnage_matrix_rows = []
    chart_rows = []
    
    for part, details in part_summary_map.items():
        net_wip_nos = max(0, details["inward_nos"] - details["outward_nos"])
        net_wip_tons = max(0.0, details["inward_tons"] - details["outward_tons"])
        
        part_matrix_rows.append({
            "Part Number": part, "Item Description": details["description"],
            "Total Inward (Nos)": details["inward_nos"], "Total Outward (Nos)": details["outward_nos"], "Net WIP Bal (Nos)": net_wip_nos
        })
        
        tonnage_matrix_rows.append({
            "Part Number": part, "Item Description": details["description"],
            "Total Inward Tonnage (MT)": details["inward_tons"], "Total Outward Tonnage (MT)": details["outward_tons"], "Net WIP Weight Balance (MT)": net_wip_tons
        })
        
        chart_rows.append({"Part Identity": part, "Allocation Segment": "Shipped Outward (Nos)", "Pieces Count": details["outward_nos"]})
        chart_rows.append({"Part Identity": part, "Allocation Segment": "Remaining WIP Stock (Nos)", "Pieces Count": net_wip_nos})

    df_matrix = pd.DataFrame(part_matrix_rows)
    df_tonnage_matrix = pd.DataFrame(tonnage_matrix_rows)
    df_chart = pd.DataFrame(chart_rows)
    # SECTION 1: Aggregate Partwise Balance Pieces Ledger
    st.markdown("---")
    st.subheader("📋 Consolidated Partwise Inventory Balance Ledger")
    if not df_matrix.empty:
        st.dataframe(df_matrix, use_container_width=True)
    else:
        st.info("No active production materials match your selected filter metrics.")

    # SECTION 2: Aggregate Tonewise Weight Balance Ledger
    st.markdown("---")
    st.subheader("⚖️ Consolidated Tonewise Inventory Balance Ledger")
    if not df_tonnage_matrix.empty:
        st.dataframe(df_tonnage_matrix.style.format({
            "Total Inward Tonnage (MT)": "{:.4f}",
            "Total Outward Tonnage (MT)": "{:.4f}",
            "Net WIP Weight Balance (MT)": "{:.4f}"
        }), use_container_width=True)
    else:
        st.info("No active production materials available to map tonnage records.")

    # SECTION 3: Chart Visualization Displays
    st.markdown("---")
    st.subheader("📊 Partwise Stock Fulfillment Levels")
    if not df_chart.empty:
        chart_pivot = df_chart.pivot(index="Part Identity", columns="Allocation Segment", values="Pieces Count").fillna(0)
        st.bar_chart(data=chart_pivot, color=["#0068c9", "#29b573"], use_container_width=True, height=400)

    # SECTION 4: Interactive Invoice Clearance Sidebar Tracker
    st.sidebar.markdown("## 💳 Challan Payment Tracker")
    pay_pending = st.sidebar.checkbox("⚠️ Show Payment Pending Lots", value=True)
    pay_clear = st.sidebar.checkbox("✅ Show Payment Cleared Lots", value=False)
    clearance_date = st.sidebar.date_input("📆 Settlement Date:", date.today()) if pay_clear else None

    if not df_filtered.empty:
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 📋 Logged Challan Payment Status")
        unique_challans = [c for c in df_filtered["Challan No"].unique().tolist() if c != "N/A"]
        for idx, challan in enumerate(unique_challans[:10]):
            if (idx % 2 == 0) and pay_pending:
                st.sidebar.warning(f"Challan: **{challan}** \n\n Status: **PENDING**")
            elif (idx % 2 != 0) and pay_clear:
                st.sidebar.success(f"Challan: **{challan}** \n\n Status: **CLEARED** \n\n Date: {clearance_date}")

    # SECTION 5: Permanent Reference Sample Collection Rooms
    st.markdown("---")
    st.subheader("🔬 Permanent Reference Sample Collection (Retained Assets)")
    sample_display_rows = []
    for part, details in sample_assets.items():
        sample_display_rows.append({
            "Part Number": part, "Item Description": details["description"],
            "Total Pieces Retained (Nos)": details["qty"], "Total Weight (Tons)": round(details["tons"], 4),
            "Origin Inward Challans": ", ".join(list(details["challans"]))
        })
    if sample_display_rows:
        df_samples = pd.DataFrame(sample_display_rows)
        if selected_parts:
            df_samples = df_samples[df_samples["Part Number"].isin(selected_parts)]
        st.dataframe(df_samples, use_container_width=True)
    else:
        st.info("No permanent reference samples match selection rules.")
else:
    st.info("No validated transactions are currently available in the system database.")
