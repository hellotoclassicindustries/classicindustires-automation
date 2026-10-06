# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 1 (API ROUTING & INFRASTRUCTURE REGISTRIES)
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

# FIX: Changed from st.sidebar.cache_data to the standard global st.cache_data
@st.cache_data(ttl=2)
def fetch_raw_attendance_feed():
    """Fetches full attendance matrix from Supabase public.raw_attendance_feed"""
    endpoint = f"{SUPABASE_URL.strip('/')}/rest/v1/raw_attendance_feed?order=month_year.desc,employee_id.asc"
    try:
        response = requests.get(endpoint, headers=HEADERS)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception:
        return []

# FIX: Changed from st.sidebar.cache_data to the standard global st.cache_data
@st.cache_data(ttl=15)
def fetch_cntr_employee_master():
    """Queries production employee metadata profile registries"""
    endpoint = f"{SUPABASE_URL.strip('/')}/rest/v1/cntr_employee_master?order=employee_id.asc"
    try:
        response = requests.get(endpoint, headers=HEADERS)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception:
        return []

def update_db_payment_status(employee_id, month_year, new_status):
    """Performs transactional REST PATCH to persist updated payment state down to the Supabase layer"""
    endpoint = f"{SUPABASE_URL.strip('/')}/rest/v1/raw_attendance_feed?employee_id=eq.{employee_id}&month_year=eq.{month_year}"
    payload = {"payment_status": new_status}
    try:
        res = requests.patch(endpoint, headers=HEADERS, json=payload)
        return res.status_code in [200, 201, 204]
    except Exception:
        return False

def parse_row_date(month_year_str):
    """Maps custom database string metrics directly into true datetime.date objects for sorting"""
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
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 2 (MASTER INGESTION & PROCESSING ENGINES)
# ============================================================================

# Load Raw Datasets from Synced Production Pools
raw_attendance_data = fetch_raw_attendance_feed()
master_emp_data = fetch_cntr_employee_master()

# Compile Employee Profile Metadata Map directly from authority registries
emp_metadata_map = {}
for emp in master_emp_data:
    emp_id = emp.get("employee_id")
    if emp_id:
        emp_metadata_map[str(emp_id).strip().upper()] = {
            "start_date": emp.get("start_date") or "N/A",
            "last_day_of_work": emp.get("last_day_of_work") or "N/A",
            "employee_status": emp.get("employee_status") or "Active",
            "comp_monthly": float(emp.get("comp_monthly")) if emp.get("comp_monthly") else 0.00,
            "shift_hours": float(emp.get("shift_hours")) if emp.get("shift_hours") else 12.00,
            "show_flag": emp.get("show", True)
        }

def evaluate_attendance_tokens_fallback(days_list, base_shift):
    """
    BACKUP ENGINE ONLY: Runs calculations from character array tokens 
    ONLY if database columns for total_hours or total_days are completely empty.
    """
    total_hours = 0.0
    proportional_days = 0.0
    
    for token in days_list:
        if not token:
            continue
        clean = str(token).strip().upper()
        
        if clean == "" or clean == "A":
            hours_today = 0.0
        elif clean == "P":
            hours_today = base_shift
        elif re.match(r"^\d+$", clean):
            hours_today = float(clean)
        elif "/" in clean:
            try:
                parts = clean.split("/")
                hours_today = float(parts[0]) + (float(parts[1]) / 60.0)
            except:
                hours_today = 0.0
        elif "P" in clean:
            try:
                numeric_extracted = re.sub(r"[^0-9.]", "", clean)
                overtime_val = float(numeric_extracted) if numeric_extracted else 0.0
                hours_today = base_shift + overtime_val
            except:
                hours_today = base_shift
        else:
            try:
                numeric_extracted = re.sub(r"[^0-9.]", "", clean)
                hours_today = float(numeric_extracted) if numeric_extracted else 0.0
            except:
                hours_today = 0.0
                
        total_hours += hours_today
        if base_shift > 0 and hours_today > 0:
            proportional_days += (hours_today / base_shift)
            
    return round(total_hours, 2), round(proportional_days, 2)
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 3 (CALENDAR SYSTEM FILTERS & DATAFRAME ASSEMBLY)
# ============================================================================

if not raw_attendance_data:
    st.info("📋 System Log: No staging rows found inside public.raw_attendance_feed table space.")
else:
    # Calculate previous calendar month parameters automatically
    today = datetime.date.today()
    past_month_date = today - relativedelta(months=1)
    default_start = past_month_date.replace(day=1)
    default_end = past_month_date.replace(day=calendar.monthrange(past_month_date.year, past_month_date.month)[1])

    # Single Calendar input dropdown configuration box layout
    chosen_dates = st.date_input(
        "Select Payout Month:",
        value=(default_start, default_end),
        key="main_graphical_calendar_picker"
    )

    if isinstance(chosen_dates, tuple) and len(chosen_dates) == 2:
        start_cal, end_cal = chosen_dates
    else:
        start_cal, end_cal = default_start, default_end

    # Layout textual filter fields row
    mat_col1, mat_col4 = st.columns(2)
    with mat_col1:
        search_mat_id = st.text_input("Filter by Employee ID:", "", key="mat_id_input").strip()
    with mat_col4:
        search_mat_status = st.selectbox("Filter by Employee Status:", options=["All Statuses", "Active Only", "In-Active Only"], key="mat_status_input")

    start_day, end_day = st.slider("Select Day Columns View Range:", min_value=1, max_value=31, value=(1, 31), key="mat_day_slider")

    # Construct tracking rows prioritizing dynamic memory computation architectures
    processed_rows = []
    for item in raw_attendance_data:
        m_yr = item.get("month_year") or "N/A"
        row_dt = parse_row_date(m_yr)
        
        # Filter rows by calendar input bounds
        if row_dt:
            if not (start_cal <= row_dt <= end_cal):
                continue
                
        days_list = item.get("attendance_days") or []
        emp_id_str = str(item.get("employee_id") or "").strip().upper()
        meta = emp_metadata_map.get(emp_id_str, {
            "start_date": "N/A", "last_day_of_work": "N/A", "employee_status": "Active",
            "comp_monthly": 0.00, "shift_hours": 12.00
        })
        
        def safe_float(val):
            if val is None or str(val).strip() == "" or str(val).lower() == "none": return 0.00
            try: return float(val)
            except: return 0.00

        # MAX DB USAGE POLICY: Pull primary metrics straight out of raw_attendance_feed table columns
        db_hours = safe_float(item.get("total_hours"))
        db_days = safe_float(item.get("total_days"))
        
        current_status = meta.get("employee_status", "Active")
        configured_monthly_comp = meta.get("comp_monthly", 0.00)
        configured_shift_hours = meta.get("shift_hours", 12.00)
        
        # Safe Fallback Engine: Runs calculations *only* if DB field values are absent
        if db_hours <= 0.0 or db_days <= 0.0:
            total_hours_worked, total_days_worked = evaluate_attendance_tokens_fallback(days_list, configured_shift_hours)
        else:
            total_hours_worked = db_hours
            total_days_worked = db_days
            
        overtime_hours = safe_float(item.get("over_time"))
        lesstime_hours = safe_float(item.get("less_time"))
        row_month_days = get_days_in_month(m_yr)

        # Payroll rate logic computations
        if current_status.upper() == "ACTIVE" and row_month_days > 0:
            per_hour_rate = (configured_monthly_comp / float(row_month_days)) / configured_shift_hours
            per_minute_rate = per_hour_rate / 60.0
            calculated_gross_payout = total_hours_worked * 60.0 * per_minute_rate
            total_minutes_worked = total_hours_worked * 60.0
        else:
            per_hour_rate = 0.00
            per_minute_rate = 0.00
            calculated_gross_payout = 0.00
            total_minutes_worked = 0.00

        row_dict = {
            "Month_Year": m_yr, "EMP_ID": item.get("employee_id") or "N/A", "EMP_Name": item.get("employee_name") or "Unnamed",
            "Over_Time": overtime_hours, "Less_Time": lesstime_hours,
            "Total_Hours": total_hours_worked, "Total_Minutes": total_minutes_worked, "Total_Days": total_days_worked,
            "Start_Date": meta.get("start_date", "N/A"), "Last_Date": meta.get("last_day_of_work", "N/A"), "EMP_Status": current_status,
            "Base_Monthly_Comp": configured_monthly_comp, "Rate_Per_Hour": per_hour_rate, "Rate_Per_Minute": per_minute_rate,
            "Gross_Payout": calculated_gross_payout,
            "Payment_Status": item.get("payment_status") or "Pending", "DB_Show_Flag": item.get("show") if item.get("show") is not None else True
        }
        for day in range(1, 32):
            row_dict[f"D{day:02d}"] = days_list[day-1] if (days_list and day-1 < len(days_list)) else ""
        processed_rows.append(row_dict)
        
    df = pd.DataFrame(processed_rows)
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 4 - SUB-PART 4A (TABLE GRAPHICS ENGINE)
# ============================================================================

    if df.empty:
        st.warning("⚠️ No operational records match the active date window boundaries selected.")
    else:
        # Apply filter conditions
        filtered_df = df[df["DB_Show_Flag"] == True].copy()
        if search_mat_id:
            filtered_df = filtered_df[filtered_df["EMP_ID"].astype(str).str.contains(search_mat_id, case=False, na=False)]
        if search_mat_status == "Active Only":
            filtered_df = filtered_df[filtered_df["EMP_Status"].str.upper() == "ACTIVE"]
        elif search_mat_status == "In-Active Only":
            filtered_df = filtered_df[filtered_df["EMP_Status"].str.upper() == "IN-ACTIVE"]

        selected_day_cols = [f"D{d:02d}" for d in range(start_day, end_day + 1)]
        
        # Grid column order setup
        grid_columns_order = (
            ["Month_Year", "EMP_ID", "EMP_Name"] + selected_day_cols + 
            ["Over_Time", "Less_Time", "Total_Hours", "Total_Minutes", "Total_Days", "Base_Monthly_Comp", 
             "Rate_Per_Hour", "Rate_Per_Minute", "Gross_Payout", "Payment_Status", "Start_Date", "Last_Date", "EMP_Status"]
        )
        
        validated_columns = [col for col in grid_columns_order if col in filtered_df.columns]
        render_df = filtered_df[validated_columns]

        cfg = {
            "Month_Year": st.column_config.TextColumn("Month_Year", width="small", disabled=True),
            "EMP_ID": st.column_config.TextColumn("EMP ID", width="small", disabled=True),
            "EMP_Name": st.column_config.TextColumn("Employee Name", width="medium", disabled=True),
            "Over_Time": st.column_config.NumberColumn("Extra Hrs", format="%.2f", width="small", disabled=True),
            "Less_Time": st.column_config.NumberColumn("Short Hrs", format="%.2f", width="small", disabled=True),
            "Total_Hours": st.column_config.NumberColumn("Total Hrs", format="%.2f", width="small", disabled=True),
            "Total_Minutes": st.column_config.NumberColumn("Total Min", format="%.0f", width="small", disabled=True),
            "Total_Days": st.column_config.NumberColumn("Total Days", format="%.1f", width="small", disabled=True),
            "Base_Monthly_Comp": st.column_config.NumberColumn("Base Comp Rate", format="₹%.2f", width="small", disabled=True),
            "Rate_Per_Hour": st.column_config.NumberColumn("Hourly Rate", format="₹%.2f", width="small", disabled=True),
            "Rate_Per_Minute": st.column_config.NumberColumn("Per Min Rate", format="₹%.4f", width="small", disabled=True),
            "Gross_Payout": st.column_config.NumberColumn("Calculated Gross Payout", format="₹%.2f", width="medium", disabled=True),
            "Payment_Status": st.column_config.SelectboxColumn("Payment Status", width="medium", options=["Pending", "Done"], required=True),
            "EMP_Status": st.column_config.TextColumn("EMP Status", width="small", disabled=True)
        }
        for d_col in selected_day_cols:
            if d_col in validated_columns:
                cfg[d_col] = st.column_config.TextColumn(d_col.replace("D", ""), width=45, disabled=True)

        edited_df = st.data_editor(render_df, hide_index=True, width="stretch", column_config=cfg, key="attendance_ledger_data_editor")
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 4 - SUB-PART 4B (SYNC, FORMULAS & EXPORTS)
# ============================================================================

        # Detect modifications and execute dynamic database updates
        if st.session_state.attendance_ledger_data_editor.get("edited_rows"):
            modifications = st.session_state.attendance_ledger_data_editor["edited_rows"]
            for numeric_index_str, altered_props in modifications.items():
                row_idx = int(numeric_index_str)
                if "Payment_Status" in altered_props:
                    target_emp = render_df.iloc[row_idx]["EMP_ID"]
                    target_month = render_df.iloc[row_idx]["Month_Year"]
                    updated_val = altered_props["Payment_Status"]
                    
                    with st.spinner(f"Updating status for {target_emp}..."):
                        if update_db_payment_status(target_emp, target_month, updated_val):
                            st.success(f"✓ Synchronised Ledger Row status to '{updated_val}' for Employee ID: {target_emp}")
                            st.cache_data.clear()
                            st.rerun()

        # Formulas Reference block
        st.html("<hr>")
        st.markdown("### 🧮 Workforce Payroll Calculation Formulas")
        f_col1, f_col2, f_col3 = st.columns(3)
        with f_col1:
            st.info("**1. Per Minute Rate Engine**\n\n\[\text{Rate per Min} = \frac{\text{Base Monthly Comp} / \text{Days in Month}}{\text{Shift Hours} \times 60}\]")
        with f_col2:
            st.info("**2. Total Minutes Sourced**\n\n\[\text{Total Minutes} = \text{Total Hours (From DB)} \times 60\]")
        with f_col3:
            st.info("**3. Consolidated Gross Payout**\n\n\[\text{Gross Payout} = \text{Total Minutes} \times \text{Rate per Min}\]")
            
        # Expandable Breakdown Section
        with st.expander("🔍 Click to view Fractional Shift Conversion and Payout Example (e.g. '11/30')"):
            st.markdown("""
            When processing complex shorthand strings in memory (e.g., if a record column value needs fallback processing), fractional time tokens split hour and minute indices using the `/` parameter:
            
            ##### **Step A: Hour Conversion Formula**
            \[\text{Decimal Hours} = \text{Hours Component} + \left( \frac{\text{Minutes Component}}{60} \right)\]
            
            * **Example Token Entry:** `11/30`
            * **Calculation:** \[11 + \left( \frac{30}{60} \right) = 11 + 0.50 = \mathbf{11.50\text{ Hours}}\]
            
            ##### **Step B: Practical Payout Example Match**
            Let's trace a concrete payout calculation using an active employee profile:
            * **Employee Profile parameters:** Monthly Base Salary = **₹30,000**, Contracted Shift Target = **12 Hours**, Month = **September (30 Days)**.
            * **Total Hours Worked (From DB or Fallback):** Assume an employee logs exactly one `11/30` shift in the entire month frame (**11.50 Hours total**).
            
            1. **Daily Wage Base Rate:** \[₹30,000 / 30 \text{ Days} = ₹1,000 \text{ per day}\]
            2. **Hourly Wage Base Rate:** \[₹1,000 / 12 \text{ Shift Hours} = ₹83.3333 \text{ per hour}\]
            3. **Per Minute Wage Base Rate:** \[₹83.3333 / 60 \text{ Minutes} = \mathbf{₹1.3889\text{ per minute}}\]
            4. **Convert Total Time to Minutes:** \[11.50 \text{ Hours} \times 60 \text{ Minutes} = \mathbf{690\text{ Minutes}}\]
            5. **Final Gross Payout calculation Result:** \[690 \text{ Minutes} \times ₹1.3889 = \mathbf{₹958.33}\]
            """)
        st.html("<hr>")

        # 📥 Original Data Export Workspace (Completely Unaltered)
        st.markdown("#### 📥 Export Historical Attendance Matrix Ledger")
        down_col1, down_col2 = st.columns(2)
        
        with down_col1:
            csv_df = edited_df.copy()
            for col in csv_df.columns:
                if col.startswith("D") and col[1:].isdigit():
                    csv_df[col] = csv_df[col].apply(lambda x: f"\t{x}" if (isinstance(x, str) and "/" in x) else x)
            csv_buffer = io.StringIO()
            csv_df.to_csv(csv_buffer, index=False)
            st.download_button(
                label="📊 Download Ledger as CSV (Preserve Formats)", data=csv_buffer.getvalue(),
                file_name=f"Historical_Attendance_Ledger_{datetime.date.today()}.csv", mime="text/csv", key="ledger_csv_download_btn"
            )
            
        with down_col2:
            def generate_ledger_matrix_pdf(dataframe):
                pdf_buffer = io.BytesIO()
                document = SimpleDocTemplate(pdf_buffer, pagesize=landscape(letter), rightMargin=20, leftMargin=20, topMargin=30, bottomMargin=30)
                story_components = []
                pdf_styles = getSampleStyleSheet()
                title_text_style = ParagraphStyle('LedgerTitleStyle', parent=pdf_styles['Heading1'], fontSize=14, leading=18, textColor=colors.HexColor("#1A365D"), alignment=0)
                header_cell_style = ParagraphStyle('LedgerHeaderStyle', parent=pdf_styles['Normal'], fontSize=6, leading=8, textColor=colors.white, fontName="Helvetica-Bold")
                data_cell_style = ParagraphStyle('LedgerDataStyle', parent=pdf_styles['Normal'], fontSize=5, leading=7, textColor=colors.black)
                
                story_components.append(Paragraph("Main Historical Attendance Matrix Ledger", title_text_style))
                story_components.append(Spacer(1, 10))
                headers = list(dataframe.columns)
                pdf_table_data = [[Paragraph(f"<b>{h}</b>", header_cell_style) for h in headers]]
                
                for _, row_data in dataframe.iterrows():
                    row_cells = []
                    for header_item in headers:
                        val = row_data[header_item]
                        val_str = f"{val:.2f}" if isinstance(val, float) else str(val)
                        row_cells.append(Paragraph(val_str, data_cell_style))
                    pdf_table_data.append(row_cells)
                
                total_cols = len(headers)
                available_width = 752  
                column_width = max(20, available_width / total_cols)
                matrix_table = Table(pdf_table_data, colWidths=[column_width]*total_cols, repeatRows=1)
                matrix_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2B6CB0")), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E0")),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
                    ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ]))
                story_components.append(matrix_table)
                document.build(story_components)
                pdf_buffer.seek(0)
                return pdf_buffer.getvalue()

            if not edited_df.empty:
                st.download_button(
                    label="📄 Download Ledger as PDF (Landscape)", data=generate_ledger_matrix_pdf(edited_df),
                    file_name=f"Historical_Attendance_Ledger_{datetime.date.today()}.pdf", mime="application/pdf", key="ledger_pdf_download_btn"
                )
            else:
                st.button("📄 Download Ledger as PDF (Landscape)", disabled=True)
