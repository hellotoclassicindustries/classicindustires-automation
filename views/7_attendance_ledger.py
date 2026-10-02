import streamlit as st
import pandas as pd
import requests
import datetime

# ============================================================================
# ⚙️ SECURE ENDPOINT CREDENTIALS ROUTING
# ============================================================================
SUPABASE_URL = st.secrets.get("SUPABASE_BASE_URL", "https://supabase.co")
SUPABASE_KEY = st.secrets.get("SUPABASE_ANON_KEY", "YOUR_ANON_KEY")
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

@st.cache_data(ttl=60)
def fetch_raw_attendance_feed():
    """Fetches verified matrix inputs out of public.raw_attendance_feed"""
    endpoint = f"{SUPABASE_URL.strip('/')}/rest/v1/raw_attendance_feed?show=eq.true&order=month_year.desc,employee_id.asc"
    try:
        res = requests.get(endpoint, headers=HEADERS)
        return res.json() if res.status_code == 200 else []
    except Exception:
        return []

@st.cache_data(ttl=60)
def fetch_cntr_employee_master():
    """Queries profile registry out of public.cntr_employee_master"""
    endpoint = f"{SUPABASE_URL.strip('/')}/rest/v1/cntr_employee_master?show=eq.true"
    try:
        res = requests.get(endpoint, headers=HEADERS)
        return res.json() if res.status_code == 200 else []
    except Exception:
        return []

def execute_database_row_patch(record_id, decision_token):
    """Commits supervisor processing updates directly to Supabase"""
    endpoint = f"{SUPABASE_URL.strip('/')}/rest/v1/raw_attendance_feed?id=eq.{record_id}"
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    payload = {
        "show": False,
        "sync_status": f"flagged to delete + {ts}"
    } if decision_token == "Del" else {
        "sync_status": f"Success ✅ ({ts})"
    }
    try:
        response = requests.patch(endpoint, headers=HEADERS, json=payload)
        return response.status_code in [200, 201, 204]
    except Exception:
        return False

# ============================================================================
# 🖥️ CORE STREAMLIT USER INTERFACE LAYOUT (COMPACT METRICS SPECIFICATION)
# ============================================================================
st.title("📋 Employee Attendance Ledger")
st.markdown("Filter, verify, and monitor rolling month-wise employee shift parameters.")

# Initialize background data connections
raw_feed = fetch_raw_attendance_feed()
master_profiles = fetch_cntr_employee_master()

# Map employee profile metrics cleanly (Key: employee_id)
meta_map = {}
for emp in master_profiles:
    eid = emp.get("employee_id")
    if eid:
        meta_map[str(eid).strip()] = {
            "start": emp.get("start_date", "N/A"),
            "last": emp.get("last_day_of_work", "N/A"),
            "status": emp.get("employee_status", "Active"),
            "contact": emp.get("contact", "N/A")
        }

if not raw_feed:
    st.info("📋 Staging Queue Is Empty: No verified rows are pending check processes.")
else:
    processed_rows = []
    months_set = set()
    
    for item in raw_feed:
        days = item.get("attendance_days", [])
        m_yr = item.get("month_year", "N/A")
        months_set.add(m_yr)
        emp_id = str(item.get("employee_id", "")).strip()
        
        # Intercept metadata configurations from cntr_employee_master dynamically
        m_data = meta_map.get(emp_id, {"start": "N/A", "last": "N/A", "status": "Active", "contact": "N/A"})
        
        row = {
            "Action": "Review",
            "Month_Year": m_yr,
            "EMP_ID": item.get("employee_id"),
            "EMP_Name": item.get("employee_name"),
            "Over_Time": float(item.get("over_time")) if item.get("over_time") else 0.0,
            "Less_Time": float(item.get("less_time")) if item.get("less_time") else 0.0,
            "Total_Hours": float(item.get("total_hours")) if item.get("total_hours") else 0.0,
            "Total_Days": float(item.get("total_days")) if item.get("total_days") else 0.0,
            "Start_Date": m_data["start"],
            "Last_Date": m_data["last"],
            "Status": m_data["status"],
            "Contact": m_data["contact"],
            "File": item.get("source_filename"),
            "ID": item.get("id")
        }
        
        for d in range(1, 32):
            row[f"D{d:02d}"] = days[d-1] if d-1 < len(days) else ""
            
        processed_rows.append(row)
        
    base_df = pd.DataFrame(processed_rows)

    # ============================================================================
    # 🎛️ SIDEBAR PARAMETERS FILTER MODULES
    # ============================================================================
    st.sidebar.header("🔍 Filter Parameters")
    selected_months = st.sidebar.multiselect("Time Frame:", options=sorted(list(months_set)), default=sorted(list(months_set)))
    search_id = st.sidebar.text_input("Search Employee ID:", "").strip()
    search_name = st.sidebar.text_input("Search Employee Name:", "").strip()
    
    # Filter array sweeps matching sidebar conditions
    f_df = base_df[base_df["Month_Year"].isin(selected_months)]
    if search_id:
        f_df = f_df[f_df["EMP_ID"].astype(str).str.contains(search_id, case=False, na=False)]
    if search_name:
        f_df = f_df[f_df["EMP_Name"].astype(str).str.contains(search_name, case=False, na=False)]

    # ============================================================================
    # 📈 COMPACT EXECUTIVE KPI BANNER PANEL
    # ============================================================================
    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    m_col1.metric("Total Days Logged", f"{f_df['Total_Days'].sum():.1f} Days")
    m_col2.metric("Productive Hours", f"{f_df['Total_Hours'].sum():.2f} Hrs")
    m_col3.metric("Over_Time Sum", f"{f_df['Over_Time'].sum():.2f} Hrs")
    m_col4.metric("Less_Time Sum", f"{f_df['Less_Time'].sum():.2f} Hrs")

    # ============================================================================
    # 🖥️ VERIFIED DATA GRID DESIGN PATH (COMPACT COLUMN CONFIGURATIONS)
    # ============================================================================
    col_order = (
        ["Action", "Month_Year", "EMP_ID", "EMP_Name"] + 
        [f"D{d:02d}" for d in range(1, 32)] + 
        ["Over_Time", "Less_Time", "Total_Hours", "Total_Days", "Start_Date", "Last_Date", "Status", "Contact", "File", "ID"]
    )
    f_df = f_df[col_order]
    
    # Setup cell width restrictions to prevent horizontal table breaks
    cfg = {
        "Action": st.column_config.SelectboxColumn("Action", options=["Review", "Yes", "Del"], required=True, width="small"),
        "Month_Year": st.column_config.TextColumn("Month_Year", width="small"),
        "EMP_ID": st.column_config.TextColumn("EMP ID", width="small"),
        "EMP_Name": st.column_config.TextColumn("Employee Name", width="medium"),
        "Over_Time": st.column_config.NumberColumn("Extra Hrs", format="%.2f", width="small"),
        "Less_Time": st.column_config.NumberColumn("Short Hrs", format="%.2f", width="small"),
        "Total_Hours": st.column_config.NumberColumn("Total Hrs", format="%.2f", width="small"),
        "Total_Days": st.column_config.NumberColumn("Total Days", format="%.1f", width="small"),
        "ID": st.column_config.NumberColumn("DB ID", format="%d", width="small")
    }
    
    # Enforce strict 50-pixel width cell boxes down calendar columns D01-D31
    for day_idx in range(1, 32):
        cfg[f"D{day_idx:02d}"] = st.column_config.TextColumn(f"{day_idx:02d}", width=50)

    disabled_cols = [c for c in col_order if c != "Action"]

    edited_df = st.data_editor(
        f_df,
        hide_index=True,
        disabled=disabled_cols,
        use_container_width=True,
        column_config=cfg
    )

    # ============================================================================
    # 💾 BATCH SUBMIT PROCESSING QUEUE COMMAND RULES
    # ============================================================================
    if st.button("💾 Commit Ledger Updates & Sync To Supabase", type="primary"):
        saves = 0
        for _, r in edited_df.iterrows():
            act = r["Action"]
            db_id = r["ID"]
            if act in ["Yes", "Del"]:
                if execute_database_row_patch(db_id, act):
                    saves += 1
                    
        if saves > 0:
            st.success(f"🎉 Successfully synchronized {saves} attendance rows directly inside Supabase!")
            st.cache_data.clear()
            st.rerun()
        else:
            st.warning("📋 No updates detected. Switch specific row Actions to 'Yes' or 'Del' before clicking commit.")
