# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 1 (VIEW ROUTING & DATE MATH TOOLS)
# ============================================================================

import streamlit as st
import pandas as pd
import requests
import json
import io
import re  
import datetime
import calendar
from dateutil.relativedelta import relativedelta
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# 🛰️ Secure Secret Credentials Resolution Routing
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except Exception as e:
    st.error("❌ Missing Infrastructure Secrets Configuration inside Settings.")
    st.stop()

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

@st.cache_data(ttl=2)
def fetch_unified_attendance_ledger():
    """Queries the newly deployed public.v_attendance_ledger Supabase view"""
    endpoint = f"{SUPABASE_URL.strip('/')}/rest/v1/v_attendance_ledger?order=month_year.desc,employee_id.asc"
    try:
        response = requests.get(endpoint, headers=HEADERS)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception:
        return []

def update_db_payment_status(employee_id, month_year, new_status):
    """Performs transactional REST PATCH to persist updated payment state down to the Supabase feed table layer"""
    endpoint = f"{SUPABASE_URL.strip('/')}/rest/v1/raw_attendance_feed?employee_id=eq.{employee_id}&month_year=eq.{month_year}"
    payload = {"payment_status": new_status}
    try:
        res = requests.patch(endpoint, headers=HEADERS, json=payload)
        # SYNTAX FIX: Successfully matches common REST patch completion standard codes
        return res.status_code in [200, 201, 204]
    except Exception:
        return False

def parse_row_date(month_year_str):
    """Maps custom string variations like 'September-2026' or '09-2026' to a proper datetime.date object"""
    if not month_year_str or str(month_year_str).strip() == "N/A":
        return None
    normalized = str(month_year_str).strip().replace("/", "-")
    year_match = re.search(r"\b(20\d{2})\b", normalized)
    year = int(year_match.group(1)) if year_match else datetime.date.today().year
    
    for m_idx in range(1, 13):
        full_name = calendar.month_name[m_idx].upper()
        short_name = calendar.month_abbr[m_idx].upper()
        if full_name in normalized.upper() or short_name in normalized.upper():
            return datetime.date(year, m_idx, 1)
            
    digits = re.findall(r"\b(\d{1,2})\b", normalized)
    for num_str in digits:
        m_val = int(num_str)
        if 1 <= m_val <= 12:
            return datetime.date(year, m_val, 1)
    return None

def get_days_in_month(month_year_str):
    """Extracts actual days available inside specific timeline string as an integer (e.g. 'Oct-2026')"""
    dt = parse_row_date(month_year_str)
    if dt:
        return int(calendar.monthrange(dt.year, dt.month)[1])
    return 31
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 2 (FILTERS ENGINE & COMPUTATION MATRIX)
# ============================================================================

# Load combined data from the Supabase view schema directly
view_records_data = fetch_unified_attendance_ledger()

if not view_records_data:
    st.info("📋 System Log: No integrated database rows found inside the v_attendance_ledger workspace view.")
else:
    # Calculate previous calendar month parameters automatically
    today = datetime.date.today()
    past_month_date = today - relativedelta(months=1)
    default_start = past_month_date.replace(day=1)
    default_end = past_month_date.replace(day=calendar.monthrange(past_month_date.year, past_month_date.month)[1])

    # Single calendar input widget setup
    chosen_dates = st.date_input(
        "Select Payout Month:",
        value=(default_start, default_end),
        key="main_graphical_calendar_picker"
    )

    if isinstance(chosen_dates, tuple) and len(chosen_dates) == 2:
        start_cal, end_cal = chosen_dates
    else:
        start_cal, end_cal = default_start, default_end

    # Search filter layout configs
    mat_col1, mat_col4 = st.columns(2)
    with mat_col1:
        search_mat_id = st.text_input("Filter by Employee ID:", "", key="mat_id_input").strip()
    with mat_col4:
        search_mat_status = st.selectbox("Filter by Employee Status:", options=["All Statuses", "Active Only", "In-Active Only"], key="mat_status_input")

    start_day, end_day = st.slider("Select Day Columns View Range:", min_value=1, max_value=31, value=(1, 31), key="mat_day_slider")

    # Processing array mapping loop
    processed_rows = []
    for item in view_records_data:
        m_yr = item.get("month_year") or "N/A"
        row_dt = parse_row_date(m_yr)
        
        # Filter rows by calendar input bounds
        if row_dt:
            if not (start_cal <= row_dt <= end_cal):
                continue
                
        def safe_float(val):
            if val is None or str(val).strip() == "" or str(val).lower() == "none": return 0.00
            try: return float(val)
            except: return 0.00

        # Sourced straight from unified view columns map
        total_hours_worked = safe_float(item.get("total_hours"))
        total_days_worked = safe_float(item.get("total_days"))
        base_monthly_comp = safe_float(item.get("base_monthly_comp"))
        configured_shift_hours = safe_float(item.get("shift_hours") or 12.00)
        current_status = item.get("employee_status") or "Active"
        days_list = item.get("attendance_days") or []
        
        # 🧮 IN-MEMORY CALCULATIONS Engine (Pure RAM Math allocations)
        total_minutes_worked = total_hours_worked * 60.0
        row_month_days = get_days_in_month(m_yr)
        
        if configured_shift_hours > 0:
            actual_days_worked = round(total_hours_worked / configured_shift_hours, 2)
        else:
            actual_days_worked = 0.00

        if current_status.upper() == "ACTIVE" and row_month_days > 0 and configured_shift_hours > 0:
            per_hour_rate = (base_monthly_comp / float(row_month_days)) / configured_shift_hours
            per_minute_rate = per_hour_rate / 60.0
            calculated_gross_payout = total_minutes_worked * per_minute_rate
        else:
            per_hour_rate = 0.00
            per_minute_rate = 0.00
            calculated_gross_payout = 0.00

        row_dict = {
            "Month_Year": m_yr,
            "EMP_ID": item.get("employee_id") or "N/A",
            "EMP_Name": item.get("employee_name") or "Unnamed",
            "Over_Time": safe_float(item.get("over_time")),
            "Less_Time": safe_float(item.get("less_time")),
            "Total_Hours": total_hours_worked,
            "Total_Minutes": total_minutes_worked,             # RAM Calculated Metric
            "Total_Days": total_days_worked,                   # Raw Days Sourced from DB
            "Actual_Days_Worked": actual_days_worked,           # RAM Calculated Proportional Metric
            "Start_Date": item.get("start_date") or "N/A",
            "Last_Date": item.get("last_day_of_work") or "N/A",
            "EMP_Status": current_status,
            "Base_Monthly_Comp": base_monthly_comp,
            "Rate_Per_Hour": per_hour_rate,                    # RAM Calculated Metric
            "Rate_Per_Minute": per_minute_rate,                # RAM Calculated Metric
            "Gross_Payout": calculated_gross_payout,           # RAM Calculated Metric
            "Payment_Status": item.get("payment_status") or "Pending",
            "DB_Show_Flag": item.get("show") if item.get("show") is not None else True
        }
        for day in range(1, 32):
            row_dict[f"D{day:02d}"] = days_list[day-1] if (days_list and day-1 < len(days_list)) else ""
        processed_rows.append(row_dict)
        
    df = pd.DataFrame(processed_rows)
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 3 (CALENDAR LAYOUTS & STABLE DATAFRAME GENERATION)
# ============================================================================

    # Calculate previous calendar month parameters automatically
    today = datetime.date.today()
    past_month_date = today - relativedelta(months=1)
    default_start = past_month_date.replace(day=1)
    default_end = past_month_date.replace(day=calendar.monthrange(past_month_date.year, past_month_date.month)[1])

    # Render unified date picker widget
    chosen_dates = st.date_input(
        "Select Payout Month:",
        value=(default_start, default_end),
        key="main_graphical_calendar_picker"
    )

    if isinstance(chosen_dates, tuple) and len(chosen_dates) == 2:
        start_cal, end_cal = chosen_dates
    else:
        start_cal, end_cal = default_start, default_end

    # Layout search strings filters
    mat_col1, mat_col4 = st.columns(2)
    with mat_col1:
        search_mat_id = st.text_input("Filter by Employee ID:", "", key="mat_id_input").strip()
    with mat_col4:
        search_mat_status = st.selectbox("Filter by Employee Status:", options=["All Statuses", "Active Only", "In-Active Only"], key="mat_status_input")

    start_day, end_day = st.slider("Select Day Columns View Range:", min_value=1, max_value=31, value=(1, 31), key="mat_day_slider")

    # Rebuild processing arrays cleanly in-memory
    processed_rows = []
    for item in view_records_data:
        m_yr = item.get("month_year") or "N/A"
        row_dt = parse_row_date(m_yr)
        
        if row_dt:
            if not (start_cal <= row_dt <= end_cal):
                continue
                
        days_list = item.get("attendance_days") or []
        emp_id_str = str(item.get("employee_id") or "").strip().upper()
        
        def safe_float(val):
            if val is None or str(val).strip() == "" or str(val).lower() == "none": return 0.00
            try: return float(val)
            except: return 0.00

        base_monthly_comp = safe_float(item.get("base_monthly_comp"))
        configured_shift_hours = safe_float(item.get("shift_hours") or 8.00)
        current_status = item.get("employee_status") or "Active"
        
        # 🛡️ THE CRITICAL PIECE: Ignore corrupted DB totals, force clean in-memory reconstruction
        total_hours_worked, total_days_present, actual_days_worked = process_workforce_metrics_from_tokens(days_list, configured_shift_hours)
        
        total_minutes_worked = total_hours_worked * 60.0
        row_month_days = get_days_in_month(m_yr)

        # Payroll metric rate logic executions
        if current_status.upper() == "ACTIVE" and row_month_days > 0 and configured_shift_hours > 0:
            per_hour_rate = (base_monthly_comp / float(row_month_days)) / configured_shift_hours
            per_minute_rate = per_hour_rate / 60.0
            calculated_gross_payout = total_minutes_worked * per_minute_rate
        else:
            per_hour_rate = 0.00
            per_minute_rate = 0.00
            calculated_gross_payout = 0.00

        row_dict = {
            "Month_Year": m_yr, 
            "EMP_ID": item.get("employee_id") or "N/A", 
            "EMP_Name": item.get("employee_name") or "Unnamed",
            "Over_Time": safe_float(item.get("over_time")), 
            "Less_Time": safe_float(item.get("less_time")),
            "Total_Hours": total_hours_worked, 
            "Total_Minutes": total_minutes_worked, 
            "Total_Days": total_days_present,                  # True Count of raw days present
            "Actual_Days_Worked": actual_days_worked,           # Correct Proportional Allocation Metric
            "Start_Date": item.get("start_date") or "N/A",
            "Last_Date": item.get("last_day_of_work") or "N/A", 
            "EMP_Status": current_status,
            "Base_Monthly_Comp": base_monthly_comp, 
            "Rate_Per_Hour": per_hour_rate, 
            "Rate_Per_Minute": per_minute_rate,
            "Gross_Payout": calculated_gross_payout,
            "Payment_Status": item.get("payment_status") or "Pending", 
            "DB_Show_Flag": item.get("show") if item.get("show") is not None else True
        }
        for day in range(1, 32):
            row_dict[f"D{day:02d}"] = days_list[day-1] if (days_list and day-1 < len(days_list)) else ""
        processed_rows.append(row_dict)
        
    df = pd.DataFrame(processed_rows)
