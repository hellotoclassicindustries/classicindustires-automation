# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 1 OF 3 (ENDPOINTS & UNRESTRICTED POOLS)
# ============================================================================

import streamlit as st
import pandas as pd
import requests
import datetime
import json

# 🛰️ Secure Secret Credentials Resolution Routing
SUPABASE_URL = st.secrets.get("SUPABASE_BASE_URL", "https://supabase.co")
SUPABASE_KEY = st.secrets.get("SUPABASE_ANON_KEY", "YOUR_ANON_KEY")
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

@st.cache_data(ttl=2) # 2-second responsive cache for rapid sync turnaround loops
def fetch_raw_attendance_feed():
    """Fetches full attendance matrix from Supabase without restrictive filters"""
    endpoint = f"{SUPABASE_URL.strip('/')}/rest/v1/raw_attendance_feed?order=month_year.desc,employee_id.asc"
    try:
        response = requests.get(endpoint, headers=HEADERS)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception:
        return []

@st.cache_data(ttl=60)
def fetch_cntr_employee_master():
    """Queries production employee metadata profile registries"""
    endpoint = f"{SUPABASE_URL.strip('/')}/rest/v1/cntr_employee_master"
    try:
        response = requests.get(endpoint, headers=HEADERS)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception:
        return []

def execute_database_row_patch(record_id, verification_decision):
    """Updates verification choices and dynamic timestamps on the remote table"""
    endpoint = f"{SUPABASE_URL.strip('/')}/rest/v1/raw_attendance_feed?id=eq.{record_id}"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if verification_decision == "Del":
        payload = {
            "show": False,
            "sync_status": f"flagged to delete + {timestamp}"
        }
    else:
        payload = {
            "show": True,
            "sync_status": f"Success ✅ ({timestamp})"
        }
        
    try:
        response = requests.patch(endpoint, headers=HEADERS, json=payload)
        # ✔️ PRODUCTION REPAIR FIXED: Restored complete status list verification criteria
        return response.status_code in [200, 201, 204]
    except Exception:
        return False
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 2 OF 3 (MAPPING & FILTERS)
# ============================================================================

# Interface Layout Header Initialization
st.title("📋 Enterprise Attendance Ledger Dashboard")
st.markdown("Filter, track, verify, and monitor rolling month-wise employee shift parameters using live production profile streams.")

# Load Datasets from Supabase Production Pools
raw_attendance_data = fetch_raw_attendance_feed()
master_emp_data = fetch_cntr_employee_master()

# Compile Employee Profile Metadata Map directly from cntr_employee_master (Key: employee_id)
emp_metadata_map = {}
for emp in master_emp_data:
    emp_id = emp.get("employee_id")
    if emp_id:
        emp_metadata_map[str(emp_id).strip()] = {
            "start_date": emp.get("start_date", "N/A"),
            "last_day_of_work": emp.get("last_day_of_work", "N/A"),
            "employee_status": emp.get("employee_status", "Active"),
            "contact": emp.get("contact", "N/A")
        }

if not raw_attendance_data:
    st.info("📋 System Log: No data rows found inside public.raw_attendance_feed table space.")
else:
    processed_rows = []
    available_months_list = set()
    
    for item in raw_attendance_data:
        days_list = item.get("attendance_days") or []
        
        # Safe-decode JSON string representations of day matrix lists if needed
        if isinstance(days_list, str):
            try:
                days_list = json.loads(days_list)
            except:
                days_list = []
                
        m_yr = item.get("month_year", "N/A")
        available_months_list.add(m_yr)
        emp_id_str = str(item.get("employee_id", "")).strip()
        
        # Link metadata profiles from cntr_employee_master table space dynamically
        meta = emp_metadata_map.get(emp_id_str, {"start_date": "N/A", "last_day_of_work": "N/A", "employee_status": "Active", "contact": "N/A"})
        
        # Dynamic float parser intercepts empty string values gracefully
        def safe_float(val):
            if val is None or str(val).strip() == "":
                return 0.00
            try:
                return float(val)
            except:
                return 0.00

        row_dict = {
            "Action_Gate": "Review",
            "Month_Year": m_yr,
            "EMP_ID": item.get("employee_id"),
            "EMP_Name": item.get("employee_name"),
            "Over_Time": safe_float(item.get("over_time")),
            "Less_Time": safe_float(item.get("less_time")),
            "Total_Hours": safe_float(item.get("total_hours")),
            "Total_Days": safe_float(item.get("total_days")),
            "Start_Date": meta["start_date"],
            "Last_Date": meta["last_day_of_work"],
            "EMP_Status": meta["employee_status"],
            "Contact_Info": meta["contact"],
            "File_Origin": item.get("source_filename"),
            "DB_ID": item.get("id"),
            "DB_Show_Flag": item.get("show") if item.get("show") is not None else True
        }
        
        # Unpack absolute 31 days horizontally with length guards
        for day in range(1, 32):
            day_str = f"D{day:02d}"
            row_dict[day_str] = days_list[day-1] if (days_list and day-1 < len(days_list)) else ""
            
        processed_rows.append(row_dict)
        
    df = pd.DataFrame(processed_rows)

    # ============================================================================
    # 🎛️ CONTROL PANEL FILTERS INTERFACE SECTION
    # ============================================================================
    st.sidebar.header("🔍 Filter Parameters")
    
    # Toggle switch options to filter across your custom database status criteria
    view_mode = st.sidebar.selectbox(
        "Select Dataset Visibility Mode:",
        options=["Show Active Records Only (show = true)", "Show Removed Records Only (show = false)", "Show All Records (Combined)"]
    )
    
    selected_months = st.sidebar.multiselect(
        "Select Time Frame (Month_Year):",
        options=sorted(list(available_months_list)),
        default=sorted(list(available_months_list))
    )
    
    search_emp_id = st.sidebar.text_input("Search Employee ID:", "").strip()
    search_emp_name = st.sidebar.text_input("Search Employee Name:", "").strip()
    
    # Apply Visibility View Mode Filters
    if view_mode == "Show Active Records Only (show = true)":
        filtered_df = df[df["DB_Show_Flag"] == True]
    elif view_mode == "Show Removed Records Only (show = false)":
        filtered_df = df[df["DB_Show_Flag"] == False]
    else:
        filtered_df = df.copy()
        
    # Apply Time Frame and Text Filters
    filtered_df = filtered_df[filtered_df["Month_Year"].isin(selected_months)]
    
    if search_emp_id:
        filtered_df = filtered_df[filtered_df["EMP_ID"].astype(str).str.contains(search_emp_id, case=False, na=False)]
    if search_emp_name:
        filtered_df = filtered_df[filtered_df["EMP_Name"].astype(str).str.contains(search_emp_name, case=False, na=False)]
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 3 OF 3 (METRICS & FUTURE-PROOF LEDGER)
# ============================================================================

    # ============================================================================
    # 📊 EXECUTIVE KPI SCOPE INFOGRAPHIC REVEAL
    # ============================================================================
    st.markdown("### 📈 Filtered Workspace Summary Metrics")
    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
    
    with metric_col1:
        st.metric("Total Days Logged", f"{filtered_df['Total_Days'].sum():.1f} Days")
    with metric_col2:
        st.metric("Total Productive Hours", f"{filtered_df['Total_Hours'].sum():.2f} Hrs")
    with metric_col3:
        st.metric("Accumulated Over_Time", f"{filtered_df['Over_Time'].sum():.2f} Hrs")
    with metric_col4:
        st.metric("Accumulated Less_Time", f"{filtered_df['Less_Time'].sum():.2f} Hrs")

    # ============================================================================
    # 📋 ATTENDANCE FORMAT DATAGRID EDIT PANEL
    # ============================================================================
    st.markdown("### 🖥️ Main Interactive Attendance Ledger")
    st.caption("Double-click Action Selection cell properties to verify rows ('Yes' / 'Del') directly to database tables.")

    # Re-order array layers into standard attendance grid view layout matching clean styles
    grid_columns_order = (
        ["Action_Gate", "Month_Year", "EMP_ID", "EMP_Name"] + 
        [f"D{d:02d}" for d in range(1, 32)] + 
        ["Over_Time", "Less_Time", "Total_Hours", "Total_Days", "Start_Date", "Last_Date", "EMP_Status", "Contact_Info", "File_Origin", "DB_ID"]
    )
    filtered_df = filtered_df[grid_columns_order]

    # Disable all fields except Action Selection column to maintain mathematical integrity
    columns_to_disable = [c for c in grid_columns_order if c != "Action_Gate"]

    # Setup cell width restrictions to prevent horizontal table text explosions
    cfg = {
        "Action_Gate": st.column_config.SelectboxColumn("Action", options=["Review", "Yes", "Del"], required=True, width="small"),
        "Month_Year": st.column_config.TextColumn("Month_Year", width="small"),
        "EMP_ID": st.column_config.TextColumn("EMP ID", width="small"),
        "EMP_Name": st.column_config.TextColumn("Employee Name", width="medium"),
        "Over_Time": st.column_config.NumberColumn("Extra Hrs", format="%.2f", width="small"),
        "Less_Time": st.column_config.NumberColumn("Short Hrs", format="%.2f", width="small"),
        "Total_Hours": st.column_config.NumberColumn("Total Hrs", format="%.2f", width="small"),
        "Total_Days": st.column_config.NumberColumn("Total Days", format="%.1f", width="small"),
        "DB_ID": st.column_config.NumberColumn("DB ID", format="%d", width="small")
    }
    
    # Enforce clear uniform width for the 31 calendar columns
    for day_idx in range(1, 32):
        cfg[f"D{day_idx:02d}"] = st.column_config.TextColumn(f"{day_idx:02d}", width=50)

    # Future-proof width specification removes deprecation logs
    edited_df = st.data_editor(
        filtered_df,
        hide_index=True,
        disabled=columns_to_disable,
        width="stretch",
        column_config=cfg
    )

    # ============================================================================
    # 💾 BATCH DECISION COMMITS TRIGGER BLOCK
    # ============================================================================
    if st.button("💾 Commit Ledger Updates & Sync To Supabase", type="primary"):
        save_counter = 0
        
        for index, row in edited_df.iterrows():
            selected_action = row["Action_Gate"]
            record_db_id = row["DB_ID"]
            
            if selected_action in ["Yes", "Del"]:
                success = execute_database_row_patch(record_db_id, selected_action)
                if success:
                    save_counter += 1
                    
        if save_counter > 0:
            st.success(f"🎉 Successfully synchronized {save_counter} attendance rows changes directly into Supabase tables!")
            st.cache_data.clear() # Evict temporary memory footprints
            st.rerun()
        else:
            st.warning("📋 No updates detected. Switch specific row Action Selections to 'Yes' or 'Del' before saving.")
