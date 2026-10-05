# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 1 OF 3 (API ROUTING & INGESTION)
# ============================================================================

import streamlit as st
import pandas as pd
import requests
import json
import io
import re  
import datetime
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

# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: INITIAL DATA PROCESSING LOOP
# ============================================================================

st.title("📋 Enterprise Attendance & Workforce Analytics Console")
st.markdown("Monitor rolling month-wise employee shift parameters, calendar duration windows, and dynamic payroll payouts.")

# Load Raw Datasets from Synced Production Pools
raw_attendance_data = fetch_raw_attendance_feed()
master_emp_data = fetch_cntr_employee_master()

# Compile Employee Profile Metadata Map directly from cntr_employee_master
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
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 2 - SUB-PART A (DATASET INTERFACE SETUP)
# ============================================================================

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
        
        meta = emp_metadata_map.get(emp_id_str, {
            "start_date": "N/A", 
            "last_day_of_work": "N/A", 
            "employee_status": "Active",
            "comp_monthly": 0.00,
            "shift_hours": 12.00
        })
        
        def safe_float(val):
            if val is None or str(val).strip() == "" or str(val).lower() == "none": return 0.00
            try: return float(val)
            except: return 0.00

        total_hours_worked = safe_float(item.get("total_hours"))
        total_days_worked = safe_float(item.get("total_days"))
        
        current_status = meta.get("employee_status", "Active")
        configured_monthly_comp = meta.get("comp_monthly", 0.00)
        configured_shift_hours = meta.get("shift_hours", 12.00)
        
        if current_status.upper() == "ACTIVE":
            standard_monthly_days = 26.0
            per_hour_rate = (configured_monthly_comp / standard_monthly_days) / configured_shift_hours
            calculated_gross_payout = per_hour_rate * total_hours_worked
        else:
            per_hour_rate = 0.00
            calculated_gross_payout = 0.00

        row_dict = {
            "Month_Year": m_yr,
            "EMP_ID": item.get("employee_id") or "N/A",
            "EMP_Name": item.get("employee_name") or "Unnamed",
            "Over_Time": safe_float(item.get("over_time")),
            "Less_Time": safe_float(item.get("less_time")),
            "Total_Hours": total_hours_worked,
            "Total_Days": total_days_worked,
            "Start_Date": meta.get("start_date", "N/A"),
            "Last_Date": meta.get("last_day_of_work", "N/A"),
            "EMP_Status": current_status,
            "Base_Monthly_Comp": configured_monthly_comp,
            "Rate_Per_Hour": per_hour_rate,
            "Gross_Payout": calculated_gross_payout,
            "DB_Show_Flag": item.get("show") if item.get("show") is not None else True
        }
        
        for day in range(1, 32):
            row_dict[f"D{day:02d}"] = days_list[day-1] if (days_list and day-1 < len(days_list)) else ""
            
        processed_rows.append(row_dict)
        
    df = pd.DataFrame(processed_rows)
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 2 - SUB-PART B (FILTERS & RENDER ENGINE)
# ============================================================================

    st.markdown("### 🖥️ Main Historical Attendance Matrix Ledger")
    
    mat_col1, mat_col2, mat_col3, mat_col4 = st.columns(4)
    with mat_col1:
        search_mat_id = st.text_input("Filter Ledger by Employee ID:", "", key="mat_id_input").strip()
    with mat_col2:
        search_mat_name = st.text_input("Filter Ledger by Employee Name:", "", key="mat_name_input").strip()
    with mat_col3:
        search_mat_month = st.selectbox("Filter Ledger by Month Frame:", options=["All Months"] + sorted(list(available_months_list)), key="mat_month_input")
    with mat_col4:
        search_mat_status = st.selectbox("Filter Ledger by Employee Status:", options=["All Statuses", "Active Only", "In-Active Only"], key="mat_status_input")
        
    mat_col_slider = st.columns(1)
    with mat_col_slider:
        start_day, end_day = st.slider(
            "Select Day Duration Truncation Range:",
            min_value=1, max_value=31, value=(1, 31), key="mat_day_slider"
        )

    # Apply row visibility filters
    filtered_df = df[df["DB_Show_Flag"] == True]
    
    if search_mat_id:
        filtered_df = filtered_df[filtered_df["EMP_ID"].astype(str).str.contains(search_mat_id, case=False, na=False)]
    if search_mat_name:
        filtered_df = filtered_df[filtered_df["EMP_Name"].astype(str).str.contains(search_mat_name, case=False, na=False)]
    if search_mat_month != "All Months":
        filtered_df = filtered_df[filtered_df["Month_Year"] == search_mat_month]
    if search_mat_status == "Active Only":
        filtered_df = filtered_df[filtered_df["EMP_Status"].str.upper() == "ACTIVE"]
    elif search_mat_status == "In-Active Only":
        filtered_df = filtered_df[filtered_df["EMP_Status"].str.upper() == "IN-ACTIVE"]

    selected_day_cols = [f"D{d:02d}" for d in range(start_day, end_day + 1)]

    grid_columns_order = (
        ["Month_Year", "EMP_ID", "EMP_Name"] + 
        selected_day_cols + 
        ["Over_Time", "Less_Time", "Total_Hours", "Total_Days", "Base_Monthly_Comp", "Rate_Per_Hour", "Gross_Payout", "Start_Date", "Last_Date", "EMP_Status"]
    )
    render_df = filtered_df[grid_columns_order]

    cfg = {
        "Month_Year": st.column_config.TextColumn("Month_Year", width="small"),
        "EMP_ID": st.column_config.TextColumn("EMP ID", width="small"),
        "EMP_Name": st.column_config.TextColumn("Employee Name", width="medium"),
        "Over_Time": st.column_config.NumberColumn("Extra Hrs", format="%.2f", width="small"),
        "Less_Time": st.column_config.NumberColumn("Short Hrs", format="%.2f", width="small"),
        "Total_Hours": st.column_config.NumberColumn("Total Hrs", format="%.2f", width="small"),
        "Total_Days": st.column_config.NumberColumn("Total Days", format="%.1f", width="small"),
        "Base_Monthly_Comp": st.column_config.NumberColumn("Base Comp Rate", format="₹%.2f", width="small"),
        "Rate_Per_Hour": st.column_config.NumberColumn("Hourly Rate", format="₹%.2f", width="small"),
        "Gross_Payout": st.column_config.NumberColumn("Calculated Gross Payout", format="₹%.2f", width="medium"),
        "EMP_Status": st.column_config.TextColumn("EMP Status", width="small")
    }
    for d_col in selected_day_cols:
        cfg[d_col] = st.column_config.TextColumn(d_col.replace("D", ""), width=45)

    st.dataframe(render_df, hide_index=True, width="stretch", column_config=cfg)
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 2 - SUB-PART C (EXPORT WORKSPACE)
# ============================================================================

    # 📥 DATA EXPORT WORKSPACE (CSV Fix & Matrix Landscape PDF Exporter)
    st.markdown("#### 📥 Export Historical Attendance Matrix Ledger")
    down_col1, down_col2 = st.columns(2)
    
    with down_col1:
        # Prepend escape token to stop spreadsheet programs converting fractional text like "10/30" to Date objects
        csv_df = render_df.copy()
        for col in csv_df.columns:
            if col.startswith("D") and col[1:].isdigit():
                csv_df[col] = csv_df[col].apply(lambda x: f"\t{x}" if (isinstance(x, str) and "/" in x) else x)
        
        csv_buffer = io.StringIO()
        csv_df.to_csv(csv_buffer, index=False)
        
        st.download_button(
            label="📊 Download Ledger as CSV (Preserve Formats)",
            data=csv_buffer.getvalue(),
            file_name=f"Historical_Attendance_Ledger_{datetime.date.today()}.csv",
            mime="text/csv",
            key="ledger_csv_download_btn"
        )
        
    with down_col2:
        def generate_ledger_matrix_pdf(dataframe):
            pdf_buffer = io.BytesIO()
            document = SimpleDocTemplate(
                pdf_buffer, pagesize=landscape(letter),
                rightMargin=20, leftMargin=20, topMargin=30, bottomMargin=30
            )
            story_components = []
            pdf_styles = getSampleStyleSheet()
            
            title_text_style = ParagraphStyle(
                'LedgerTitleStyle', parent=pdf_styles['Heading1'],
                fontSize=14, leading=18, textColor=colors.HexColor("#1A365D"), alignment=0
            )
            header_cell_style = ParagraphStyle(
                'LedgerHeaderStyle', parent=pdf_styles['Normal'],
                fontSize=6, leading=8, textColor=colors.white, fontName="Helvetica-Bold"
            )
            data_cell_style = ParagraphStyle(
                'LedgerDataStyle', parent=pdf_styles['Normal'],
                fontSize=5, leading=7, textColor=colors.black
            )
            
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
            available_width = 752  # 792 (landscape letter width) - 40 (margins)
            column_width = max(20, available_width / total_cols)
            calculated_widths = [column_width] * total_cols
            
            matrix_table = Table(pdf_table_data, colWidths=calculated_widths, repeatRows=1)
            matrix_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2B6CB0")),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E0")),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            
            story_components.append(matrix_table)
            document.build(story_components)
            pdf_buffer.seek(0)
            return pdf_buffer.getvalue()

        if not render_df.empty:
            ledger_pdf_bytes = generate_ledger_matrix_pdf(render_df)
            st.download_button(
                label="📄 Download Ledger as PDF (Landscape)",
                data=ledger_pdf_bytes,
                file_name=f"Historical_Attendance_Ledger_{datetime.date.today()}.pdf",
                mime="application/pdf",
                key="ledger_pdf_download_btn"
            )
        else:
            st.button("📄 Download Ledger as PDF (Landscape)", disabled=True)
