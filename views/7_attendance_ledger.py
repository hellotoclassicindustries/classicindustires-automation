# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY
# PAYROLL & ATTENDANCE WORKFLOW
# ============================================================================

import streamlit as st
import pandas as pd
import requests
import io
import re
import datetime
import calendar
import math

from dateutil.relativedelta import relativedelta

from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.styles import (
    getSampleStyleSheet,
    ParagraphStyle,
)
from reportlab.lib import colors

from xml.sax.saxutils import escape


# ============================================================================
# SUPABASE CONFIGURATION
# ============================================================================

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


# ============================================================================
# GLOBAL HELPERS
# ============================================================================

def safe_float(value):
    """Safely convert a value to float."""
    if value is None:
        return 0.00

    value_text = str(value).strip()

    if value_text == "" or value_text.lower() == "none":
        return 0.00

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.00


@st.cache_data(ttl=2)
def fetch_vw_attendance_ledger():
    """Fetch attendance ledger records from the Supabase view."""

    endpoint = (
        f"{SUPABASE_URL.strip('/')}"
        "/rest/v1/vw_attendance_ledger"
        "?order=month_year.desc,employee_id.asc"
    )

    try:
        response = requests.get(
            endpoint,
            headers=HEADERS,
            timeout=30,
        )

        if response.status_code == 200:
            return response.json()

        st.warning(
            f"Attendance ledger request failed with HTTP "
            f"status {response.status_code}."
        )
        return []

    except requests.RequestException as error:
        st.warning(f"Unable to connect to the attendance database: {error}")
        return []


def update_db_payment_status(employee_id, month_year, new_status):
    """Update payment status in raw_attendance_feed."""

    endpoint = (
        f"{SUPABASE_URL.strip('/')}"
        "/rest/v1/raw_attendance_feed"
        f"?employee_id=eq.{employee_id}"
        f"&month_year=eq.{month_year}"
    )

    payload = {
        "payment_status": new_status
    }

    try:
        response = requests.patch(
            endpoint,
            headers=HEADERS,
            json=payload,
            timeout=30,
        )

        return response.status_code in [200, 201, 204]

    except requests.RequestException:
        return False


def parse_row_date(month_year_value):
    """
    Convert values such as:
    September-2026
    September/2026
    09-2026
    into datetime.date(year, month, 1).
    """

    if month_year_value is None:
        return None

    month_year_text = str(month_year_value).strip()

    if not month_year_text or month_year_text.upper() == "N/A":
        return None

    normalized = month_year_text.replace("/", "-")

    year_match = re.search(r"\b(20\d{2})\b", normalized)

    if year_match:
        year = int(year_match.group(1))
    else:
        year = datetime.date.today().year

    normalized_upper = normalized.upper()

    for month_number in range(1, 13):
        full_month_name = calendar.month_name[month_number].upper()
        short_month_name = calendar.month_abbr[month_number].upper()

        if (
            full_month_name in normalized_upper
            or short_month_name in normalized_upper
        ):
            return datetime.date(year, month_number, 1)

    numeric_values = re.findall(r"\b(\d{1,2})\b", normalized)

    for numeric_value in numeric_values:
        month_number = int(numeric_value)

        if 1 <= month_number <= 12:
            return datetime.date(year, month_number, 1)

    return None


def get_days_in_month(month_year_value):
    """Return the actual number of days in the specified month."""

    row_date = parse_row_date(month_year_value)

    if row_date:
        return calendar.monthrange(
            row_date.year,
            row_date.month,
        )[1]

    return 31


def generate_ledger_matrix_pdf(dataframe):
    """
    Generate a landscape PDF from the selected rows and columns.
    """

    if dataframe is None or dataframe.empty or len(dataframe.columns) == 0:
        return b""

    pdf_buffer = io.BytesIO()

    document = SimpleDocTemplate(
        pdf_buffer,
        pagesize=landscape(letter),
        rightMargin=20,
        leftMargin=20,
        topMargin=30,
        bottomMargin=30,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "LedgerTitleStyle",
        parent=styles["Heading1"],
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#1A365D"),
        alignment=0,
    )

    header_style = ParagraphStyle(
        "LedgerHeaderStyle",
        parent=styles["Normal"],
        fontSize=6,
        leading=8,
        textColor=colors.white,
        fontName="Helvetica-Bold",
        alignment=1,
    )

    data_style = ParagraphStyle(
        "LedgerDataStyle",
        parent=styles["Normal"],
        fontSize=5,
        leading=7,
        textColor=colors.black,
        alignment=1,
    )

    story = []

    story.append(
        Paragraph(
            "Payroll & Attendance Ledger",
            title_style,
        )
    )

    story.append(Spacer(1, 10))

    headers = list(dataframe.columns)

    table_data = [
        [
            Paragraph(
                escape(str(column_name)),
                header_style,
            )
            for column_name in headers
        ]
    ]

    for _, row in dataframe.iterrows():
        row_cells = []

        for column_name in headers:
            value = row[column_name]

            if pd.isna(value):
                value = ""

            if isinstance(value, float):
                value_text = f"{value:.2f}"
            else:
                value_text = str(value)

            row_cells.append(
                Paragraph(
                    escape(value_text),
                    data_style,
                )
            )

        table_data.append(row_cells)

    available_width = 752
    column_count = len(headers)
    column_width = max(20, available_width / column_count)

    ledger_table = Table(
        table_data,
        colWidths=[column_width] * column_count,
        repeatRows=1,
    )

    ledger_table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#2B6CB0"),
                ),
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.white,
                ),
                (
                    "ALIGN",
                    (0, 0),
                    (-1, -1),
                    "CENTER",
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.3,
                    colors.HexColor("#CBD5E0"),
                ),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [
                        colors.white,
                        colors.HexColor("#F7FAFC"),
                    ],
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    4,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    4,
                ),
            ]
        )
    )

    story.append(ledger_table)

    document.build(story)

    pdf_buffer.seek(0)

    return pdf_buffer.getvalue()


# ============================================================================
# LOAD ATTENDANCE DATA
# ============================================================================

view_records_data = fetch_vw_attendance_ledger()

if not view_records_data:
    st.info(
        "📋 No integrated database rows were found in "
        "vw_attendance_ledger."
    )
    st.stop()


# ============================================================================
# PAYROLL & ATTENDANCE FILTERS
# ============================================================================

today = datetime.date.today()
previous_month_date = today - relativedelta(months=1)

default_start = previous_month_date.replace(day=1)

default_end = previous_month_date.replace(
    day=calendar.monthrange(
        previous_month_date.year,
        previous_month_date.month,
    )[1]
)

st.header("📋 Payroll & Attendance Workflow")

chosen_dates = st.date_input(
    "Select Payout Month:",
    value=(default_start, default_end),
    key="unique_attendance_calendar_range_picker",
)

if isinstance(chosen_dates, tuple) and len(chosen_dates) == 2:
    start_cal, end_cal = chosen_dates
else:
    start_cal = default_start
    end_cal = default_end


filter_col1, filter_col2, filter_col3 = st.columns(3)

with filter_col1:
    search_mat_id = st.text_input(
        "Filter by Employee ID:",
        "",
        key="mat_id_input",
    ).strip()

with filter_col2:
    search_mat_name = st.text_input(
        "Filter by Employee Name:",
        "",
        key="mat_name_input",
    ).strip()

with filter_col3:
    search_mat_status = st.selectbox(
        "Filter by Employee Status:",
        options=[
            "All Statuses",
            "Active Only",
            "In-Active Only",
        ],
        key="mat_status_input",
    )


# ============================================================================
# PAYROLL CALCULATION ENGINE
# ============================================================================

processed_rows = []

for item in view_records_data:
    month_year = item.get("month_year") or "N/A"
    row_date = parse_row_date(month_year)

    if row_date:
        if not (start_cal <= row_date <= end_cal):
            continue

    total_hours_worked = safe_float(
        item.get("total_hours")
    )

    total_days_worked = safe_float(
        item.get("total_days")
    )

    base_monthly_comp = safe_float(
        item.get("base_monthly_comp")
    )

    configured_shift_hours = safe_float(
        item.get("shift_hours")
    )

    if configured_shift_hours <= 0:
        configured_shift_hours = 8.00

    current_status = (
        item.get("employee_status")
        or "Active"
    )

    days_list = item.get("attendance_days") or []

    total_minutes_worked = round(
        total_hours_worked * 60.0,
        2,
    )

    month_days = get_days_in_month(month_year)

    if configured_shift_hours > 0:
        actual_days_worked = round(
            total_hours_worked / configured_shift_hours,
            2,
        )
    else:
        actual_days_worked = 0.00

    if (
        str(current_status).upper() == "ACTIVE"
        and month_days > 0
        and configured_shift_hours > 0
    ):
        daily_allocation_rate = (
            base_monthly_comp / float(month_days)
        )

        # Round hourly rate upward to the nearest penny.
        per_hour_rate = (
            math.ceil(
                (
                    daily_allocation_rate
                    / configured_shift_hours
                ) * 100
            ) / 100.0
        )

        # Round per-minute rate upward to four decimal places.
        per_minute_rate = (
            math.ceil(
                (per_hour_rate / 60.0) * 10000
            ) / 10000.0
        )

        calculated_gross_payout = round(
            total_hours_worked * per_hour_rate,
            2,
        )

    else:
        per_hour_rate = 0.00
        per_minute_rate = 0.00
        calculated_gross_payout = 0.00

    row_dict = {
        "Month_Year": month_year,
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
        "DB_Show_Flag": (
            item.get("show")
            if item.get("show") is not None
            else True
        ),
    }

    for day_number in range(1, 32):
        day_column = f"D{day_number:02d}"

        if days_list and day_number - 1 < len(days_list):
            row_dict[day_column] = days_list[day_number - 1]
        else:
            row_dict[day_column] = ""

    processed_rows.append(row_dict)


df = pd.DataFrame(processed_rows)


# ============================================================================
# ATTENDANCE LEDGER TABLE
# ============================================================================

if df.empty:
    st.warning(
        "⚠️ No attendance records match the selected date range."
    )
    st.stop()


filtered_df = df[df["DB_Show_Flag"] == True].copy()

if search_mat_id:
    filtered_df = filtered_df[
        filtered_df["EMP_ID"]
        .astype(str)
        .str.contains(
            search_mat_id,
            case=False,
            na=False,
        )
    ]

if search_mat_name:
    filtered_df = filtered_df[
        filtered_df["EMP_Name"]
        .astype(str)
        .str.contains(
            search_mat_name,
            case=False,
            na=False,
        )
    ]

if search_mat_status == "Active Only":
    filtered_df = filtered_df[
        filtered_df["EMP_Status"]
        .astype(str)
        .str.upper()
        == "ACTIVE"
    ]

elif search_mat_status == "In-Active Only":
    filtered_df = filtered_df[
        filtered_df["EMP_Status"]
        .astype(str)
        .str.upper()
        == "IN-ACTIVE"
    ]


if filtered_df.empty:
    st.warning(
        "⚠️ No ledger records match the active filters."
    )
    st.stop()


all_day_columns = [
    f"D{day_number:02d}"
    for day_number in range(1, 32)
]

grid_columns_order = (
    [
        "Month_Year",
        "EMP_ID",
        "EMP_Name",
    ]
    + all_day_columns
    + [
        "Over_Time",
        "Less_Time",
        "Total_Hours",
        "Total_Minutes",
        "Total_Days",
        "Actual_Days_Worked",
        "Base_Monthly_Comp",
        "Rate_Per_Hour",
        "Rate_Per_Minute",
        "Gross_Payout",
        "Payment_Status",
        "Start_Date",
        "Last_Date",
        "EMP_Status",
    ]
)

validated_columns = [
    column_name
    for column_name in grid_columns_order
    if column_name in filtered_df.columns
]

render_df = filtered_df[validated_columns].copy()


# ============================================================================
# TABLE COLUMN CONFIGURATION
# ============================================================================

column_config = {
    "Month_Year": st.column_config.TextColumn(
        "Month/Year",
        width="small",
        disabled=True,
    ),
    "EMP_ID": st.column_config.TextColumn(
        "Employee ID",
        width="small",
        disabled=True,
    ),
    "EMP_Name": st.column_config.TextColumn(
        "Employee Name",
        width="medium",
        disabled=True,
    ),
    "Over_Time": st.column_config.NumberColumn(
        "Extra Hrs",
        format="%.2f",
        width="small",
        disabled=True,
    ),
    "Less_Time": st.column_config.NumberColumn(
        "Short Hrs",
        format="%.2f",
        width="small",
        disabled=True,
    ),
    "Total_Hours": st.column_config.NumberColumn(
        "Total Hrs",
        format="%.2f",
        width="small",
        disabled=True,
    ),
    "Total_Minutes": st.column_config.NumberColumn(
        "Total Minutes",
        format="%.2f",
        width="small",
        disabled=True,
    ),
    "Total_Days": st.column_config.NumberColumn(
        "Raw Days Present",
        format="%.0f",
        width="small",
        disabled=True,
    ),
    "Actual_Days_Worked": st.column_config.NumberColumn(
        "Actual Days Worked",
        format="%.2f",
        width="medium",
        disabled=True,
    ),
    "Base_Monthly_Comp": st.column_config.NumberColumn(
        "Base Monthly Comp",
        format="₹%.2f",
        width="small",
        disabled=True,
    ),
    "Rate_Per_Hour": st.column_config.NumberColumn(
        "Hourly Rate",
        format="₹%.2f",
        width="small",
        disabled=True,
    ),
    "Rate_Per_Minute": st.column_config.NumberColumn(
        "Per Minute Rate",
        format="₹%.4f",
        width="small",
        disabled=True,
    ),
    "Gross_Payout": st.column_config.NumberColumn(
        "Gross Payout",
        format="₹%.2f",
        width="medium",
        disabled=True,
    ),
    "Payment_Status": st.column_config.SelectboxColumn(
        "Payment Status",
        width="medium",
        options=["Pending", "Done"],
        required=True,
    ),
    "Start_Date": st.column_config.TextColumn(
        "Start Date",
        width="small",
        disabled=True,
    ),
    "Last_Date": st.column_config.TextColumn(
        "Last Working Date",
        width="small",
        disabled=True,
    ),
    "EMP_Status": st.column_config.TextColumn(
        "Employee Status",
        width="small",
        disabled=True,
    ),
}

for day_column in all_day_columns:
    if day_column in validated_columns:
        column_config[day_column] = st.column_config.TextColumn(
            day_column.replace("D", ""),
            width=45,
            disabled=True,
        )


# ============================================================================
# DATA EDITOR
# ============================================================================

edited_df = st.data_editor(
    render_df,
    hide_index=True,
    width="stretch",
    column_config=column_config,
    key="attendance_ledger_data_editor",
)


# ============================================================================
# PAYMENT STATUS UPDATE
# ============================================================================

editor_state = st.session_state.get(
    "attendance_ledger_data_editor",
    {},
)

edited_rows = editor_state.get(
    "edited_rows",
    {},
)

if edited_rows:
    for row_index_text, altered_properties in edited_rows.items():
        row_index = int(row_index_text)

        if "Payment_Status" not in altered_properties:
            continue

        if row_index >= len(render_df):
            continue

        target_employee = render_df.iloc[row_index]["EMP_ID"]
        target_month = render_df.iloc[row_index]["Month_Year"]
        updated_status = altered_properties["Payment_Status"]

        with st.spinner(
            f"Updating payment status for {target_employee}..."
        ):
            update_successful = update_db_payment_status(
                target_employee,
                target_month,
                updated_status,
            )

        if update_successful:
            st.success(
                f"✓ Payment status updated to '{updated_status}' "
                f"for Employee ID: {target_employee}"
            )

            st.cache_data.clear()
            st.rerun()
        else:
            st.error(
                f"Unable to update payment status for "
                f"Employee ID: {target_employee}."
            )


# ============================================================================
# PAYROLL & ATTENDANCE WORKFLOW EXPORTS
# ============================================================================

st.markdown("---")
st.header("📤 Payroll & Attendance Workflow Exports")

export_df = edited_df.copy()

export_col1, export_col2 = st.columns(2)


# ============================================================================
# CSV EXPORT
# ============================================================================

with export_col1:
    st.subheader("📊 CSV Export")

    csv_df = export_df.copy()

    # Preserve attendance values such as 11/30 when opened in Excel.
    for column_name in csv_df.columns:
        if (
            column_name.startswith("D")
            and column_name[1:].isdigit()
        ):
            csv_df[column_name] = csv_df[column_name].apply(
                lambda value: (
                    f"\t{value}"
                    if isinstance(value, str)
                    and "/" in value
                    else value
                )
            )

    csv_buffer = io.StringIO()
    csv_df.to_csv(csv_buffer, index=False)

    st.download_button(
        label="⬇️ Download Ledger as CSV (Preserve Formats)",
        data=csv_buffer.getvalue(),
        file_name=(
            "Historical_Attendance_Ledger_"
            f"{datetime.date.today()}.csv"
        ),
        mime="text/csv",
        key="ledger_csv_download_btn",
    )


# ============================================================================
# PDF EXPORT
# ============================================================================

with export_col2:
    st.subheader("📄 PDF Export")

    available_pdf_columns = list(export_df.columns)

    default_pdf_columns = [
        column_name
        for column_name in [
            "Month_Year",
            "EMP_ID",
            "EMP_Name",
            "Total_Hours",
            "Actual_Days_Worked",
            "Base_Monthly_Comp",
            "Rate_Per_Hour",
            "Rate_Per_Minute",
            "Gross_Payout",
            "Payment_Status",
            "EMP_Status",
        ]
        if column_name in available_pdf_columns
    ]

    selected_pdf_columns = st.multiselect(
        "Select columns to include in the PDF:",
        options=available_pdf_columns,
        default=default_pdf_columns,
        key="ledger_pdf_columns",
    )

    row_options = []
    row_lookup = {}

    for position, (_, row) in enumerate(export_df.iterrows()):
        employee_id = row.get("EMP_ID", "N/A")
        employee_name = row.get("EMP_Name", "Unnamed")
        month_year = row.get("Month_Year", "N/A")

        label = (
            f"{position + 1}. "
            f"{employee_id} - "
            f"{employee_name} - "
            f"{month_year}"
        )

        row_options.append(label)
        row_lookup[label] = position

    selected_pdf_row_labels = st.multiselect(
        "Select rows to include in the PDF:",
        options=row_options,
        default=[],
        help=(
            "Leave this empty to include all filtered ledger rows."
        ),
        key="ledger_pdf_rows",
    )

    if selected_pdf_row_labels:
        selected_row_positions = [
            row_lookup[label]
            for label in selected_pdf_row_labels
        ]

        pdf_target_df = export_df.iloc[
            selected_row_positions
        ].copy()
    else:
        pdf_target_df = export_df.copy()

    if selected_pdf_columns:
        pdf_target_df = pdf_target_df[
            selected_pdf_columns
        ].copy()
    else:
        pdf_target_df = pd.DataFrame()

    if not selected_pdf_columns:
        st.warning(
            "Select at least one column for the PDF."
        )
        pdf_data = b""

    elif pdf_target_df.empty:
        st.warning(
            "No rows are available for the selected PDF."
        )
        pdf_data = b""

    else:
        pdf_data = generate_ledger_matrix_pdf(
            pdf_target_df
        )

    st.download_button(
        label="⬇️ Download Ledger as PDF (Landscape)",
        data=pdf_data,
        file_name=(
            "Historical_Attendance_Ledger_"
            f"{datetime.date.today()}.pdf"
        ),
        mime="application/pdf",
        key="ledger_pdf_download_btn",
        disabled=not bool(pdf_data),
    )


# ============================================================================
# FORMULAS REFERENCE
# ============================================================================

st.markdown("---")
st.header("🧮 Calculation Formulas")

formula_col1, formula_col2, formula_col3 = st.columns(3)


with formula_col1:
    st.markdown("**1. Per Minute Rate Engine**")

    st.latex(
        r"\mathrm{Rate\ Per\ Min} = "
        r"\frac{"
        r"\mathrm{Base\ Monthly\ Comp} / \mathrm{Days\ In\ Month}"
        r"}"
        r"{\mathrm{Shift\ Hours} \times 60}"
    )

    with st.expander(
        "🔍 View Example Verification Details"
    ):
        st.markdown("""
        ##### 📐 In-Memory Precision: Time String Expansion

        Values such as **`11/30`** are interpreted as
        11 hours and 30 minutes.

        * **Extraction Check:** `11/30` becomes 11 hours and 30 minutes.
        * **Fractional Math Calculation:**
        """)

        st.latex(
            r"\frac{30}{60} = 0.5\ \mathrm{Hours}"
        )

        st.markdown(
            "* **Decimal Aggregation Payout:**"
        )

        st.latex(
            r"11 + 0.5 = 11.5\ \mathrm{Hours}"
        )


with formula_col2:
    st.markdown("**2. Proportional Days Math**")

    st.latex(
        r"\mathrm{Actual\ Days\ Worked} = "
        r"\frac{"
        r"\mathrm{Total\ Hours\ Worked}"
        r"}"
        r"{\mathrm{Shift\ Hours}}"
    )

    with st.expander(
        "🔍 View Consistency Proof"
    ):
        st.markdown("""
        ##### 📈 Mathematical Consistency Proof

        Two separate `11/30` entries produce
        23 total hours.
        """)

        st.latex(
            r"11.5 + 11.5 = 23.0\ \mathrm{Hours}"
        )

        st.markdown(
            "Against an 8-hour shift, working `11/30` "
            "produces:"
        )

        st.latex(
            r"11.5 - 8.0 = 3.5\ \mathrm{Overtime\ Hours}"
        )

        st.markdown(
            "Two such days produce exactly "
            "**7.0 hours of overtime**."
        )


with formula_col3:
    st.markdown("**3. Consolidated Gross Payout**")

    st.latex(
        r"\mathrm{Gross\ Payout} = "
        r"\mathrm{Total\ Hours\ Worked} \times "
        r"\mathrm{Rate\ Per\ Hour}"
    )

    with st.expander(
        "🔍 View Payout Math Example"
    ):
        st.markdown("""
        ##### 💰 Example Calculation Breakdown

        * **Hourly Sourcing:** Uses the derived
          `Rate_Per_Hour` multiplied directly by logged hours.
        * **Precision Enforced:** Values are rounded according
          to the configured payroll precision rules.
        """)
