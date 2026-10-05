# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 1 OF 3 (API ROUTING & INGESTION)
# ============================================================================

import streamlit as st
import pandas as pd
import requests
import json
import io
import re  # 💡 Added to resolve the NameError regex parsing crash
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
    # VIEWS/7_ATTENDANCE_LEDGER.PY: CSV EXPORT UTILITY SECTION
    # ============================================================================
    st.markdown("### 📥 Export Clean Analytical Records")
    
    # 🧼 Create a clean processing space copy of the target dataframe
    csv_export_df = render_df.copy()
    
    # Target all the day tracking grid column matrices (D01 to D31)
    active_d_cols = [col for col in csv_export_df.columns if col.startswith("D")]
    
    # 🔒 EXCEL DATE PROTECTION FIX: Prefix fractions with a single apostrophe string marker
    for d_col in active_d_cols:
        csv_export_df[d_col] = csv_export_df[d_col].apply(
            lambda x: f"'{str(x).strip()}" if pd.notna(x) and str(x).strip() != "" else ""
        )
        
    # Build clean system-friendly byte stream pools
    @st.cache_data(ttl=2)
    def convert_ledger_df_to_csv(dataframe):
        return dataframe.to_csv(index=False).encode('utf-8')
        
    clean_csv_bytes = convert_ledger_df_to_csv(csv_export_df)
    
    st.download_button(
        label="📥 Download Historical Matrix Ledger as Clean CSV",
        data=clean_csv_bytes,
        file_name=f"Attendance_Ledger_Export_{datetime.datetime.now().strftime('%Y-%m-%d')}.csv",
        mime="text/csv",
        type="secondary",
        key="attendance_ledger_csv_export_btn"
    )
# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY: PART 3 - FRAGMENT A1 (OVERRIDE FILTER ROW)
# ============================================================================
    st.markdown("### 📥 Export Clean Analytical Records")
    
    # 🧼 Create a sterile copy of the data frame to manipulate for the export layer
    csv_export_df = render_df.copy()
    
    # Identify all active daily calendar status tracking columns currently on screen
    active_d_cols = [col for col in csv_export_df.columns if col.startswith("D")]
    
    # 🔒 Force Excel/Sheets to read text literals: wrap cell targets inside ="TEXT" formulas
    for d_col in active_d_cols:
        csv_export_df[d_col] = csv_export_df[d_col].apply(
            lambda x: f'="{str(x).strip()}"' if pd.notna(x) and str(x).strip() != "" else ""
        )
        
    # Convert data frame to system friendly UTF-8 byte arrays
    @st.cache_data(ttl=2)
    def convert_ledger_df_to_csv(dataframe):
        return dataframe.to_csv(index=False).encode('utf-8')
        
    clean_csv_bytes = convert_ledger_df_to_csv(csv_export_df)
    
    st.download_button(
        label="📥 Download Historical Matrix Ledger as Clean CSV",
        data=clean_csv_bytes,
        file_name=f"Attendance_Ledger_Export_{datetime.datetime.now().strftime('%Y-%m-%d')}.csv",
        mime="text/csv",
        type="secondary",
        key="attendance_ledger_csv_export_btn"
    )

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

            # ⚙️ RECALCULATION ENGINE: Dynamic profile extraction tracking
            emp_id_clean = str(emp_data['EMP_ID']).strip().upper()
            meta_profile = emp_metadata_map.get(emp_id_clean, {})
            
            # Fetch Shift_Hours parameter dynamically from the metadata map
            configured_shift_hours = float(meta_profile.get("shift_hours", 12.00))
            
            # Determine the total number of calendar days selected in the slider range (e.g., 31)
            total_days_in_range = float((slip_end_day - slip_start_day) + 1)
            
            empty_cells_count = 0.0
            absent_cells_count = 0.0
            
            total_whole_hours = 0.0
            total_minutes = 0.0
            
            # Row parser loop over selected slider range
            for day in range(slip_start_day, slip_end_day + 1):
                day_mark = str(emp_data.get(f"D{day:02d}", "")).strip().upper()
                
                # 1️⃣ Check for True Empty Cells
                if day_mark == "" or day_mark == "NONE" or day_mark.isspace():
                    empty_cells_count += 1.0
                    continue
                
                # 2️⃣ Check for True Absent Cells
                if day_mark == "A":
                    absent_cells_count += 1.0
                    continue
                
                # 3️⃣ Accumulate Productive Hours (Only for actual worked days)
                if day_mark == "P":
                    total_whole_hours += configured_shift_hours
                elif "/" in day_mark:
                    try:
                        parts = day_mark.split("/")
                        total_whole_hours += float(parts[0])
                        total_minutes += float(parts[1])
                    except:
                        continue
                elif "P" in day_mark:
                    total_whole_hours += configured_shift_hours
                    num_digits = re.sub(r"[^0-9.]", "", day_mark)
                    if num_digits:
                        total_whole_hours += float(num_digits)
                elif day_mark.isdigit() or re.match(r"^\d+?\.\d+?\$", day_mark):
                    total_whole_hours += float(day_mark)
            
            # 🛡️ Dynamic Math: (Total calendar days) - (Empty cells + Absent cells)
            days_count_override = total_days_in_range - (empty_cells_count + absent_cells_count)
            
            # Late Fusion Step: Pool accumulated minutes cleanly to eliminate rounding drift
            converted_decimal_hours = total_minutes / 60.0
            hours_worked_override = round(total_whole_hours + converted_decimal_hours, 2)
            
            emp_data['Total_Days'] = days_count_override
            emp_data['Total_Hours'] = hours_worked_override
            
            # Run the dynamic payout formula using the dynamic shift baseline
            if str(emp_data['EMP_Status']).upper() == "ACTIVE":
                standard_monthly_days = 26.0
                hourly_rate_recalculated = (float(emp_data['Base_Monthly_Comp']) / standard_monthly_days) / configured_shift_hours
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
                # 💡 Formatting changed to :.0f to completely hide decimal zero placeholders
                st.markdown(f"**Truncated Range Worked:** {emp_data['Total_Days']:.0f} Days (Days {slip_start_day} to {slip_end_day})")
            with slip_card_col2:
                st.markdown(f"**Base Configured Salary:** ₹ {emp_data['Base_Monthly_Comp']:,.2f}")
                st.markdown(f"**Calculated Hourly Rate:** ₹ {emp_data['Rate_Per_Hour']:,.2f} / hr (Based on {configured_shift_hours:.0f}-hr shift)")
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
                doc.build([t1]) # Test layout structure alignment
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
