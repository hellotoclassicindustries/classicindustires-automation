# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 1 OF 3 (READ-ONLY CORE INFRASTRUCTURE)
# ============================================================================

import streamlit as st
import pandas as pd
import requests
import datetime
import json

# 🛰️ Secure Secret Credentials Resolution Routing
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except Exception as e:
    st.error("❌ Missing Infrastructure Secrets Configuration inside Streamlit Dashboard settings.")
    st.stop()

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

@st.cache_data(ttl=5) # Responsive cache for rapid reporting turnaround checks
def fetch_raw_attendance_feed():
    """Fetches full attendance matrix tracking data from public.raw_attendance_feed"""
    endpoint = f"{SUPABASE_URL.strip('/')}/rest/v1/raw_attendance_feed?order=month_year.desc,employee_id.asc"
    try:
        response = requests.get(endpoint, headers=HEADERS)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception:
        return []

@st.cache_data(ttl=15)
def fetch_cntr_employee_master():
    """Queries current master workforce profile metrics from public.cntr_employee_master"""
    endpoint = f"{SUPABASE_URL.strip('/')}/rest/v1/cntr_employee_master?order=employee_id.asc"
    try:
        response = requests.get(endpoint, headers=HEADERS)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception:
        return []
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 2 OF 3 (CALENDAR SLIDER & FEED GRID)
# ============================================================================

st.title("📋 Enterprise Attendance & Workforce Analytics Console")
st.markdown("Monitor rolling month-wise employee shift parameters, calendar duration windows, and active roster records.")

# Load Raw Datasets from Synced Production Pools
raw_attendance_data = fetch_raw_attendance_feed()
master_emp_data = fetch_cntr_employee_master()

# Compile Employee Profile Metadata Map (Key: employee_id)
emp_metadata_map = {}
for emp in master_emp_data:
    emp_id = emp.get("employee_id")
    if emp_id:
        emp_metadata_map[str(emp_id).strip().upper()] = {
            "start_date": emp.get("start_date") or "N/A",
            "last_day_of_work": emp.get("last_day_of_work") or "N/A",
            "employee_status": emp.get("employee_status") or "Active",
            "show_flag": emp.get("show", True)
        }

if not raw_attendance_data:
    st.info("📋 System Log: No staging rows found inside public.raw_attendance_feed table space.")
else:
    processed_rows = []
    available_months_list = set()
    
    for item in raw_attendance_data:
        days_list = item.get("attendance_days") or []
        if isinstance(days_list, str):
            try: days_list = json.loads(days_list)
            except: days_list = []
                
        m_yr = item.get("month_year") or "N/A"
        available_months_list.add(m_yr)
        emp_id_str = str(item.get("employee_id") or "").strip().upper()
        
        meta = emp_metadata_map.get(emp_id_str, {"start_date": "N/A", "last_day_of_work": "N/A", "employee_status": "Active"})
        
        def safe_float(val):
            if val is None or str(val).strip() == "" or str(val).lower() == "none": return 0.00
            try: return float(val)
            except: return 0.00

        row_dict = {
            "Month_Year": m_yr,
            "EMP_ID": item.get("employee_id") or "N/A",
            "EMP_Name": item.get("employee_name") or "Unnamed",
            "Over_Time": safe_float(item.get("over_time")),
            "Less_Time": safe_float(item.get("less_time")),
            "Total_Hours": safe_float(item.get("total_hours")),
            "Total_Days": safe_float(item.get("total_days")),
            "Start_Date": meta.get("start_date", "N/A"),
            "Last_Date": meta.get("last_day_of_work", "N/A"),
            "EMP_Status": meta.get("employee_status", "Active"),
            "DB_Show_Flag": item.get("show") if item.get("show") is not None else True
        }
        
        for day in range(1, 32):
            row_dict[f"D{day:02d}"] = days_list[day-1] if (days_list and day-1 < len(days_list)) else ""
            
        processed_rows.append(row_dict)
        
    df = pd.DataFrame(processed_rows)

    # ============================================================================
    # 🎛️ SIDEBAR PARAMETER FILTERS INTERFACE SECTION
    # ============================================================================
    st.sidebar.header("🔍 Global Search Filters")
    
    selected_months = st.sidebar.multiselect(
        "Filter Time Frame (Month_Year):",
        options=sorted(list(available_months_list)),
        default=sorted(list(available_months_list))
    )
    
    search_emp_id = st.sidebar.text_input("Filter Employee ID (Attendance Grid):", "").strip()
    search_emp_name = st.sidebar.text_input("Filter Employee Name (Attendance Grid):", "").strip()
    
    # 🗓️ DURATION WINDOW CALENDAR SLIDER FILTER RULE
    st.sidebar.markdown("---")
    st.sidebar.subheader("📅 Day Duration Truncation")
    start_day, end_day = st.sidebar.slider(
        "Select Calendar Duration (Days Interval Bounds):",
        min_value=1, max_value=31, value=(1, 31)
    )

    # Apply core multi-conditional tracking masks
    filtered_df = df[df["DB_Show_Flag"] == True]
    if len(selected_months) > 0:
        filtered_df = filtered_df[filtered_df["Month_Year"].isin(selected_months)]
    if search_emp_id:
        filtered_df = filtered_df[filtered_df["EMP_ID"].astype(str).str.contains(search_emp_id, case=False, na=False)]
    if search_emp_name:
        filtered_df = filtered_df[filtered_df["EMP_Name"].astype(str).str.contains(search_emp_name, case=False, na=False)]

    # Generate truncated sliding day sequence headers dynamically based on slider selection
    selected_day_cols = [f"D{d:02d}" for d in range(start_day, end_day + 1)]

    # Re-order array grid mapping layout paths
    grid_columns_order = (
        ["Month_Year", "EMP_ID", "EMP_Name"] + 
        selected_day_cols + 
        ["Over_Time", "Less_Time", "Total_Hours", "Total_Days", "Start_Date", "Last_Date", "EMP_Status"]
    )
    filtered_df = filtered_df[grid_columns_order]

    # Display KPI Score Metrics Cards Summary panel
    st.markdown("### 📈 Attendance Summary Calculations Panel")
    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
    metric_col1.metric("Total Days Logged", f"{filtered_df['Total_Days'].sum():.1f} Days")
    metric_col2.metric("Total Productive Hours", f"{filtered_df['Total_Hours'].sum():.2f} Hours")
    metric_col3.metric("Accumulated Over_Time", f"{filtered_df['Over_Time'].sum():.2f} Hours")
    metric_col4.metric("Accumulated Less_Time", f"{filtered_df['Less_Time'].sum():.2f} Hours")

    st.markdown("### 🖥️ Main Historical Attendance Matrix Ledger")
    cfg = {
        "Month_Year": st.column_config.TextColumn("Month_Year", width="small"),
        "EMP_ID": st.column_config.TextColumn("EMP ID", width="small"),
        "EMP_Name": st.column_config.TextColumn("Employee Name", width="medium"),
        "Over_Time": st.column_config.NumberColumn("Extra Hrs", format="%.2f", width="small"),
        "Less_Time": st.column_config.NumberColumn("Short Hrs", format="%.2f", width="small"),
        "Total_Hours": st.column_config.NumberColumn("Total Hrs", format="%.2f", width="small"),
        "Total_Days": st.column_config.NumberColumn("Total Days", format="%.1f", width="small")
    }
    for d_col in selected_day_cols:
        cfg[d_col] = st.column_config.TextColumn(d_col.replace("D", ""), width=45)

    st.dataframe(filtered_df, hide_index=True, width="stretch", column_config=cfg)
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 3 OF 3 (ACTIVE WORKFORCE REGISTRY PANEL)
# ============================================================================

st.markdown("---")
st.markdown("### 👥 Active Employee Master Registry Directory")
st.markdown("View core operational metadata records and profile details imported directly from your human resources profiles.")

if not master_emp_data:
    st.warning("⚠️ Profile Link Alert: No workforce profile data entries located inside public.cntr_employee_master.")
else:
    # Build a clean dataframe specifically for your workforce roster profile sheets
    master_rows_list = []
    for emp in master_emp_data:
        if emp.get("show") is False: continue # Filter out completely deleted accounts
        
        master_rows_list.append({
            "Roster_Status": emp.get("employee_status") or "Active",
            "EMP_ID": emp.get("employee_id") or "N/A",
            "Employee_Name": emp.get("employee_name") or "Unnamed",
            "Shift_Hours": float(emp.get("shift_hours")) if emp.get("shift_hours") else 12.00,
            "Start_Onboarding_Date": emp.get("start_date") or "N/A",
            "Last_Day_Worked": emp.get("last_day_of_work") or "N/A",
            "Contact_Number": emp.get("contact") or "N/A",
            "ID_Proof_Details": emp.get("id_proof") or "N/A",
            "Monthly_Compensation": float(emp.get("comp_monthly")) if emp.get("comp_monthly") else 0.00
        })
        
    master_df = pd.DataFrame(master_rows_list)
    
    # 🔍 SEPARATE WORKFORCE MASTER ROW LOOKUP COMPONENT SEARCH FILTERS
    dir_col1, dir_col2, dir_col3 = st.columns(3)
    with dir_col1:
        search_dir_id = st.text_input("Filter Directory by Employee ID:", "", key="dir_id_input").strip()
    with dir_col2:
        search_dir_name = st.text_input("Filter Directory by Employee Name:", "", key="dir_name_input").strip()
    with dir_col3:
        search_dir_status = st.selectbox("Filter Directory by Profile Status:", options=["All Profiles", "Active Only", "In-Active Only"])
        
    # Execute Roster Directory layout filters array mutations
    if search_dir_id:
        master_df = master_df[master_df["EMP_ID"].astype(str).str.contains(search_dir_id, case=False, na=False)]
    if search_dir_name:
        master_df = master_df[master_df["Employee_Name"].astype(str).str.contains(search_dir_name, case=False, na=False)]
        
    if search_dir_status == "Active Only":
        master_df = master_df[master_df["Roster_Status"].str.upper() == "ACTIVE"]
    elif search_dir_status == "In-Active Only":
        master_df = master_df[master_df["Roster_Status"].str.upper() == "IN-ACTIVE"]
        
    # Display the directory spreadsheet container panel layout
    dir_cfg = {
        "Roster_Status": st.column_config.TextColumn("Roster Status", width="small"),
        "EMP_ID": st.column_config.TextColumn("EMP ID", width="small"),
        "Employee_Name": st.column_config.TextColumn("Employee Name", width="medium"),
        "Shift_Hours": st.column_config.NumberColumn("Scheduled Shift (Hrs)", format="%.2f", width="small"),
        "Monthly_Compensation": st.column_config.NumberColumn("Compensation", format="₹%.2f", width="small")
    }
    
    st.dataframe(master_df, hide_index=True, width="stretch", column_config=dir_cfg)
