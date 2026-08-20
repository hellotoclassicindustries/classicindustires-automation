import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, date, timedelta

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
st.title("📦 Partwise WIP Balance & Fulfillment Dashboard")
st.markdown("---")

raw_data = fetch_raw_ledger_payload()

if raw_data:
    # 1. Initialize data registries for clean partwise grouping arrays
    part_timeline_logs = []
    sample_assets = {}

    # 2. Unified Pass: Process transaction blocks and completely isolate samples based STRICTLY on text notes
    for row in raw_data:
        part = str(row["part_number"]).strip().upper()
        desc = str(row["description"]).strip().upper()
        qty = int(row["qty_nos"])
        remarks = str(row["remarks_notes"]).strip().upper()
        entry_type = row["entry_type"].strip().lower()
        
        # 🔬 STRICT TEXT REMARKS GATING RULE:
        # Relies 100% on the explicit written label "SAMPLE" inside your remarks/notes context.
        # Quantity loops are completely ignored here to ensure structural accuracy across historical logs.
        is_sample = ("SAMPLE" in remarks or "SAMPLE" in part or "SAMPLE" in desc)
        
        if is_sample:
            lot_id = row["challan_no"].strip().upper() if entry_type == "inward" else "RETAINED"
            if part not in sample_assets:
                sample_assets[part] = {"description": desc, "qty": 0, "challans": set()}
            sample_assets[part]["qty"] += qty
            sample_assets[part]["challans"].add(lot_id)
            continue # Isolates verified samples from active production stock immediately
            
        # Log all valid items (including PTO parts and single pieces) into production tracks
        try:
            row_date = datetime.strptime(str(row["date"]).split(" ").strip(), "%Y-%m-%d").date()
        except:
            row_date = date.today()

        part_timeline_logs.append({
            "Date": row_date,
            "Part Number": part,
            "Item Description": desc,
            "Type": entry_type,
            "Quantity": qty
        })
        
    df_timeline = pd.DataFrame(part_timeline_logs)

    # 🎛️ CENTRAL EMBEDDED FILTER PANEL (DEFAULTED TO LAST 1 WEEK WINDOW)
    st.subheader("🔍 Master Performance Tally Query Panel")
    st.markdown("_Select your options below to filter all inventory metrics, grids, and chart displays collectively:_")
    
    f_col1, f_col2, f_col3 = st.columns(3)
    with f_col1:
        unique_parts = sorted(df_timeline["Part Number"].unique().tolist()) if not df_timeline.empty else []
        selected_parts = st.multiselect("🔢 Filter by Specific Part Numbers:", options=unique_parts, placeholder="All Active SKUs")
    with f_col2:
        unique_descs = sorted(df_timeline["Item Description"].unique().tolist()) if not df_timeline.empty else []
        selected_descs = st.multiselect("⚙️ Filter by Component Descriptions:", options=unique_descs, placeholder="All Descriptions")
    with f_col3:
        # TIMELINE DEFAULT LOCK: Evaluates current date and locks the past 7 days automatically
        current_run_date = date.today()
        default_start_date = current_run_date - timedelta(days=7)
        selected_date_range = st.date_input("📆 Select Transaction Evaluation Window:", [default_start_date, current_run_date])

    # ⚡ APPLY SELECTIONS TO HIGH-VOLUME RUNNING FRAMES
    df_filtered = df_timeline.copy()

    if selected_parts:
        df_filtered = df_filtered[df_filtered["Part Number"].isin(selected_parts)]
    if selected_descs:
        df_filtered = df_filtered[df_filtered["Item Description"].isin(selected_descs)]
        
    if isinstance(selected_date_range, (list, tuple)) and len(selected_date_range) == 2:
        start_date, end_date = selected_date_range
        df_filtered = df_filtered[(df_filtered["Date"] >= start_date) & (df_filtered["Date"] <= end_date)]

    # 🧮 EXECUTE PARTWISE RUNNING TALLY AGGREGATIONS
    part_summary_map = {}
    for _, row in df_filtered.iterrows():
        p_num = row["Part Number"]
        p_desc = row["Item Description"]
        p_type = row["Type"]
        p_qty = row["Quantity"]
        
        if p_num not in part_summary_map:
            part_summary_map[p_num] = {"description": p_desc, "inward": 0, "outward": 0}
            
        if p_type == "inward":
            part_summary_map[p_num]["inward"] += p_qty
        elif p_type == "outward":
            part_summary_map[p_num]["outward"] += p_qty

    # Formulate clean presentation dataframes for full-width grid plotting
    part_matrix_rows = []
    chart_rows = []
    
    for part, details in part_summary_map.items():
        net_wip_bal = details["inward"] - details["outward"]
        display_wip = max(0, net_wip_bal)
        
        part_matrix_rows.append({
            "Part Number": part,
            "Item Description": details["description"],
            "Total Inward Received (Nos)": details["inward"],
            "Total Shipped Outward (Nos)": details["outward"],
            "Net Available WIP Balance": display_wip
        })
        
        # Log clean metrics parameters to populate the double-colored stacked bar graph
        chart_rows.append({"Part Identity": part, "Allocation Segment": "Shipped Outward (Nos)", "Pieces Count": details["outward"]})
        chart_rows.append({"Part Identity": part, "Allocation Segment": "Remaining WIP Stock (Nos)", "Pieces Count": display_wip})

    df_matrix = pd.DataFrame(part_matrix_rows)
    df_chart = pd.DataFrame(chart_rows)

    # 📋 SECTION 1: Aggregate Partwise Available Stocks Matrix Ledger
    st.markdown("---")
    st.subheader("📋 Consolidated Partwise Inventory Balance Ledger")
    if not df_matrix.empty:
        st.dataframe(df_matrix, use_container_width=True)
    else:
        st.info("No active production materials match your selected filter timeline metrics.")

    # 📊 SECTION 2: Full-Width Stacked Allocation Chart (Part Identity Base)
    st.markdown("---")
    st.subheader("📊 Partwise Stock Fulfillment Levels (Shipped vs Remaining Balance)")
    if not df_chart.empty:
        chart_pivot = df_chart.pivot(index="Part Identity", columns="Allocation Segment", values="Pieces Count").fillna(0)
        st.bar_chart(
            data=chart_pivot, 
            color=["#0068c9", "#29b573"], # Blueprint Blue = Shipped Outward | Clean Green = Remaining WIP Stock
            use_container_width=True, 
            height=400
        )
    else:
        st.info("No transaction tracking entries are available within this timeline to map visualization graphs.")

    # 🔬 SECTION 3: Permanent Reference Sample Collection (Retained Assets Room)
    st.markdown("---")
    st.subheader("🔬 Permanent Reference Sample Collection (Retained Assets)")
    sample_display_rows = []
    for part, details in sample_assets.items():
        sample_display_rows.append({
            "Part Number": part,
            "Item Description": details["description"],
            "Total Pieces Retained (Nos)": details["qty"],
            "Origin Inward Challans": ", ".join(list(details["challans"]))
        })
    if sample_display_rows:
        df_samples = pd.DataFrame(sample_display_rows)
        if selected_parts:
            df_samples = df_samples[df_samples["Part Number"].isin(selected_parts)]
        st.dataframe(df_samples, use_container_width=True)
    else:
        st.info("No permanent reference samples are currently logged in the facility archives.")
else:
    st.info("No validated transaction entries are currently available to compute stock numbers.")
