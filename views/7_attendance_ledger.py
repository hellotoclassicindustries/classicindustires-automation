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
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 3 - SUB-PART B (BULK PROCESSING ENGINE)
# ============================================================================

        st.markdown(f"📊 **Current Selection Profile:** Ready to print **{len(batch_target_df)}** payslip statement(s).")
        
        slip_day_row = st.columns(1)
        with slip_day_row[0]:
            b_start_day, b_end_day = st.slider(
                "Select Day Truncation Filter (For Target Payslips):",
                min_value=1, max_value=31, value=(1, 31), key="bulk_slip_day_slider"
            )

        processed_payslips_pool = []
        
        for idx, row in batch_target_df.iterrows():
            emp_rec = row.copy()
            emp_id_clean = str(emp_rec['EMP_ID']).strip().upper()
            meta_profile = emp_metadata_map.get(emp_id_clean, {})
            
            configured_shift_hours = float(meta_profile.get("shift_hours", 12.00))
            total_days_in_range = float((b_end_day - b_start_day) + 1)
            
            empty_cells, absent_cells, total_whole_hours, total_minutes = 0.0, 0.0, 0.0, 0.0
            
            for day in range(b_start_day, b_end_day + 1):
                day_mark = str(emp_rec.get(f"D{day:02d}", "")).strip().upper()
                
                if day_mark in ["", "NONE"] or day_mark.isspace():
                    empty_cells += 1.0
                    continue
                if day_mark == "A":
                    absent_cells += 1.0
                    continue
                if day_mark == "P":
                    total_whole_hours += configured_shift_hours
                elif "/" in day_mark:
                    try:
                        parts = day_mark.split("/")
                        total_whole_hours += float(parts[0])
                        total_minutes += float(parts[1])
                    except: continue
                elif "P" in day_mark:
                    total_whole_hours += configured_shift_hours
                    num_digits = re.sub(r"[^0-9.]", "", day_mark)
                    if num_digits: total_whole_hours += float(num_digits)
                elif day_mark.isdigit() or re.match(r"^\d+?\.\d+?$", day_mark):
                    total_whole_hours += float(day_mark)
            
            days_count_override = total_days_in_range - (empty_cells + absent_cells)
            hours_worked_override = round(total_whole_hours + (total_minutes / 60.0), 2)
            
            emp_rec['Total_Days'] = days_count_override
            emp_rec['Total_Hours'] = hours_worked_override
            
            if str(emp_rec['EMP_Status']).upper() == "ACTIVE":
                standard_monthly_days = 26.0
                hourly_rate = (float(emp_rec['Base_Monthly_Comp']) / standard_monthly_days) / configured_shift_hours
                gross_payout = hourly_rate * hours_worked_override
            else:
                hourly_rate, gross_payout = 0.00, 0.00
                
            emp_rec['Rate_Per_Hour'] = hourly_rate
            emp_rec['Gross_Payout'] = gross_payout
            processed_payslips_pool.append(emp_rec)

        if processed_payslips_pool:
            with st.expander("👁️ View Summary Panel List"):
                for p_slip in processed_payslips_pool:
                    st.write(f"▪️ **{p_slip['EMP_ID']}** - {p_slip['EMP_Name']} ({p_slip['Month_Year']}) | Net Pay: **₹{p_slip['Gross_Payout']:,.2f}**")
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 3 - SUB-PART C (BATCH COMPILER)
# ============================================================================

        def generate_consolidated_payslips_pdf(slips_list, s_day, e_day):
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer, pagesize=letter, 
                rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40
            )
            story = []
            styles = getSampleStyleSheet()
            
            title_style = ParagraphStyle('TStyle', parent=styles['Heading1'], fontSize=20, leading=24, textColor=colors.HexColor("#1A365D"), alignment=1)
            sub_style = ParagraphStyle('SStyle', parent=styles['Normal'], fontSize=10, leading=14, textColor=colors.gray, alignment=1)
            heading_style = ParagraphStyle('HStyle', parent=styles['Heading2'], fontSize=12, leading=16, textColor=colors.HexColor("#2B6CB0"), spaceBefore=10, spaceAfter=5)
            body_style = ParagraphStyle('BStyle', parent=styles['Normal'], fontSize=9, leading=13)
            
            for i, data in enumerate(slips_list):
                if i > 0:
                    from reportlab.platypus import PageBreak
                    story.append(PageBreak())
                    
                story.append(Paragraph("CLASSIC INDUSTRIES", title_style))
                story.append(Paragraph("Automated Employee Monthly Payslip Statement", sub_style))
                story.append(Spacer(1, 15))
                
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
                    ('PADDING', (0,0), (-1,-1), 6),
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ]))
                story.append(t1)
                story.append(Spacer(1, 10))
                
                story.append(Paragraph("Earnings and Attendance Calculation Matrix Logs", heading_style))
                
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
                    ('PADDING', (0,0), (-1,-1), 6),
                    ('ALIGN', (2,0), (2,-1), 'RIGHT'),
                ]))
                story.append(t2)
                story.append(Spacer(1, 30))
                
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

        if processed_payslips_pool:
            batch_pdf_data = generate_consolidated_payslips_pdf(processed_payslips_pool, b_start_day, b_end_day)
            
            st.download_button(
                label=f"📥 Download {len(processed_payslips_pool)} Payslip(s) as Consolidated PDF",
                data=batch_pdf_data,
                file_name=f"Batch_Payslips_{datetime.date.today()}.pdf",
                mime="application/pdf",
                type="primary",
                key="bulk_payslip_pdf_btn"
            )
