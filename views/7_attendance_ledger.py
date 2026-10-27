# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY - PART 1
# PAYROLL & ATTENDANCE WORKFLOW (IMPORTS & CONFIGURATION)
# ============================================================================

import calendar
import datetime
import io
import math
import re
from xml.sax.saxutils import escape

import pandas as pd
import requests
import streamlit as st

from dateutil.relativedelta import relativedelta

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import (
    ParagraphStyle,
    getSampleStyleSheet,
)
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ============================================================================
# SUPABASE CONFIGURATION
# ============================================================================

try:
    SUPABASE_URL = str(st.secrets["SUPABASE_URL"]).strip().rstrip("/")
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except Exception:
    st.error("Missing SUPABASE_URL or SUPABASE_KEY in Streamlit secrets.")
    st.stop()

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY - PART 2
# GLOBAL HELPER FUNCTIONS
# ============================================================================

def safe_float(value, default=0.00):
    """Safely convert a value to float."""
    if value is None:
        return default
    if isinstance(value, bool):
        return float(value)
    try:
        text = str(value).strip()
        if not text:
            return default
        if text.lower() in {"none", "nan", "null"}:
            return default
        return float(text)
    except (TypeError, ValueError):
        return default


def money(value):
    """Format a numeric value as Indian currency."""
    return f"₹{safe_float(value):,.2f}"


def parse_row_date(value):
    """Convert flexible month-year text formats to unified dates."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() == "N/A":
        return None

    normalized = text.replace("/", "-").replace("_", "-")
    year_match = re.search(r"\b(20\d{2})\b", normalized)
    year = int(year_match.group(1)) if year_match else datetime.date.today().year
    upper_text = normalized.upper()

    for month_number in range(1, 13):
        full_name = calendar.month_name[month_number].upper()
        short_name = calendar.month_abbr[month_number].upper()
        if re.search(rf"\b{full_name}\b", upper_text) or re.search(rf"\b{short_name}\b", upper_text):
            return datetime.date(year, month_number, 1)

    numeric_values = re.findall(r"\b(\d{1,2})\b", normalized)
    for numeric_value in numeric_values:
        month_number = int(numeric_value)
        if 1 <= month_number <= 12:
            return datetime.date(year, month_number, 1)
    return None


def get_days_in_month(value):
    """Return the actual number of days in a month."""
    row_date = parse_row_date(value)
    if row_date:
        return calendar.monthrange(row_date.year, row_date.month)[1]
    return 31


def month_key_from_value(value):
    row_date = parse_row_date(value)
    return row_date.strftime("%Y-%m") if row_date else None


def make_adjustment_key(month_key, employee_id):
    return f"{month_key}:{str(employee_id)}"


def clean_text(value):
    return "" if value is None else str(value).strip()
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY - PART 3
# SUPABASE OPERATIONS & PDF GENERATION (WITH LIVE RELATIONAL PERSISTENCE)
# ============================================================================

@st.cache_data(ttl=2)
def fetch_vw_attendance_ledger():
    """Fetch attendance summary views from Supabase."""
    endpoint = f"{SUPABASE_URL}/rest/v1/vw_attendance_ledger?order=month_year.desc,employee_id.asc"
    try:
        response = requests.get(endpoint, headers=HEADERS, timeout=30)
        if response.status_code == 200:
            data = response.json()
            return data if isinstance(data, list) else []
        st.error(f"Attendance ledger request failed. HTTP {response.status_code}: {response.text}")
        return []
    except requests.RequestException as error:
        st.error(f"Unable to connect to Supabase: {error}")
        return []

def update_db_payment_status(employee_id, month_year, new_status):
    """Update payout transactional status fields in database."""
    endpoint = f"{SUPABASE_URL}/rest/v1/raw_attendance_feed?employee_id=eq.{employee_id}&month_year=eq.{month_year}"
    payload = {"payment_status": new_status}
    try:
        response = requests.patch(endpoint, headers=HEADERS, json=payload, timeout=30)
        return response.status_code in {200, 201, 204}
    except requests.RequestException:
        return False

# ----------------------------------------------------------------------------
# RELATIONAL PAYROLL ADJUSTMENTS DATABASE SYNC ENGINE
# ----------------------------------------------------------------------------

def save_db_payroll_adjustments_live(employee_id, month_key, type_label, qty, rate, payment, advance):
    """Upsert adjustment records securely into payroll_adjustments_live mapping to bigint FK."""
    endpoint = f"{SUPABASE_URL}/rest/v1/payroll_adjustments_live"
    
    # Locate the matching internal bigint serial ID from the active dataset row mapping
    internal_bigint_id = None
    for item in view_records_data:
        if str(item.get("employee_id")).strip() == str(employee_id).strip():
            internal_bigint_id = item.get("id")
            break

    if internal_bigint_id is None:
        st.error(f"✕ Verification Error: Could not locate internal relational database index for {employee_id}.")
        return False

    headers = HEADERS.copy()
    headers["Prefer"] = "resolution=merge-duplicates,return=representation"
    headers["On-Conflict"] = "employee_id,month_year"

    payload = {
        "employee_id": int(internal_bigint_id),  # Safely sends the exact bigint primary key index link
        "month_year": str(month_key),             # Passes exact checked YYYY-MM code string format
        "extra_work_type": str(type_label),
        "extra_work_quantity": float(qty),
        "extra_work_rate": float(rate),
        "rate_unit": "Fixed",
        "extra_work_payment": float(payment),
        "advance_given": float(advance),
        "adjustment_notes": "Processed automatically via Streamlit Live UI Console.",
        "adjustment_status": "Pending",
        "source_identifier": "STREAMLIT_LIVE_UI",
        "created_by": "STREAMLIT_USER"
    }

    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=30)
        return response.status_code in {200, 201, 204}
    except requests.RequestException:
        return False

def load_db_payroll_adjustments_live(month_key):
    """Fetch previously saved backend adjustment records for a given month key."""
    endpoint = f"{SUPABASE_URL}/rest/v1/payroll_adjustments_live?month_year=eq.{month_key}"
    try:
        response = requests.get(endpoint, headers=HEADERS, timeout=30)
        if response.status_code == 200:
            return response.json()
        return []
    except requests.RequestException:
        return []

# ----------------------------------------------------------------------------
# PDF LOGIC ENGINE
# ----------------------------------------------------------------------------

def generate_ledger_pdf(dataframe):
    """Compile multi-column dashboard values into printable PDFs."""
    if dataframe is None or dataframe.empty or len(dataframe.columns) == 0:
        return b""
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=landscape(letter),
        rightMargin=18, leftMargin=18, topMargin=25, bottomMargin=25
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("LedgerTitleStyle", parent=styles["Heading1"], fontSize=13, leading=16, textColor=colors.HexColor("#1A365D"))
    header_style = ParagraphStyle("LedgerHeaderStyle", parent=styles["Normal"], fontSize=5.5, leading=7, fontName="Helvetica-Bold", textColor=colors.white, alignment=TA_CENTER)
    cell_style = ParagraphStyle("LedgerCellStyle", parent=styles["Normal"], fontSize=5, leading=6.5, textColor=colors.black, alignment=TA_CENTER)

    story = [Paragraph("Payroll & Attendance Ledger", title_style), Spacer(1, 8)]
    columns = list(dataframe.columns)
    table_data = [[Paragraph(escape(str(column)), header_style) for column in columns]]

    for _, row in dataframe.iterrows():
        table_row = []
        for column in columns:
            value = row[column]
            value_text = "" if pd.isna(value) else (f"{value:.2f}" if isinstance(value, float) else str(value))
            table_row.append(Paragraph(escape(value_text), cell_style))
        table_data.append(table_row)

    column_count = len(columns)
    column_width = max(28, 756 / column_count)
    table = Table(table_data, colWidths=[column_width] * column_count, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2B6CB0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E0")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(table)
    document.build(story)
    buffer.seek(0)
    return buffer.getvalue()
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY - PART 4A (FIXED TUPLE UNPACKING)
# DATE FILTERS & RELATIONAL CACHE SYNCHRONIZATION
# ============================================================================

# ----------------------------------------------------------------------------
# 1. INITIAL BASELINE DATE & ATTENDANCE RECORD INITIALIZATION
# ----------------------------------------------------------------------------
view_records_data = fetch_vw_attendance_ledger()

if not view_records_data:
    st.info("No records were found in vw_attendance_ledger.")
    st.stop()

today = datetime.date.today()
previous_month = today - relativedelta(months=1)

default_start = previous_month.replace(day=1)

# FIXED: Appended [1] to extract only the actual number of days from the tuple
default_end = previous_month.replace(
    day=calendar.monthrange(previous_month.year, previous_month.month)[1]
)

st.header("📋 Payroll & Attendance Workflow")

chosen_dates = st.date_input(
    "Select Payout Month:",
    value=(default_start, default_end),
    key="attendance_month_range_picker",
)

if isinstance(chosen_dates, (tuple, list)):
    if len(chosen_dates) >= 2:
        start_cal, end_cal = chosen_dates[0], chosen_dates[1]
    elif len(chosen_dates) == 1:
        start_cal, end_cal = chosen_dates[0], chosen_dates[0]
    else:
        start_cal, end_cal = default_start, default_end
else:
    start_cal, end_cal = chosen_dates, chosen_dates

if start_cal > end_cal:
    start_cal, end_cal = end_cal, start_cal

selected_month_label = start_cal.strftime("%B %Y")
selected_month_key = start_cal.strftime("%Y-%m")  # Formatted as YYYY-MM

# FIXED: Appended [1] here as well to protect downstream math checks
selected_month_days = calendar.monthrange(start_cal.year, start_cal.month)[1]
if selected_month_days <= 0:
    selected_month_days = 31

# ----------------------------------------------------------------------------
# 2. SEED SESSION CACHE FROM DATABASE (MAPS RELATIONAL BIGINT BACK TO TEXT ID)
# ----------------------------------------------------------------------------
if "payroll_adjustments" not in st.session_state:
    st.session_state["payroll_adjustments"] = {}

if f"sync_done_{selected_month_key}" not in st.session_state:
    db_adjustments = load_db_payroll_adjustments_live(selected_month_key)
    if db_adjustments:
        for adj in db_adjustments:
            db_internal_id = adj.get("employee_id")
            
            ui_emp_id = None
            for item in view_records_data:
                if item.get("id") == db_internal_id:
                    ui_emp_id = str(item.get("employee_id"))
                    break
            
            if not ui_emp_id:
                continue
                
            adj_key = f"{selected_month_key}:{ui_emp_id}"
            
            st.session_state["payroll_adjustments"][adj_key] = {
                "entries": [{
                    "Particular": adj.get("extra_work_type", "Extra Earnings"),
                    "Quantity": float(adj.get("extra_work_quantity", 1.00)),
                    "Rate": float(adj.get("extra_work_rate", 0.00)),
                    "Extra_Amount": float(adj.get("extra_work_payment", 0.00))
                }],
                "advance_payment": float(adj.get("advance_given", 0.00)),
                "total_extra_amount": float(adj.get("extra_work_payment", 0.00))
            }
    st.session_state[f"sync_done_{selected_month_key}"] = True
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY - PART 4B
# INTERACTIVE DATA CONSOLE EDITOR & SECURE STORAGE CONTROLS
# ============================================================================

# ----------------------------------------------------------------------------
# 3. INTERACTIVE PAYROLL ADJUSTMENTS INTERFACE
# ----------------------------------------------------------------------------
adjustment_employee_options = {}

for item in view_records_data:
    item_month_key = month_key_from_value(item.get("month_year"))
    if item_month_key != selected_month_key:
        continue

    employee_id = str(item.get("employee_id") or "N/A")
    employee_name = item.get("employee_name") or "Unnamed"
    adjustment_employee_options[employee_id] = f"{employee_id} - {employee_name}"

st.markdown("---")
st.header("💰 Payroll Adjustments")
st.caption(f"Extra earnings and advance payments for {selected_month_label}")

if adjustment_employee_options:
    employee_ids = sorted(adjustment_employee_options.keys())

    selected_adjustment_employee = st.selectbox(
        "Select Employee:",
        options=employee_ids,
        format_func=lambda emp_id: adjustment_employee_options[emp_id],
        key="payroll_adjustment_employee",
    )

    current_adjustment_key = make_adjustment_key(selected_month_key, selected_adjustment_employee)

    saved_adjustment = st.session_state["payroll_adjustments"].get(
        current_adjustment_key,
        {"entries": [], "advance_payment": 0.00, "total_extra_amount": 0.00}
    )

    saved_entries = saved_adjustment.get("entries", [])
    entry_rows = []

    for saved_entry in saved_entries:
        entry_rows.append({
            "Particular": saved_entry.get("Particular", ""),
            "Quantity": safe_float(saved_entry.get("Quantity", 1.00)),
            "Rate": safe_float(saved_entry.get("Rate", 0.00)),
        })

    while len(entry_rows) < 5:
        entry_rows.append({"Particular": "", "Quantity": 1.00, "Rate": 0.00})

    adjustment_col1, adjustment_col2 = st.columns(2)

    with adjustment_col1:
        st.subheader("1. Extra Earning")
        st.caption("Add multiple entries. Each amount is Quantity × Rate.")

        extra_entries_df = st.data_editor(
            pd.DataFrame(entry_rows),
            hide_index=True,
            num_rows="dynamic",
            width="stretch",
            column_config={
                "Particular": st.column_config.TextColumn("1.a Particulars", help="Example: transport, loading, unloading"),
                "Quantity": st.column_config.NumberColumn("1.b Quantity / Hours", min_value=0.00, step=0.50, format="%.2f"),
                "Rate": st.column_config.NumberColumn("1.c Rate", min_value=0.00, step=1.00, format="₹%.2f")
            },
            key=f"extra_earning_entries_{selected_month_key}_{selected_adjustment_employee}",
        )

    with adjustment_col2:
        st.subheader("2. Advance Payment")
        st.caption("This amount is subtracted from gross payout.")

        advance_payment = st.number_input(
            "2. Advance Payment Amount",
            min_value=0.00,
            value=safe_float(saved_adjustment.get("advance_payment", 0.00)),
            step=100.00,
            format="%.2f",
            key=f"advance_payment_{selected_month_key}_{selected_adjustment_employee}",
        )

    cleaned_entries = []

    for _, entry in extra_entries_df.iterrows():
        particular = clean_text(entry.get("Particular", ""))
        quantity = safe_float(entry.get("Quantity", 0.00))
        rate = safe_float(entry.get("Rate", 0.00))

        if not particular and quantity <= 0 and rate <= 0:
            continue

        extra_amount = round(quantity * rate, 2)
        cleaned_entries.append({
            "Particular": particular,
            "Quantity": quantity,
            "Rate": rate,
            "Extra_Amount": extra_amount
        })

    total_extra_amount = round(sum(e["Extra_Amount"] for e in cleaned_entries), 2)
    net_adjustment = round(total_extra_amount - advance_payment, 2)

    total_col1, total_col2, total_col3 = st.columns(3)
    total_col1.metric("1.d Total Extra Amount", money(total_extra_amount))
    total_col2.metric("2. Advance Payment", money(advance_payment))
    total_col3.metric("Net Adjustment", money(net_adjustment))

    # ----------------------------------------------------------------------------
    # 4. DATABASE TRANSMISSION & UPSERT SUBMIT MECHANISM
    # ----------------------------------------------------------------------------
    if st.button("💾 Save Payroll Adjustments", key=f"save_payroll_adjustments_{selected_month_key}_{selected_adjustment_employee}"):
        aggregated_type_label = ", ".join([e["Particular"] for e in cleaned_entries if e["Particular"]]) or "Extra Duty Hours"
        
        with st.spinner("Saving adjustments securely to database table..."):
            db_success = save_db_payroll_adjustments_live(
                employee_id=selected_adjustment_employee,
                month_key=selected_month_key,
                type_label=aggregated_type_label,
                qty=1.00,
                rate=total_extra_amount,
                payment=total_extra_amount,
                advance=advance_payment
            )

        if db_success:
            st.session_state["payroll_adjustments"][current_adjustment_key] = {
                "entries": cleaned_entries,
                "advance_payment": round(advance_payment, 2),
                "total_extra_amount": total_extra_amount
            }
            st.success(f"✓ Adjustments permanently saved in database for employee ID {selected_adjustment_employee}.")
            st.cache_data.clear()
            st.rerun()
        else:
            st.error("✕ Database Save Error: Target employee mapping not verified or database connection failed.")
else:
    st.info(f"No employees are available for payroll adjustments in {selected_month_label}.")
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY - PART 5
# CORE PAYROLL CALCULATION ENGINE (REPAIRED)
# ============================================================================

st.markdown("---")
filter_col1, filter_col2, filter_col3 = st.columns(3)
search_employee_id = filter_col1.text_input("Filter by Employee ID:", key="employee_id_filter").strip()
search_employee_name = filter_col2.text_input("Filter by Employee Name:", key="employee_name_filter").strip()
status_filter = filter_col3.selectbox("Filter by Employee Status:", ["All Statuses", "Active Only", "In-Active Only"], key="employee_status_filter")

processed_rows = []
for item in view_records_data:
    month_year = item.get("month_year") or "N/A"
    row_date = parse_row_date(month_year)
    if row_date is not None and not (start_cal <= row_date <= end_cal):
        continue

    employee_id = str(item.get("employee_id") or "N/A")
    item_month_key = row_date.strftime("%Y-%m") if row_date else selected_month_key
    item_adjustment_key = make_adjustment_key(item_month_key, employee_id)

    employee_adjustment = st.session_state["payroll_adjustments"].get(item_adjustment_key, {"entries": [], "advance_payment": 0.00, "total_extra_amount": 0.00})
    total_extra_amount = safe_float(employee_adjustment.get("total_extra_amount", 0.00))
    advance_payment = safe_float(employee_adjustment.get("advance_payment", 0.00))

    total_hours_worked = safe_float(item.get("total_hours"))
    total_days_worked = safe_float(item.get("total_days"))
    base_monthly_comp = safe_float(item.get("base_monthly_comp"))
    shift_hours = max(1.00, safe_float(item.get("shift_hours"), default=8.00))

    employee_status = item.get("employee_status") or "Active"
    attendance_days = item.get("attendance_days") or []
    total_minutes_worked = round(total_hours_worked * 60.00, 2)
    month_days = get_days_in_month(month_year)
    actual_days_worked = round(total_hours_worked / shift_hours, 2)

    # REMOVED strict active-only logic step block checking flags to ensure that 
    # historical payout ledger totals populate accurately across row datasets.
    if month_days > 0 and shift_hours > 0:
        daily_allocation_rate = base_monthly_comp / month_days
        unrounded_hourly_rate = daily_allocation_rate / shift_hours
        hourly_rate = math.ceil(unrounded_hourly_rate * 100) / 100.00
        per_minute_rate = math.ceil((hourly_rate / 60.00) * 10000) / 10000.00
        gross_payout = round(total_hours_worked * hourly_rate, 2)
    else:
        hourly_rate, per_minute_rate, gross_payout = 0.00, 0.00, 0.00

    final_payout = round(gross_payout + total_extra_amount - advance_payment, 2)

    row_dict = {
        "Month_Year": month_year, "EMP_ID": employee_id, "EMP_Name": item.get("employee_name") or "Unnamed",
        "Over_Time": safe_float(item.get("over_time")), "Less_Time": safe_float(item.get("less_time")),
        "Total_Hours": total_hours_worked, "Total_Minutes": total_minutes_worked, "Total_Days": total_days_worked,
        "Actual_Days_Worked": actual_days_worked, "Start_Date": item.get("start_date") or "N/A",
        "Last_Date": item.get("last_day_of_work") or "N/A", "EMP_Status": employee_status,
        "Base_Monthly_Comp": base_monthly_comp, "Rate_Per_Hour": hourly_rate, "Rate_Per_Minute": per_minute_rate,
        "Gross_Payout": gross_payout, "Total_Extra_Amount": total_extra_amount, "Advance_Payment": advance_payment,
        "Final_Payout": final_payout, "Payment_Status": item.get("payment_status") or "Pending",
        "DB_Show_Flag": item.get("show") if item.get("show") is not None else True
    }

    for d in range(1, 32):
        row_dict[f"D{d:02d}"] = attendance_days[d - 1] if attendance_days and d - 1 < len(attendance_days) else ""
    processed_rows.append(row_dict)

df = pd.DataFrame(processed_rows)
if df.empty:
    st.warning("No attendance records match the selected month.")
    st.stop()
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY - PART 6
# DATA FILTRATION & LIVE DATA INTERACTIVE EDITOR GRID
# ============================================================================

filtered_df = df[df["DB_Show_Flag"] == True].copy()
if search_employee_id:
    filtered_df = filtered_df[filtered_df["EMP_ID"].astype(str).str.contains(search_employee_id, case=False, na=False)]
if search_employee_name:
    filtered_df = filtered_df[filtered_df["EMP_Name"].astype(str).str.contains(search_employee_name, case=False, na=False)]
if status_filter == "Active Only":
    filtered_df = filtered_df[filtered_df["EMP_Status"].astype(str).str.upper() == "ACTIVE"]
elif status_filter == "In-Active Only":
    filtered_df = filtered_df[filtered_df["EMP_Status"].astype(str).str.upper() == "IN-ACTIVE"]

if filtered_df.empty:
    st.warning("No ledger records match the selected filters.")
    st.stop()

all_day_columns = [f"D{d:02d}" for d in range(1, 32)]
grid_columns_order = (["Month_Year", "EMP_ID", "EMP_Name"] + all_day_columns + [
    "Over_Time", "Less_Time", "Total_Hours", "Total_Minutes", "Total_Days", "Actual_Days_Worked",
    "Base_Monthly_Comp", "Rate_Per_Hour", "Rate_Per_Minute", "Gross_Payout", "Total_Extra_Amount",
    "Advance_Payment", "Final_Payout", "Payment_Status", "Start_Date", "Last_Date", "EMP_Status"
])
validated_columns = [c for c in grid_columns_order if c in filtered_df.columns]
render_df = filtered_df[validated_columns].copy()

column_config = {
    "Month_Year": st.column_config.TextColumn("Month/Year", disabled=True),
    "EMP_ID": st.column_config.TextColumn("Employee ID", disabled=True),
    "EMP_Name": st.column_config.TextColumn("Employee Name", disabled=True),
    "Over_Time": st.column_config.NumberColumn("Extra Hrs", format="%.2f", disabled=True),
    "Less_Time": st.column_config.NumberColumn("Short Hrs", format="%.2f", disabled=True),
    "Total_Hours": st.column_config.NumberColumn("Total Hrs", format="%.2f", disabled=True),
    "Total_Minutes": st.column_config.NumberColumn("Total Minutes", format="%.2f", disabled=True),
    "Total_Days": st.column_config.NumberColumn("Raw Days Present", format="%.0f", disabled=True),
    "Actual_Days_Worked": st.column_config.NumberColumn("Actual Days Worked", format="%.2f", disabled=True),
    "Base_Monthly_Comp": st.column_config.NumberColumn("Base Monthly Comp", format="₹%.2f", disabled=True),
    "Rate_Per_Hour": st.column_config.NumberColumn("Hourly Rate", format="₹%.2f", disabled=True),
    "Rate_Per_Minute": st.column_config.NumberColumn("Per Minute Rate", format="₹%.4f", disabled=True),
    "Gross_Payout": st.column_config.NumberColumn("Gross Payout", format="₹%.2f", disabled=True),
    "Total_Extra_Amount": st.column_config.NumberColumn("1.d Total Extra Amount", format="₹%.2f", disabled=True),
    "Advance_Payment": st.column_config.NumberColumn("2. Advance Payment", format="₹%.2f", disabled=True),
    "Final_Payout": st.column_config.NumberColumn("Final Payout", format="₹%.2f", disabled=True),
    "Payment_Status": st.column_config.SelectboxColumn("Payment Status", options=["Pending", "Done"], required=True),
    "Start_Date": st.column_config.TextColumn("Start Date", disabled=True),
    "Last_Date": st.column_config.TextColumn("Last Working Date", disabled=True),
    "EMP_Status": st.column_config.TextColumn("Employee Status", disabled=True)
}
for col in all_day_columns:
    if col in validated_columns:
        column_config[col] = st.column_config.TextColumn(col.replace("D", ""), disabled=True)

st.subheader(f"Attendance Ledger — {selected_month_label}")
edited_df = st.data_editor(render_df, hide_index=True, width="stretch", column_config=column_config, key="attendance_ledger_data_editor")

edited_rows = st.session_state.get("attendance_ledger_data_editor", {}).get("edited_rows", {})
if edited_rows:
    for idx_txt, changes in edited_rows.items():
        idx = int(idx_txt)
        if "Payment_Status" in changes and idx < len(render_df):
            target_emp = render_df.iloc[idx]["EMP_ID"]
            target_month = render_df.iloc[idx]["Month_Year"]
            new_status = changes["Payment_Status"]
            with st.spinner(f"Updating status for {target_emp}..."):
                if update_db_payment_status(target_emp, target_month, new_status):
                    st.success(f"Payment status updated to '{new_status}' for ID {target_emp}.")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(f"Unable to update status for ID {target_emp}.")
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY - PART 7
# DATA FILE EXPORT INTERFACES & DYNAMIC EXPANSIBLE EXAMPLES
# ============================================================================

st.markdown("---")
st.header("📤 Payroll & Attendance Exports")
export_df = edited_df.copy()
export_col1, export_col2 = st.columns(2)

with export_col1:
    st.subheader("📊 CSV Export")
    csv_df = export_df.copy()
    for col in csv_df.columns:
        if col.startswith("D") and col[1:].isdigit():
            csv_df[col] = csv_df[col].apply(lambda x: f"\t{x}" if isinstance(x, str) and "/" in x else x)
    csv_buffer = io.StringIO()
    csv_df.to_csv(csv_buffer, index=False)
    st.download_button("⬇️ Download Ledger as CSV", data=csv_buffer.getvalue(), file_name=f"Attendance_Ledger_{datetime.date.today()}.csv", mime="text/csv", key="ledger_csv_download")

with export_col2:
    st.subheader("📄 PDF Export")
    avail_cols = list(export_df.columns)
    def_cols = [c for c in ["Month_Year", "EMP_ID", "EMP_Name", "Total_Hours", "Actual_Days_Worked", "Base_Monthly_Comp", "Rate_Per_Hour", "Rate_Per_Minute", "Gross_Payout", "Total_Extra_Amount", "Advance_Payment", "Final_Payout", "Payment_Status", "EMP_Status"] if c in avail_cols]
    sel_cols = st.multiselect("Select PDF columns:", options=avail_cols, default=def_cols, key="ledger_pdf_columns")

    row_opts = [f"{i+1}. {r.get('EMP_ID','N/A')} - {r.get('EMP_Name','Unnamed')} - {r.get('Month_Year','N/A')}" for i, (_, r) in enumerate(export_df.iterrows())]
    sel_rows = st.multiselect("Select PDF rows:", options=row_opts, default=[], help="Leave empty to include all filtered rows.", key="ledger_pdf_rows")

    pdf_tgt = export_df.iloc[[int(r.split(".")) - 1 for r in sel_rows]].copy() if sel_rows else export_df.copy()
    pdf_tgt = pdf_tgt[sel_cols].copy() if sel_cols else pd.DataFrame()
    pdf_data = generate_ledger_pdf(pdf_tgt) if not pdf_tgt.empty else b""
    st.download_button("⬇️ Download Ledger as PDF", data=pdf_data, file_name=f"Attendance_Ledger_{datetime.date.today()}.pdf", mime="application/pdf", key="ledger_pdf_download", disabled=not bool(pdf_data))

# ============================================================================
# DYNAMIC CALCULATION REFERENCE SYSTEM
# ============================================================================
st.markdown("---")
st.header("🧮 Calculation Formulas")
f_col1, f_col2, f_col3 = st.columns(3)

# Locate the active employee data matching the selector from Part 4
active_emp_id = st.session_state.get("payroll_adjustment_employee")
emp_record = df[df["EMP_ID"] == active_emp_id]

if not emp_record.empty:
    target_row = emp_record.iloc[0]
    calc_name = target_row["EMP_Name"]
    calc_base = target_row["Base_Monthly_Comp"]
    calc_hours = target_row["Total_Hours"]
    calc_gross = target_row["Gross_Payout"]
    calc_extra = target_row["Total_Extra_Amount"]
    calc_advance = target_row["Advance_Payment"]
    calc_final = target_row["Final_Payout"]
    
    # Read the active shift hours from raw dataset to dynamically scale logic
    raw_item = next((item for item in view_records_data if str(item.get("employee_id")) == str(active_emp_id)), {})
    calc_shift = max(1.00, safe_float(raw_item.get("shift_hours"), default=8.00))
else:
    calc_name, calc_base, calc_hours, calc_shift, calc_gross, calc_extra, calc_advance, calc_final = "Example", 25000.0, 176.0, 8.0, 13200.0, 0.0, 0.0, 13200.0

days_in_active_month = int(selected_month_days)
step_daily_rate = calc_base / days_in_active_month
step_hourly_unrounded = step_daily_rate / calc_shift
step_hourly = math.ceil(step_hourly_unrounded * 100) / 100.00
step_minute = math.ceil((step_hourly / 60.00) * 10000) / 10000.00
step_days_worked = round(calc_hours / calc_shift, 2)

with f_col1:
    st.markdown("**1. Hourly Rate Calculation**")
    st.latex(r"\mathrm{Daily\ Rate} = \frac{\mathrm{Base\ Monthly\ Comp}}{\mathrm{Days\ in\ Month}}")
    st.latex(r"\mathrm{Rate\ Per\ Hour} = \left\lceil \frac{\mathrm{Daily\ Rate}}{\mathrm{Shift\ Hours}} \times 100 \right\rceil \div 100")
    st.caption("The hourly rate rounds upward to the nearest penny.")
    
    with st.expander(f"🔍 View Live Example ({calc_name})"):
        st.markdown(f"""
        - **Target Employee:** {calc_name} ({active_emp_id})
        - **Month Days:** {days_in_active_month} days
        - **Base Wage Structure:** {money(calc_base)}
        - **Shift Assignment:** {calc_shift:.1f} Hours
        """)
        st.latex(rf"\frac{{{calc_base:,.2f}}}{{{days_in_active_month}}} = {step_daily_rate:,.4f}\ \mathrm{{per\ day}}")
        st.latex(rf"\frac{{{step_daily_rate:,.4f}}}{{{calc_shift:.1f}}} = {step_hourly_unrounded:,.4f}")
        st.latex(rf"\mathrm{{Final\ Hourly\ Rate}} = {money(step_hourly)}")
        st.latex(rf"\mathrm{{Per\ Minute\ Multiplier}} = {step_minute:,.4f}")

with f_col2:
    st.markdown("**2. Actual Days Worked Calculation**")
    st.latex(r"\mathrm{Actual\ Days\ Worked} = \frac{\mathrm{Total\ Hours\ Worked}}{\mathrm{Shift\ Hours}}")
    
    with st.expander(f"🔍 View Live Example ({calc_name})"):
        st.markdown(f"""
        - **Total Logged Time:** {calc_hours:.2f} Hours
        - **Shift Standard:** {calc_shift:.1f} Hours
        """)
        st.latex(rf"\frac{{{calc_hours:.2f}}}{{{calc_shift:.1f}}} = {step_days_worked:.2f}\ \mathrm{{Days}}")

with f_col3:
    st.markdown("**3. Final Payout Calculation**")
    st.latex(r"\mathrm{Final\ Payout} = \mathrm{Gross\ Payout} + \mathrm{Extra\ Amount} - \mathrm{Advance\ Payment}")
    
    with st.expander(f"🔍 View Live Example ({calc_name})"):
        st.markdown(f"""
        - **Gross Hours Earned:** {money(calc_gross)}
        - **Extra Incentive Bonuses:** +{money(calc_extra)}
        - **Advance Draws Deducted:** -{money(calc_advance)}
        """)
        st.latex(rf"{calc_gross:,.2f} + {calc_extra:,.2f} - {calc_advance:,.2f} = {calc_final:,.2f}")
        st.info(f"Final net payload calculated for **{calc_name}** is **{money(calc_final)}**.")
