# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 1 (VIEW ROUTING & GLOBAL UTILITIES)
# ============================================================================

import streamlit as st
import pandas as pd
import requests
import json
import io
import re  
import datetime
import calendar
import math
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

# 🛠️ GLOBAL HELPERS: Declared at top-level module scope to avoid runtime NameErrors
def safe_float(val):
    """Safely converts database parameters into float values"""
    if val is None or str(val).strip() == "" or str(val).lower() == "none":
        return 0.00
    try:
        return float(val)
    except:
        return 0.00

@st.cache_data(ttl=2)
def fetch_vw_attendance_ledger():
    """Queries the newly deployed public.vw_attendance_ledger Supabase view"""
    endpoint = f"{SUPABASE_URL.strip('/')}/rest/v1/vw_attendance_ledger?order=month_year.desc,employee_id.asc"
    try:
        response = requests.get(endpoint, headers=HEADERS)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception:
        return []

def update_db_payment_status(employee_id, month_year, new_status):
    """Performs transactional REST PATCH to save payment status down to raw_attendance_feed"""
    endpoint = f"{SUPABASE_URL.strip('/')}/rest/v1/raw_attendance_feed?employee_id=eq.{employee_id}&month_year=eq.{month_year}"
    payload = {"payment_status": new_status}
    try:
        res = requests.patch(endpoint, headers=HEADERS, json=payload)
        return res.status_code in [200, 201, 204]
    except Exception:
        return False

def parse_row_date(month_year_str):
    """Maps string variations like 'September-2026' into a proper datetime.date object"""
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
    """Extracts actual days available inside specific timeline string as an integer"""
    dt = parse_row_date(month_year_str)
    if dt:
        return int(calendar.monthrange(dt.year, dt.month)[1])
    return 31
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 2 (FILTERS ENGINE & COMPUTATION MATRIX)
# ============================================================================

# Load combined layout metrics straight from your joint Supabase database view
view_records_data = fetch_vw_attendance_ledger()

if not view_records_data:
    st.info("📋 System Log: No integrated database rows found inside the vw_attendance_ledger workspace view.")
else:
    # 📆 Calculate previous calendar month parameters automatically
    today = datetime.date.today()
    past_month_date = today - relativedelta(months=1)
    
    default_start = past_month_date.replace(day=1)
    default_end = past_month_date.replace(day=int(calendar.monthrange(past_month_date.year, past_month_date.month)[1]))

    # Single Calendar input widget setup with an isolated unique key
    chosen_dates = st.date_input(
        "Select Payout Month:",
        value=(default_start, default_end),
        key="unique_attendance_calendar_range_picker"
    )

    if isinstance(chosen_dates, tuple) and len(chosen_dates) == 2:
        start_cal, end_cal = chosen_dates
    else:
        start_cal, end_cal = default_start, default_end

    # Search filter layout columns row
    mat_col1, mat_col2, mat_col4 = st.columns(3)
    with mat_col1:
        search_mat_id = st.text_input("Filter by Employee ID:", "", key="mat_id_input").strip()
    with mat_col2:
        search_mat_name = st.text_input("Filter by Employee Name:", "", key="mat_name_input").strip()
    with mat_col4:
        search_mat_status = st.selectbox("Filter by Employee Status:", options=["All Statuses", "Active Only", "In-Active Only"], key="mat_status_input")

    # Processing array mapping loop
    processed_rows = []
    for item in view_records_data:
        m_yr = item.get("month_year") or "N/A"
        row_dt = parse_row_date(m_yr)
        
        # Filter rows by calendar input bounds
        if row_dt:
            if not (start_cal <= row_dt <= end_cal):
                continue

        # DATABASE SOURCING: Pull raw data from database view columns
        total_hours_worked = safe_float(item.get("total_hours"))
        total_days_worked = safe_float(item.get("total_days"))  
        base_monthly_comp = safe_float(item.get("base_monthly_comp"))
        configured_shift_hours = safe_float(item.get("shift_hours") or 8.00)  
        current_status = item.get("employee_status") or "Active"
        days_list = item.get("attendance_days") or []
        
        # 🧮 IN-MEMORY PAYROLL CALCULATIONS (Pure RAM Math with explicit rounding)
        total_minutes_worked = round(total_hours_worked * 60.0, 2)
        row_month_days = get_days_in_month(m_yr)

        if configured_shift_hours > 0:
            actual_days_worked = round(total_hours_worked / configured_shift_hours, 2)
        else:
            actual_days_worked = 0.00

        if current_status.upper() == "ACTIVE" and row_month_days > 0 and configured_shift_hours > 0:
            # Calculate daily allocation base
            daily_allocation_rate = base_monthly_comp / float(row_month_days)
            
            # Enforce strict in-memory rounding up for currency rates
            per_hour_rate = math.ceil((daily_allocation_rate / configured_shift_hours) * 100) / 100.0
            per_minute_rate = math.ceil((per_hour_rate / 60.0) * 10000) / 10000.0
            
            # Final Gross compensation rounded neatly to standard pennies
            calculated_gross_payout = round(total_hours_worked * per_hour_rate, 2)
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
            "Total_Days": total_days_worked,                   
            "Actual_Days_Worked": actual_days_worked,           
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
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 3 (TABLE GRAPHICS ENGINE)
# ============================================================================

    if df.empty:
        st.warning("⚠️ No integrated view records match the active tracking filters selected.")
    else:
        # Apply filter conditions
        filtered_df = df[df["DB_Show_Flag"] == True].copy()
        if search_mat_id:
            filtered_df = filtered_df[filtered_df["EMP_ID"].astype(str).str.contains(search_mat_id, case=False, na=False)]
        if search_mat_name:
            filtered_df = filtered_df[filtered_df["EMP_Name"].astype(str).str.contains(search_mat_name, case=False, na=False)]
        if search_mat_status == "Active Only":
            filtered_df = filtered_df[filtered_df["EMP_Status"].str.upper() == "ACTIVE"]
        elif search_mat_status == "In-Active Only":
            filtered_df = filtered_df[filtered_df["EMP_Status"].str.upper() == "IN-ACTIVE"]

        # Enforced static 31-day array grid column layout
        all_day_cols = [f"D{d:02d}" for d in range(1, 32)]
        
        grid_columns_order = (
            ["Month_Year", "EMP_ID", "EMP_Name"] + all_day_cols + 
            ["Over_Time", "Less_Time", "Total_Hours", "Total_Minutes", "Total_Days", "Actual_Days_Worked", "Base_Monthly_Comp", 
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
            "Total_Minutes": st.column_config.NumberColumn("Total Min (RAM)", format="%.2f", width="small", disabled=True),
            "Total_Days": st.column_config.NumberColumn("Raw Days Present", format="%.0f", width="small", disabled=True),
            "Actual_Days_Worked": st.column_config.NumberColumn("Actual Days Worked (Proportional)", format="%.2f", width="medium", disabled=True),
            "Base_Monthly_Comp": st.column_config.NumberColumn("Base Comp Rate", format="₹%.2f", width="small", disabled=True),
            "Rate_Per_Hour": st.column_config.NumberColumn("Hourly Rate (RAM)", format="₹%.2f", width="small", disabled=True),
            "Rate_Per_Minute": st.column_config.NumberColumn("Per Min Rate (RAM)", format="₹%.4f", width="small", disabled=True),
            "Gross_Payout": st.column_config.NumberColumn("Calculated Gross Payout", format="₹%.2f", width="medium", disabled=True),
            "Payment_Status": st.column_config.SelectboxColumn("Payment Status", width="medium", options=["Pending", "Done"], required=True),
            "EMP_Status": st.column_config.TextColumn("EMP Status", width="small", disabled=True)
        }
        for d_col in all_day_cols:
            if d_col in validated_columns:
                cfg[d_col] = st.column_config.TextColumn(d_col.replace("D", ""), width=45, disabled=True)

        edited_df = st.data_editor(render_df, hide_index=True, width="stretch", column_config=cfg, key="attendance_ledger_data_editor")
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 4 (SYNC & EXPORT WORKSPACES)
# ============================================================================

        # Handle user edits to update payment status back to public.raw_attendance_feed
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
            st.info("**2. Proportional Days Math**\n\n\[\text{Actual Days Worked} = \frac{\text{Total Hours Worked (From DB)}}{\text{Master Table Shift Hours}}\]")
        with f_col3:
            st.info("**3. Consolidated Gross Payout**\n\n\[\text{Gross Payout} = \text{Total Hours Worked} \times \text{Rate per Hour}\]")
        
        # 🆕 INJECTED INTERACTIVE EXPLANATION MODULE
        st.markdown("---")
        show_math_explanation = st.checkbox("🔍 View: The Math: How 11/30 Becomes 11.5 and Keeps Calculations Exact")
        if show_math_explanation:
            st.success("""
            #### 📐 In-Memory Precision Verification: Time String Expansion
            To ensure billing remains exact across custom logs, strings like **`11/30`** or **`0/40`** are converted to decimal hours:
            * **Extraction Check:** An entry like `11/30` splits into `11` hours and `30` minutes.
            * **Fractional Math:** Minutes are evaluated as: \(\frac{30}{60} = 0.5\text{ Hours}\).
            * **Decimal Aggregation:** Total value resolves exactly to \(11 + 0.5 = \mathbf{11.5\text{ Hours}}\).
            
            ##### 📈 Mathematical Consistency Proof
            * **Total Hours Context:** If an employee logs two `11/30` entries, the system computes \(11.5 + 11.5 = \mathbf{23.0\text{ Hours}}\).
            * **Overtime Context:** Against an 8-hour shift, working `11/30` (11.5 hours) yields exactly \(11.5 - 8 = \mathbf{3.5\text{ Overtime Hours}}\). Two such days accumulate to exactly **7.0 hours** of overtime, with no minutes lost.
            """)
        st.html("<hr>")

        # 📥 Export Workspaces
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
