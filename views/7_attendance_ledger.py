# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 1 OF 3 (API ROUTING & INGESTION)
# ============================================================================

import streamlit as st
import pandas as pd
import requests
import json
import io
import datetime
from reportlab.lib.pagesizes import letter
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
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 2 OF 3 (MAIN LEDGER AND ON-PAGE FILTERS)
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
    with mat_col_slider[0]:
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
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 3 - FRAGMENT A1 (OVERRIDE FILTER ROW)
# ============================================================================

    st.markdown("---")
    st.markdown("### 🧾 Interactive Salary Slip Generator Window")
    st.markdown("Select an employee row and apply specific overrides.")

    if filtered_df.empty:
        st.warning("⚠️ No rows currently match your global ledger filters.")
    else:
        employee_options = []
        for idx, row in filtered_df.iterrows():
            employee_options.append(f"{row['EMP_ID']} - {row['EMP_Name']} ({row['Month_Year']})")
            
        selected_emp_string = st.selectbox(
            "Choose Profile Target for Payslip:", 
            options=employee_options, 
            key="slip_profile_select"
        )
        
        if selected_emp_string:
            selected_idx = employee_options.index(selected_emp_string)
            emp_data = filtered_df.iloc[selected_idx].copy()
            
            st.markdown("#### 🛠️ On-Screen Payslip Parameter Overrides")
            slip_f_col1, slip_filter_col2, slip_filter_col3 = st.columns(3)
            
            with slip_f_col1:
                # 📅 1. Pay Cycle Date Frame Override Filter
                override_month = st.text_input(
                    "Override Pay Period (Month-Year):", 
                    value=str(emp_data['Month_Year']), 
                    key="slip_override_month"
                )
                emp_data['Month_Year'] = override_month
                
            with slip_filter_col2:
                # 👤 2. Employee Status Override Toggle Filter
                override_status = st.selectbox(
                    "Override Profile Status:", 
                    options=["Active", "In-Active"], 
                    index=0 if str(emp_data['EMP_Status']).upper() == "ACTIVE" else 1, 
                    key="slip_override_status"
                )
                emp_data['EMP_Status'] = override_status
                
            with slip_filter_col3:
                # 📅 3. Day Duration Truncation Range Slider Filter
                slip_start_day, slip_end_day = st.slider(
                    "Select Day Duration Truncation Range:",
                    min_value=1, max_value=31, value=(1, 31), 
                    key="slip_day_duration_slider"
                )
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 3 - FRAGMENT A2 (RECALCULATION ENGINE & CARD)
# ============================================================================

            # Recalculate financial parameters instantly based on live on-screen overrides
            days_count_override = 0.0
            days_array_source = []
            
            # Extract day grid marks from the selected range bounds
            for day in range(slip_start_day, slip_end_day + 1):
                day_mark = str(emp_data.get(f"D{day:02d}", "")).strip().upper()
                days_array_source.append(day_mark)
                if "P" in day_mark or (day_mark.isdigit() and float(day_mark) > 0):
                    days_count_override += 1.0
            
            # Recompute total hour layers dynamically using standard 12-hour shifts
            hours_worked_override = days_count_override * 12.0
            emp_data['Total_Days'] = days_count_override
            emp_data['Total_Hours'] = hours_worked_override
            
            # Run the dynamic pay engine formula based on your chosen status filter override
            if str(emp_data['EMP_Status']).upper() == "ACTIVE":
                standard_monthly_days = 26.0
                hourly_rate_recalculated = (float(emp_data['Base_Monthly_Comp']) / standard_monthly_days) / 12.0
                gross_payout_recalculated = hourly_rate_recalculated * hours_worked_override
            else:
                hourly_rate_recalculated = 0.00
                gross_payout_recalculated = 0.00
                
            emp_data['Rate_Per_Hour'] = hourly_rate_recalculated
            emp_data['Gross_Payout'] = gross_payout_recalculated
            
            # Render Live Recalculated Values Card on the screen
            slip_card_col1, slip_card_col2 = st.columns(2)
            with slip_card_col1:
                st.markdown(f"**Employee ID & Name:** {emp_data['EMP_ID']} - {emp_data['EMP_Name']}")
                st.markdown(f"**Pay Cycle Period:** {emp_data['Month_Year']}")
                st.markdown(f"**Roster Profile Status:** `{emp_data['EMP_Status']}`")
                st.markdown(f"**Truncated Range Worked:** {emp_data['Total_Days']:.1f} Days (Days {slip_start_day} to {slip_end_day})")
            with slip_card_col2:
                st.markdown(f"**Base Configured Salary:** ₹ {emp_data['Base_Monthly_Comp']:,.2f}")
                st.markdown(f"**Calculated Hourly Rate:** ₹ {emp_data['Rate_Per_Hour']:,.2f} / hr")
                st.markdown(f"**Recalculated Hours Logged:** {emp_data['Total_Hours']:.2f} Hours")
                st.markdown(f"### **Net Payroll Payout:** ₹ {emp_data['Gross_Payout']:,.2f}")
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 3 - FRAGMENT A3 (PDF COMPILER ENGINE)
# ============================================================================

            # Professional PDF compilation engine
            def generate_salary_slip_pdf(data, s_day, e_day):
                buffer = io.BytesIO()
                doc = SimpleDocTemplate(
                    buffer, pagesize=letter, 
                    rightMargin=40, leftMargin=40, 
                    topMargin=40, bottomMargin=40
                )
                story = []
                
                styles = getSampleStyleSheet()
                title_style = ParagraphStyle(
                    'TitleStyle', parent=styles['Heading1'], 
                    fontSize=20, leading=24, 
                    textColor=colors.HexColor("#1A365D"), alignment=1
                )
                sub_style = ParagraphStyle(
                    'SubStyle', parent=styles['Normal'], 
                    fontSize=10, leading=14, 
                    textColor=colors.gray, alignment=1
                )
                heading_style = ParagraphStyle(
                    'HeadingStyle', parent=styles['Heading2'], 
                    fontSize=12, leading=16, 
                    textColor=colors.HexColor("#2B6CB0"), 
                    spaceBefore=10, spaceAfter=10
                )
                body_style = ParagraphStyle(
                    'BodyStyle', parent=styles['Normal'], 
                    fontSize=10, leading=14
                )
                
                story.append(Paragraph("CLASSIC INDUSTRIES", title_style))
                story.append(Paragraph("Automated Employee Monthly Payslip Statement", sub_style))
                story.append(Spacer(1, 15))
                
                # ✔️ FIXED LAYOUT ARRAY BOUNDS: Locked explicit 132-point boundaries per grid column
                cw1 = [132, 132, 132, 132]
                table_data = [
                    [Paragraph("<b>Employee ID:</b>", body_style), Paragraph(str(data['EMP_ID']), body_style), Paragraph("<b>Pay Period:</b>", body_style), Paragraph(str(data['Month_Year']), body_style)],
                    [Paragraph("<b>Employee Name:</b>", body_style), Paragraph(str(data['EMP_Name']), body_style), Paragraph("<b>Roster Status:</b>", body_style), Paragraph(str(data['EMP_Status']), body_style)],
                    [Paragraph("<b>Onboarding Date:</b>", body_style), Paragraph(str(data['Start_Date']), body_style), Paragraph("<b>Last Day Worked:</b>", body_style), Paragraph(str(data['Last_Date']), body_style)],
                ]
                t1 = Table(table_data, colWidths=cw1)
                t1.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F7FAFC")),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
                    ('PADDING', (0,0), (-1,-1), 8),
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ]))
                story.append(t1)
                story.append(Spacer(1, 15))
                
                story.append(Paragraph("Earnings and Attendance Calculation Matrix Logs", heading_style))
                
                # ✔️ FIXED LAYOUT ARRAY BOUNDS: Locked explicit width distributions across payroll logs
                cw2 = [240, 140, 148]
                salary_data = [
                    [Paragraph("<b>Description</b>", body_style), Paragraph("<b>Metric Value</b>", body_style), Paragraph("<b>Calculated Gross Payout</b>", body_style)],
                    [Paragraph("Base Monthly Salary Rate", body_style), Paragraph("-", body_style), Paragraph(f"INR {data['Base_Monthly_Comp']:,.2f}", body_style)],
                    [Paragraph("Calculated Hourly Processing Rate", body_style), Paragraph(f"INR {data['Rate_Per_Hour']:,.2f} / hr", body_style), Paragraph("-", body_style)],
                    [Paragraph(f"Truncated Days Logged (Days {s_day}-{e_day})", body_style), Paragraph(f"{data['Total_Days']:.1f} Days", body_style), Paragraph("-", body_style)],
                    [Paragraph("Total Recalculated Productive Hours", body_style), Paragraph(f"{data['Total_Hours']:.2f} Hours", body_style), Paragraph("-", body_style)],
                    [Paragraph("Extra Over_Time Balance Hours", body_style), Paragraph(f"{data['Over_Time']:.2f} Hours", body_style), Paragraph("-", body_style)],
                    [Paragraph("Short Less_Time Balance Hours", body_style), Paragraph(f"{data['Less_Time']:.2f} Hours", body_style), Paragraph("-", body_style)],
                    [Paragraph("<b>Net Monthly Payroll Payout</b>", body_style), Paragraph("-", body_style), Paragraph(f"<b>INR {data['Gross_Payout']:,.2f}</b>", body_style)],
                ]
                t2 = Table(salary_data, colWidths=cw2)
                t2.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#EDF2F7")),
                    ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor("#E2E8F0")),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
                    ('PADDING', (0,0), (-1,-1), 8),
                    ('ALIGN', (2,0), (2,-1), 'RIGHT'),
                ]))
                story.append(t2)
                story.append(Spacer(1, 40))
                
                # ✔️ FIXED LAYOUT ARRAY BOUNDS: Locked signature block dimensions evenly
                cw3 = [264, 264]
                sig_data = [
                    [Paragraph("_____________________________<br/>Authorized Signatory Signature", body_style), Paragraph("_____________________________<br/>Employee Acknowledgment Signature", body_style)]
                ]
                t3 = Table(sig_data, colWidths=cw3)
                t3.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER')]))
                story.append(t3)
                
                doc.build(story)
                buffer.seek(0)
                return buffer.getvalue()

            pdf_data = generate_salary_slip_pdf(emp_data, slip_start_day, slip_end_day)
            
            st.download_button(
                label="📥 Generate & Download Salary Slip PDF",
                data=pdf_data,
                file_name=f"Salary_Slip_{emp_data['EMP_ID']}_{emp_data['Month_Year']}.pdf",
                mime="application/pdf",
                type="primary",
                key="slip_pdf_download_btn"
            )
