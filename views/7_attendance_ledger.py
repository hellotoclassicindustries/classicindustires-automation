# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY - PART 1
# CONFIGURATIONS, INITIALISERS & IN-MEMORY MATHEMATICAL ENGINE
# ============================================================================

import calendar
import datetime
import io
import math
import re
import pandas as pd
import requests
import streamlit as st
from dateutil.relativedelta import relativedelta
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except Exception:
    st.error(
        "❌ Missing infrastructure secrets configuration. "
        "Please configure SUPABASE_URL and SUPABASE_KEY."
    )
    st.stop()

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

SOURCE_IDENTIFIER = "STREAMLIT_LIVE_UI"
APP_USER = (
    st.session_state.get("user_name")
    or st.session_state.get("username")
    or "Streamlit User"
)

ADJUSTMENT_RATE_UNITS = ["Per Hour", "Per Day", "Per Shift", "Per Task", "Per Load", "Fixed"]
ADJUSTMENT_STATUSES = ["Pending", "Approved", "Rejected"]

def safe_float(value):
    """Safely convert an incoming raw cell database value to float."""
    if value is None:
        return 0.00
    value_text = str(value).strip()
    if value_text == "":
        return 0.00
    if value_text.lower() in ["none", "nan", "null", "n/a"]:
        return 0.00
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.00

def money(value):
    """Round an application calculation monetary amount to two decimal places."""
    return round(safe_float(value), 2)

def normalise_employee_id(value):
    """Convert variable tracking IDs into consistent string keys."""
    if value is None:
        return ""
    value_text = str(value).strip()
    if value_text.lower() in ["none", "nan", "null", "n/a"]:
        return ""
    if value_text.endswith(".0"):
        value_text = value_text[:-2]
    return value_text

def parse_bigint_employee_id(value):
    """Convert an employee tracking string key to a PostgreSQL BIGINT integer."""
    employee_id_text = normalise_employee_id(value)
    if not employee_id_text:
        return None
    try:
        return int(employee_id_text)
    except (TypeError, ValueError):
        return None
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY - PART 2
# DATE STRUCTURING REGEX PARSERS & APPLICATION RUNTIME REVENUE MATH
# ============================================================================

def parse_row_date(month_year_value):
    """Convert variable text matrix date inputs into unified date objects."""
    if month_year_value is None:
        return None
    month_year_text = str(month_year_value).strip()
    if not month_year_text or month_year_text.upper() == "N/A":
        return None

    normalized = month_year_text.replace("/", "-")
    normalized_upper = normalized.upper()
    year_match = re.search(r"\b(20\d{2})\b", normalized)
    year = int(year_match.group(1)) if year_match else datetime.date.today().year

    for month_number in range(1, 13):
        f_m = calendar.month_name[month_number].upper()
        s_m = calendar.month_abbr[month_number].upper()
        if f_m in normalized_upper or s_m in normalized_upper:
            return datetime.date(year, month_number, 1)

    year_month_match = re.search(r"\b(20\d{2})-(0[1-9]|1[0-2])\b", normalized)
    if year_month_match:
        return datetime.date(int(year_month_match.group(1)), int(year_month_match.group(2)), 1)

    numeric_values = re.findall(r"\b(\d{1,2})\b", normalized)
    for numeric_value in numeric_values:
        month_number = int(numeric_value)
        if 1 <= month_number <= 12:
            return datetime.date(year, month_number, 1)
    return None

def canonical_month_year(month_year_value):
    """Convert a month value to the strict database formatting format YYYY-MM."""
    row_date = parse_row_date(month_year_value)
    return row_date.strftime("%Y-%m") if row_date else None

def display_month_year(month_year_value):
    """Convert standard database format to a user-friendly month string label."""
    row_date = parse_row_date(month_year_value)
    return row_date.strftime("%B-%Y") if row_date else str(month_year_value or "N/A")

def get_days_in_month(month_year_value):
    """Return the exact number of days tracked inside the active month configuration."""
    row_date = parse_row_date(month_year_value)
    return calendar.monthrange(row_date.year, row_date.month)[1] if row_date else 31

def calculate_extra_work_payment(quantity, rate, rate_unit):
    """Calculate extra-work payment parameters completely inside runtime memory."""
    qty = max(0.00, safe_float(quantity))
    rt = max(0.00, safe_float(rate))
    return money(rt) if rate_unit == "Fixed" else money(qty * rt)

def calculate_final_net_payable(regular_gross, extra_payment, advance_given):
    """Calculate absolute final net payable keeping processing rules in runtime memory."""
    r_gross = max(0.00, safe_float(regular_gross))
    e_pay = max(0.00, safe_float(extra_payment))
    adv = max(0.00, safe_float(advance_given))
    return money(r_gross + e_pay - adv)
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY - PART 3
# RESTful API NETWORK PIPELINES & IDEMPOTENT PERSISTENCE ENGINE
# ============================================================================

@st.cache_data(ttl=5)
def fetch_vw_attendance_ledger():
    """Fetch baseline transactional records tracking attendance views."""
    endpoint = f"{SUPABASE_URL.strip('/')}/rest/v1/vw_attendance_ledger?select=*&order=month_year.desc,employee_id.asc"
    try:
        response = requests.get(endpoint, headers=HEADERS, timeout=30)
        return response.json() if response.status_code == 200 else []
    except requests.RequestException:
        return []

@st.cache_data(ttl=5)
def fetch_payroll_adjustments():
    """Fetch stored live adjustment logs tracking current active configurations."""
    endpoint = f"{SUPABASE_URL.strip('/')}/rest/v1/payroll_adjustments_live?select=*&order=month_year.desc,employee_id.asc"
    try:
        response = requests.get(endpoint, headers=HEADERS, timeout=30)
        return response.json() if response.status_code == 200 else []
    except requests.RequestException:
        return []

def save_payroll_adjustment(adjustment_payload):
    """Sync values to public tables handling composite constraint checks."""
    endpoint = f"{SUPABASE_URL.strip('/')}/rest/v1/payroll_adjustments_live?on_conflict=employee_id,month_year"
    upsert_headers = {
        **HEADERS,
        "Prefer": "resolution=merge-duplicates,return=representation",
    }
    try:
        response = requests.post(endpoint, headers=upsert_headers, json=adjustment_payload, timeout=30)
        if response.status_code in:
            return True, response.json()
        return False, response.text
    except requests.RequestException as error:
        return False, str(error)

def build_adjustment_lookup(adjustment_records):
    """Build a fast memory search dictionary map keyed on (employee_id, month_year)."""
    lookup = {}
    for record in adjustment_records or []:
        emp_id = normalise_employee_id(record.get("employee_id"))
        m_yr = canonical_month_year(record.get("month_year"))
        if emp_id and m_yr:
            lookup[(emp_id, m_yr)] = record
    return lookup

def update_db_payment_status(employee_id, month_year, new_status):
    """Update primary workflow verification flags inside database tables."""
    endpoint = f"{SUPABASE_URL.strip('/')}/rest/v1/raw_attendance_feed?employee_id=eq.{employee_id}&month_year=eq.{month_year}"
    payload = {"payment_status": new_status}
    try:
        res = requests.patch(endpoint, headers=HEADERS, json=payload, timeout=30)
        return res.status_code in [200, 201, 204]
    except requests.RequestException:
        return False
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY - PART 4
# LANDSCAPE PDF EXPORT MATRIX ENGINE GENERATOR
# ============================================================================

def generate_ledger_matrix_pdf(dataframe):
    """Compile structured canvas reports across active parameters rows."""
    if dataframe is None or dataframe.empty or len(dataframe.columns) == 0:
        return b""

    pdf_buffer = io.BytesIO()
    document = SimpleDocTemplate(
        pdf_buffer, pagesize=landscape(letter),
        rightMargin=20, leftMargin=20, topMargin=30, bottomMargin=30
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "LedgerTitleStyle", parent=styles["Heading1"], fontSize=14,
        leading=18, textColor=colors.HexColor("#1A365D"), alignment=0
    )
    header_style = ParagraphStyle(
        "LedgerHeaderStyle", parent=styles["Normal"], fontSize=6,
        leading=8, textColor=colors.white, fontName="Helvetica-Bold", alignment=1
    )
    data_style = ParagraphStyle(
        "LedgerDataStyle", parent=styles["Normal"], fontSize=5,
        leading=7, textColor=colors.black, alignment=1
    )

    story = [Paragraph("Payroll & Attendance Ledger", title_style), Spacer(1, 10)]
    headers = list(dataframe.columns)
    table_data = [[Paragraph(escape(str(column_name)), header_style) for column_name in headers]]

    for _, row in dataframe.iterrows():
        row_cells = []
        for column_name in headers:
            value = row[column_name]
            value_text = f"{value:.2f}" if isinstance(value, float) else str(value if not pd.isna(value) else "")
            row_cells.append(Paragraph(escape(value_text), data_style))
        table_data.append(row_cells)

    column_width = max(20, 752 / max(len(headers), 1))
    ledger_table = Table(table_data, colWidths=[column_width] * len(headers), repeatRows=1)
    ledger_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2B6CB0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    story.append(ledger_table)
    document.build(story)
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY - PART 5
# PRESENTATION CONTROLS FILTERS & CORE SYSTEM DATA PROCESSING LOOP
# ============================================================================

view_records_data = fetch_vw_attendance_ledger()
adjustment_records_data = fetch_payroll_adjustments()
adjustment_lookup = build_adjustment_lookup(adjustment_records_data)

if not view_records_data:
    st.info("📋 No integrated database rows were found in vw_attendance_ledger.")
    st.stop()

today = datetime.date.today()
previous_month_date = today - relativedelta(months=1)
default_start = previous_month_date.replace(day=1)
default_end = previous_month_date.replace(
    day=calendar.monthrange(previous_month_date.year, previous_month_date.month)[1]
)

st.header("📋 Payroll & Attendance Workflow")
chosen_dates = st.date_input(
    "Select Payout Month:", value=(default_start, default_end),
    key="unique_attendance_calendar_range_picker",
)
start_cal, end_cal = chosen_dates if (isinstance(chosen_dates, tuple) and len(chosen_dates) == 2) else (default_start, default_end)

filter_col1, filter_col2, filter_col3 = st.columns(3)
with filter_col1:
    search_mat_id = st.text_input("Filter by Employee ID:", "", key="mat_id_input").strip()
with filter_col2:
    search_mat_name = st.text_input("Filter by Employee Name:", "", key="mat_name_input").strip()
with filter_col3:
    search_mat_status = st.selectbox(
        "Filter by Employee Status:", options=["All Statuses", "Active Only", "In-Active Only"],
        key="mat_status_input",
    )

processed_rows = []
employee_dropdown_map = {}

for item in view_records_data:
    original_month_year = item.get("month_year") or "N/A"
    row_date = parse_row_date(original_month_year)
    database_month_year = canonical_month_year(original_month_year)
    employee_id = item.get("employee_id")
    employee_id_text = normalise_employee_id(employee_id)
    emp_name = item.get("employee_name") or "Unnamed"

    if employee_id_text and employee_id_text != "N/A":
        employee_dropdown_map[employee_id_text] = f"{emp_name} (ID: {employee_id_text})"
    if row_date and not (start_cal <= row_date <= end_cal):
        continue

    total_hours_worked = safe_float(item.get("total_hours"))
    total_days_worked = safe_float(item.get("total_days"))
    base_monthly_comp = safe_float(item.get("base_monthly_comp"))
    configured_shift_hours = safe_float(item.get("shift_hours")) or 8.00
    current_status = item.get("employee_status") or "Active"
    days_list = item.get("attendance_days") or []
    total_minutes_worked = round(total_hours_worked * 60.0, 2)
    month_days = get_days_in_month(original_month_year)
    actual_days_worked = round(total_hours_worked / configured_shift_hours, 2) if configured_shift_hours > 0 else 0.00

    if str(current_status).upper() == "ACTIVE" and month_days > 0 and configured_shift_hours > 0:
        daily_allocation_rate = base_monthly_comp / float(month_days)
        per_hour_rate = math.ceil((daily_allocation_rate / configured_shift_hours) * 100) / 100.0
        per_minute_rate = math.ceil((per_hour_rate / 60.0) * 10000) / 10000.0
        calculated_gross_payout = round(total_hours_worked * per_hour_rate, 2)
    else:
        per_hour_rate = per_minute_rate = calculated_gross_payout = 0.00

    adjustment = adjustment_lookup.get((employee_id_text, database_month_year), {})
    adjustment_quantity = safe_float(adjustment.get("extra_work_quantity"))
    adjustment_rate = safe_float(adjustment.get("extra_work_rate"))
    adjustment_payment = safe_float(adjustment.get("extra_work_payment"))
    adjustment_advance = safe_float(adjustment.get("advance_given"))
    final_net_payable = calculate_final_net_payable(calculated_gross_payout, adjustment_payment, adjustment_advance)

    row_dict = {
        "Month_Year": original_month_year, "DB_Month_Year": database_month_year,
        "EMP_ID": employee_id_text or "N/A", "EMP_Name": emp_name,
        "Over_Time": safe_float(item.get("over_time")), "Less_Time": safe_float(item.get("less_time")),
        "Total_Hours": total_hours_worked, "Total_Minutes": total_minutes_worked,
        "Total_Days": total_days_worked, "Actual_Days_Worked": actual_days_worked,
        "Start_Date": item.get("start_date") or "N/A", "Last_Date": item.get("last_day_of_work") or "N/A",
        "EMP_Status": current_status, "Base_Monthly_Comp": base_monthly_comp,
        "Rate_Per_Hour": per_hour_rate, "Rate_Per_Minute": per_minute_rate, "Gross_Payout": calculated_gross_payout,
        
        "Extra_Earning": adjustment_payment, "Advance_Given": adjustment_advance, "Final_Net_Payable": final_net_payable,
        "Extra_Work_Type": adjustment.get("extra_work_type") or "", "Extra_Work_Quantity": adjustment_quantity,
        "Extra_Work_Rate": adjustment_rate, "Rate_Unit": adjustment.get("rate_unit") or "Fixed",
        "Adjustment_Status": adjustment.get("adjustment_status") or "No UI Adjustment",
        "Adjustment_Source": adjustment.get("source_identifier") or "NO_UI_ADJUSTMENT",
        "Adjustment_Notes": adjustment.get("adjustment_notes") or "",
        "Payment_Status": item.get("payment_status") or "Pending",
        "DB_Show_Flag": item.get("show") if item.get("show") is not None else True,
    }

    for day_number in range(1, 32):
        day_column = f"D{day_number:02d}"
        row_dict[day_column] = days_list[day_number - 1] if (days_list and day_number - 1 < len(days_list)) else ""
    processed_rows.append(row_dict)

df = pd.DataFrame(processed_rows)
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY - PART 6
# PRIMARY ATTENDANCE MATRIX LEDGER RENDERING COMPONENT
# ============================================================================

if df.empty:
    st.warning("⚠️ No attendance records match the selected date range.")
    st.stop()

filtered_df = df[df["DB_Show_Flag"] == True].copy()
if search_mat_id:
    filtered_df = filtered_df[filtered_df["EMP_ID"].astype(str).str.contains(search_mat_id, case=False, na=False)]
if search_mat_name:
    filtered_df = filtered_df[filtered_df["EMP_Name"].astype(str).str.contains(search_mat_name, case=False, na=False)]

if search_mat_status == "Active Only":
    filtered_df = filtered_df[filtered_df["EMP_Status"].astype(str).str.upper() == "ACTIVE"]
elif search_mat_status == "In-Active Only":
    filtered_df = filtered_df[filtered_df["EMP_Status"].astype(str).str.upper() == "IN-ACTIVE"]

if filtered_df.empty:
    st.warning("⚠️ No ledger records match the active filters.")
    st.stop()

all_day_columns = [f"D{day_number:02d}" for day_number in range(1, 32)]
grid_columns_order = (
    ["Month_Year", "EMP_ID", "EMP_Name"] + all_day_columns +
    [
        "Over_Time", "Less_Time", "Total_Hours", "Total_Minutes", "Total_Days",
        "Actual_Days_Worked", "Base_Monthly_Comp", "Rate_Per_Hour", "Rate_Per_Minute", "Gross_Payout",
        "Extra_Earning", "Advance_Given", "Final_Net_Payable",
        "Extra_Work_Type", "Extra_Work_Quantity", "Extra_Work_Rate", "Rate_Unit",
        "Adjustment_Status", "Adjustment_Source", "Payment_Status", "Start_Date", "Last_Date", "EMP_Status"
    ]
)

validated_columns = [c for c in grid_columns_order if c in filtered_df.columns]
render_df = filtered_df[validated_columns].copy()

column_config = {
    "Month_Year": st.column_config.TextColumn("Month/Year", width="small", disabled=True),
    "EMP_ID": st.column_config.TextColumn("Employee ID", width="small", disabled=True),
    "EMP_Name": st.column_config.TextColumn("Employee Name", width="medium", disabled=True),
    "Over_Time": st.column_config.NumberColumn("Extra Hrs", format="%.2f", width="small", disabled=True),
    "Less_Time": st.column_config.NumberColumn("Short Hrs", format="%.2f", width="small", disabled=True),
    "Total_Hours": st.column_config.NumberColumn("Total Hrs", format="%.2f", width="small", disabled=True),
    "Total_Minutes": st.column_config.NumberColumn("Total Minutes", format="%.2f", width="small", disabled=True),
    "Total_Days": st.column_config.NumberColumn("Raw Days Present", format="%.0f", width="small", disabled=True),
    "Actual_Days_Worked": st.column_config.NumberColumn("Actual Days Worked", format="%.2f", width="medium", disabled=True),
    "Base_Monthly_Comp": st.column_config.NumberColumn("Base Monthly Comp", format="₹%.2f", width="small", disabled=True),
    "Rate_Per_Hour": st.column_config.NumberColumn("Hourly Rate", format="₹%.2f", width="small", disabled=True),
    "Rate_Per_Minute": st.column_config.NumberColumn("Per Minute Rate", format="₹%.4f", width="small", disabled=True),
    "Gross_Payout": st.column_config.NumberColumn("Gross Payout", format="₹%.2f", width="medium", disabled=True),
    
    "Extra_Earning": st.column_config.NumberColumn("Extra Earning", format="₹%.2f", width="medium", disabled=True),
    "Advance_Given": st.column_config.NumberColumn("Advance Given", format="₹%.2f", width="small", disabled=True),
    "Final_Net_Payable": st.column_config.NumberColumn("Final Net Payable", format="₹%.2f", width="medium", disabled=True),
    
    "Extra_Work_Type": st.column_config.TextColumn("Extra Work Type", width="medium", disabled=True),
    "Extra_Work_Quantity": st.column_config.NumberColumn("Extra Work Qty", format="%.2f", width="small", disabled=True),
    "Extra_Work_Rate": st.column_config.NumberColumn("Extra Work Rate", format="₹%.2f", width="small", disabled=True),
    "Rate_Unit": st.column_config.TextColumn("Rate Unit", width="small", disabled=True),
    "Adjustment_Status": st.column_config.TextColumn("Adjustment Status", width="small", disabled=True),
    "Adjustment_Source": st.column_config.TextColumn("Adjustment Source", width="medium", disabled=True),
    "Payment_Status": st.column_config.SelectboxColumn("Payment Status", width="medium", options=["Pending", "Done"], required=True),
    "Start_Date": st.column_config.TextColumn("Start Date", width="small", disabled=True),
    "Last_Date": st.column_config.TextColumn("Last Working Date", width="small", disabled=True),
    "EMP_Status": st.column_config.TextColumn("Employee Status", width="small", disabled=True),
}

for d_col in all_day_columns:
    if d_col in validated_columns:
        column_config[d_col] = st.column_config.TextColumn(d_col.replace("D", ""), width=45, disabled=True)

edited_df = st.data_editor(render_df, hide_index=True, width="stretch", column_config=column_config, key="ledger_editor")
editor_state = st.session_state.get("ledger_editor", {}).get("edited_rows", {})

if editor_state:
    for row_idx_text, altered_properties in editor_state.items():
        row_index = int(row_idx_text)
        if "Payment_Status" not in altered_properties or row_index >= len(render_df):
            continue
        t_employee = render_df.iloc[row_index]["EMP_ID"]
        t_month = render_df.iloc[row_index]["Month_Year"]
        updated_status = altered_properties["Payment_Status"]

        with st.spinner(f"Updating payment status for {t_employee}..."):
            success = update_db_payment_status(t_employee, t_month, updated_status)
        if success:
            st.success(f"✓ Payment status updated to '{updated_status}' for Employee ID: {t_employee}")
            st.cache_data.clear()
            st.rerun()
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY - PART 7
# DOWNLOAD CHANNELS AND FILE ARCHIVE WORKFLOW PIPELINES
# ============================================================================

st.markdown("---")
st.header("📤 Payroll & Attendance Workflow Exports")
export_df = edited_df.copy()
export_col1, export_col2 = st.columns(2)

with export_col1:
    st.subheader("📊 CSV Export")
    csv_df = export_df.copy()
    for column_name in csv_df.columns:
        if column_name.startswith("D") and column_name[1:].isdigit():
            csv_df[column_name] = csv_df[column_name].apply(lambda v: f"\t{v}" if isinstance(v, str) and "/" in v else v)
    csv_buffer = io.StringIO()
    csv_df.to_csv(csv_buffer, index=False)
    st.download_button(
        label="⬇️ Download Ledger as CSV (Preserve Formats)", data=csv_buffer.getvalue(),
        file_name=f"Historical_Attendance_Ledger_{datetime.date.today()}.csv",
        mime="text/csv", key="ledger_csv_download_btn",
    )

with export_col2:
    st.subheader("📄 PDF Export")
    available_pdf_columns = list(export_df.columns)
    default_pdf_columns = [
        c for c in [
            "Month_Year", "EMP_ID", "EMP_Name", "Total_Hours", "Actual_Days_Worked",
            "Base_Monthly_Comp", "Rate_Per_Hour", "Gross_Payout",
            "Extra_Earning", "Advance_Given", "Final_Net_Payable", "Payment_Status", "EMP_Status"
        ] if c in available_pdf_columns
    ]
    selected_pdf_columns = st.multiselect("Select columns for PDF:", options=available_pdf_columns, default=default_pdf_columns, key="pdf_cols")
    row_options, row_lookup = [], {}
    for pos, (_, r) in enumerate(export_df.iterrows()):
        label = f"{pos + 1}. {r.get('EMP_ID', 'N/A')} - {r.get('EMP_Name', 'Unnamed')} - {r.get('Month_Year', 'N/A')}"
        row_options.append(label)
        row_lookup[label] = pos

    selected_pdf_row_labels = st.multiselect("Select rows for PDF:", options=row_options, default=[], key="pdf_rows")
    pdf_target_df = export_df.iloc[[row_lookup[lbl] for lbl in selected_pdf_row_labels]].copy() if selected_pdf_row_labels else export_df.copy()
    pdf_target_df = pdf_target_df[selected_pdf_columns].copy() if selected_pdf_columns else pd.DataFrame()

    if not selected_pdf_columns:
        st.warning("Select at least one column for the PDF.")
        pdf_data = b""
    elif pdf_target_df.empty:
        st.warning("No rows are available for the selected PDF.")
        pdf_data = b""
    else:
        pdf_data = generate_ledger_matrix_pdf(pdf_target_df)

    st.download_button(
        label="⬇️ Download Ledger as PDF (Landscape)", data=pdf_data,
        file_name=f"Historical_Attendance_Ledger_{datetime.date.today()}.pdf",
        mime="application/pdf", key="ledger_pdf_download_btn", disabled=not bool(pdf_data),
    )
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY - PART 8
# ANCHORED EXPANDABLE SECTION FOR POST-GRID LIVE PAYROLL ADJUSTMENTS
# ============================================================================

st.markdown("---")
with st.expander("🛠️ Expand Payroll Adjustment Workspace Section", expanded=False):
    st.markdown("#### Create / Edit Monthly Payroll Adjustment")
    if employee_dropdown_map:
        col_adj1, col_adj2, col_adj3 = st.columns(3)
        with col_adj1:
            selected_emp_key = st.selectbox(
                "Select Employee", options=list(employee_dropdown_map.keys()),
                format_func=lambda x: employee_dropdown_map[x], key="adjustment_employee_select"
            )
        with col_adj2:
            selected_date = st.date_input("Select Payroll Month", value=datetime.date.today(), key="adjustment_month_input")
            target_canonical_month = selected_date.strftime("%Y-%m")
        with col_adj3:
            input_rate_unit = st.selectbox("Rate Unit", options=ADJUSTMENT_RATE_UNITS, index=5, key="adjustment_rate_unit_select")

        col_adj4, col_adj5, col_adj6 = st.columns(3)
        with col_adj4:
            input_work_type = st.text_input("Extra Work Type", value="", placeholder="e.g., Weekend Special Task", key="adjustment_work_type_input")
        with col_adj5:
            input_quantity = st.number_input("Extra Work Quantity", min_value=0.00, value=0.00, step=1.00, format="%.2f", key="adjustment_quantity_input")
        with col_adj6:
            input_rate = st.number_input("Extra Work Rate", min_value=0.00, value=0.00, step=50.00, format="%.2f", key="adjustment_rate_input")

        col_adj7, col_adj8 = st.columns(2)
        with col_adj7:
            input_advance = st.number_input("Advance Given", min_value=0.00, value=0.00, step=100.00, format="%.2f", key="adjustment_advance_input")
        with col_adj8:
            input_notes = st.text_area("Adjustment Notes", value="", placeholder="Provide reasoning details...", key="adjustment_notes_input")

        calc_extra_payment = calculate_extra_work_payment(input_quantity, input_rate, input_rate_unit)
        matched_base_gross = 0.00
        if not df.empty:
            matched_rows = df[(df["EMP_ID"] == selected_emp_key) & (df["DB_Month_Year"] == target_canonical_month)]
            if not matched_rows.empty:
                matched_base_gross = safe_float(matched_rows["Gross_Payout"].values[0])
        calc_net_payable = calculate_final_net_payable(matched_base_gross, calc_extra_payment, input_advance)

        st.markdown("##### 📊 Calculation Preview Verification")
        v_col1, v_col2, v_col3, v_col4 = st.columns(4)
        v_col1.metric("Base Payout Gross", f"₹{matched_base_gross:,.2f}")
        v_col2.metric("Extra Earning (Calculated)", f"₹{calc_extra_payment:,.2f}")
        v_col3.metric("Advance (Deduction)", f"₹{input_advance:,.2f}")
        v_col4.metric("Net Payable Payout", f"₹{calc_net_payable:,.2f}")

        if st.button("✅ Accept & Save Adjustments", type="primary", key="save_adjustment_action_btn"):
            parsed_bigint_id = parse_bigint_employee_id(selected_emp_key)
            if parsed_bigint_id is None:
                st.error("❌ Invalid employee identification formatting format mapping context.")
            else:
                payload = {
                    "employee_id": parsed_bigint_id, "month_year": target_canonical_month,
                    "extra_work_type": str(input_work_type).strip(), "extra_work_quantity": float(input_quantity),
                    "extra_work_rate": float(input_rate), "rate_unit": str(input_rate_unit),
                    "extra_work_payment": float(calc_extra_payment), "advance_given": float(input_advance),
                    "adjustment_notes": str(input_notes).strip(), "adjustment_status": "Approved",
                    "source_identifier": SOURCE_IDENTIFIER, "created_by": APP_USER,
                    "approved_by": APP_USER, "approved_at": datetime.datetime.now().isoformat()
                }
                with st.spinner("Saving calculations configuration details..."):
                    save_status, details = save_payroll_adjustment(payload)
                if save_status:
                    st.success("✓ Calculations registered successfully! Ledger view updating.")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(f"Persistence Exception Encountered: {details}")
    else:
        st.warning("⚠️ No active employee profiles discovered to populate form fields.")
