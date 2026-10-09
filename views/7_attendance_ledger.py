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
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from xml.sax.saxutils import escape


# ============================================================================
# CONFIGURATION
# ============================================================================

try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

except Exception:
    st.error(
        "Missing SUPABASE_URL or SUPABASE_KEY in Streamlit secrets."
    )
    st.stop()


SUPABASE_URL = SUPABASE_URL.rstrip("/")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

APP_USER = (
    st.session_state.get("user_name")
    or st.session_state.get("username")
    or "Streamlit User"
)

SOURCE_IDENTIFIER = "STREAMLIT_LIVE_UI"

ADJUSTMENT_RATE_UNITS = [
    "Per Hour",
    "Per Day",
    "Per Shift",
    "Per Task",
    "Per Load",
    "Fixed",
]

ADJUSTMENT_STATUSES = [
    "Pending",
    "Approved",
    "Rejected",
]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def safe_float(value):
    if value is None:
        return 0.00

    text = str(value).strip()

    if not text:
        return 0.00

    if text.lower() in {"none", "nan", "null", "n/a"}:
        return 0.00

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.00


def money(value):
    return round(safe_float(value), 2)


def normalise_employee_id(value):
    if value is None:
        return ""

    text = str(value).strip()

    if text.lower() in {"none", "nan", "null", "n/a"}:
        return ""

    if text.endswith(".0"):
        text = text[:-2]

    return text


def parse_bigint_employee_id(value):
    employee_id = normalise_employee_id(value)

    if not employee_id:
        return None

    try:
        return int(employee_id)
    except (TypeError, ValueError):
        return None


def parse_month(value):
    if value is None:
        return None

    text = str(value).strip()

    if not text or text.upper() == "N/A":
        return None

    text = text.replace("/", "-")
    text_upper = text.upper()

    year_match = re.search(r"\b(20\d{2})\b", text)

    if year_match:
        year = int(year_match.group(1))
    else:
        year = datetime.date.today().year

    for month_number in range(1, 13):
        full_month = calendar.month_name[month_number].upper()
        short_month = calendar.month_abbr[month_number].upper()

        if full_month in text_upper or short_month in text_upper:
            return datetime.date(year, month_number, 1)

    year_month_match = re.search(
        r"\b(20\d{2})-(0[1-9]|1[0-2])\b",
        text,
    )

    if year_month_match:
        return datetime.date(
            int(year_month_match.group(1)),
            int(year_month_match.group(2)),
            1,
        )

    numeric_values = re.findall(r"\b(\d{1,2})\b", text)

    for numeric_value in numeric_values:
        month_number = int(numeric_value)

        if 1 <= month_number <= 12:
            return datetime.date(year, month_number, 1)

    return None


def canonical_month(value):
    parsed = parse_month(value)

    if parsed is None:
        return None

    return parsed.strftime("%Y-%m")


def display_month(value):
    parsed = parse_month(value)

    if parsed is None:
        return str(value or "N/A")

    return parsed.strftime("%B-%Y")


def days_in_month(value):
    parsed = parse_month(value)

    if parsed is None:
        return 31

    return calendar.monthrange(
        parsed.year,
        parsed.month,
    )[1]


def calculate_extra_work_payment(
    quantity,
    rate,
    rate_unit,
):
    quantity = max(0.00, safe_float(quantity))
    rate = max(0.00, safe_float(rate))

    if rate_unit == "Fixed":
        return money(rate)

    return money(quantity * rate)


def calculate_final_net_payable(
    regular_gross,
    extra_earning,
    advance_given,
):
    return money(
        safe_float(regular_gross)
        + safe_float(extra_earning)
        - safe_float(advance_given)
    )


def get_first_value(record, *field_names, default=None):
    for field_name in field_names:
        if (
            field_name in record
            and record[field_name] is not None
        ):
            return record[field_name]

    return default


def build_adjustment_lookup(records):
    lookup = {}

    for record in records or []:
        employee_id = normalise_employee_id(
            record.get("employee_id")
        )

        month_year = canonical_month(
            record.get("month_year")
        )

        if employee_id and month_year:
            lookup[(employee_id, month_year)] = record

    return lookup


# ============================================================================
# SUPABASE FUNCTIONS
# ============================================================================

@st.cache_data(ttl=10)
def fetch_attendance_records():
    endpoint = (
        f"{SUPABASE_URL}/rest/v1/vw_attendance_ledger"
        "?select=*"
        "&order=month_year.desc,employee_id.asc"
    )

    try:
        response = requests.get(
            endpoint,
            headers=HEADERS,
            timeout=30,
        )

        if response.status_code == 200:
            return response.json()

        st.error(
            "Unable to load attendance ledger. "
            f"HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )
        return []

    except requests.RequestException as error:
        st.error(f"Attendance request failed: {error}")
        return []


@st.cache_data(ttl=10)
def fetch_payroll_adjustments():
    endpoint = (
        f"{SUPABASE_URL}/rest/v1/payroll_adjustments_live"
        "?select=*"
        "&order=month_year.desc,employee_id.asc"
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
            "Unable to load payroll adjustments. "
            f"HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )
        return []

    except requests.RequestException as error:
        st.warning(
            f"Payroll adjustment request failed: {error}"
        )
        return []


def save_payroll_adjustment(payload):
    endpoint = (
        f"{SUPABASE_URL}/rest/v1/payroll_adjustments_live"
        "?on_conflict=employee_id,month_year"
    )

    request_headers = {
        **HEADERS,
        "Prefer": (
            "resolution=merge-duplicates,"
            "return=representation"
        ),
    }

    try:
        response = requests.post(
            endpoint,
            headers=request_headers,
            json=payload,
            timeout=30,
        )

        if response.status_code in (200, 201):
            try:
                return True, response.json()
            except ValueError:
                return True, []

        return False, (
            f"HTTP {response.status_code}: "
            f"{response.text[:1000]}"
        )

    except requests.RequestException as error:
        return False, str(error)


def update_payment_status(
    employee_id,
    month_year,
    status,
):
    numeric_employee_id = parse_bigint_employee_id(
        employee_id
    )

    canonical_month_year = canonical_month(month_year)

    if numeric_employee_id is None:
        return False, "Invalid employee ID."

    if not canonical_month_year:
        return False, "Invalid payroll month."

    endpoint = (
        f"{SUPABASE_URL}/rest/v1/raw_attendance_feed"
        f"?employee_id=eq.{numeric_employee_id}"
        f"&month_year=eq.{canonical_month_year}"
    )

    payload = {
        "payment_status": status,
    }

    try:
        response = requests.patch(
            endpoint,
            headers=HEADERS,
            json=payload,
            timeout=30,
        )

        if response.status_code in (200, 201, 204):
            return True, ""

        return False, (
            f"HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )

    except requests.RequestException as error:
        return False, str(error)


# ============================================================================
# PDF FUNCTION
# ============================================================================

def generate_pdf(dataframe):
    if dataframe is None or dataframe.empty:
        return b""

    buffer = io.BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=20,
        rightMargin=20,
        topMargin=25,
        bottomMargin=25,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#1A365D"),
    )

    header_style = ParagraphStyle(
        "Header",
        parent=styles["Normal"],
        fontSize=6,
        leading=7,
        textColor=colors.white,
        fontName="Helvetica-Bold",
        alignment=1,
    )

    cell_style = ParagraphStyle(
        "Cell",
        parent=styles["Normal"],
        fontSize=5,
        leading=6,
        alignment=1,
    )

    story = [
        Paragraph(
            "Attendance and Payroll Ledger",
            title_style,
        ),
        Spacer(1, 8),
    ]

    columns = list(dataframe.columns)

    table_data = [
        [
            Paragraph(
                escape(str(column)),
                header_style,
            )
            for column in columns
        ]
    ]

    for _, row in dataframe.iterrows():
        table_row = []

        for column in columns:
            value = row[column]

            if pd.isna(value):
                value = ""

            if isinstance(value, float):
                value = f"{value:.2f}"

            table_row.append(
                Paragraph(
                    escape(str(value)),
                    cell_style,
                )
            )

        table_data.append(table_row)

    column_count = max(len(columns), 1)
    column_width = 750 / column_count

    table = Table(
        table_data,
        colWidths=[column_width] * column_count,
        repeatRows=1,
    )

    table.setStyle(
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
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.3,
                    colors.HexColor("#CBD5E0"),
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

    story.append(table)
    document.build(story)

    buffer.seek(0)
    return buffer.getvalue()
    # ============================================================================
# LOAD DATA
# ============================================================================

attendance_records = fetch_attendance_records()
adjustment_records = fetch_payroll_adjustments()

adjustment_lookup = build_adjustment_lookup(
    adjustment_records
)

if not attendance_records:
    st.info(
        "No attendance records were found in "
        "vw_attendance_ledger."
    )
    st.stop()


# ============================================================================
# PAGE HEADER
# ============================================================================

st.title("Attendance Ledger")

st.caption(
    "Attendance appears first. Downloads appear below the ledger. "
    "Payroll Adjustment is available at the bottom."
)


# ============================================================================
# FILTERS
# ============================================================================

today = datetime.date.today()
previous_month = today - relativedelta(months=1)

default_start = previous_month.replace(day=1)

default_end = previous_month.replace(
    day=calendar.monthrange(
        previous_month.year,
        previous_month.month,
    )[1]
)

date_range = st.date_input(
    "Select payout month:",
    value=(default_start, default_end),
    key="attendance_date_range",
)

if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date = default_start
    end_date = default_end


filter_col1, filter_col2, filter_col3 = st.columns(3)

with filter_col1:
    employee_id_filter = st.text_input(
        "Filter by Employee ID",
        key="employee_id_filter",
    ).strip()

with filter_col2:
    employee_name_filter = st.text_input(
        "Filter by Employee Name",
        key="employee_name_filter",
    ).strip()

with filter_col3:
    status_filter = st.selectbox(
        "Filter by Employee Status",
        options=[
            "All Statuses",
            "Active Only",
            "In-Active Only",
        ],
        key="employee_status_filter",
    )


# ============================================================================
# BUILD DISPLAY DATA
# ============================================================================

processed_rows = []

for item in attendance_records:
    original_month = get_first_value(
        item,
        "month_year",
        "Month_Year",
        default="N/A",
    )

    parsed_month = parse_month(original_month)

    if parsed_month is not None:
        if parsed_month < start_date or parsed_month > end_date:
            continue

    database_month = canonical_month(original_month)

    employee_id = normalise_employee_id(
        get_first_value(
            item,
            "employee_id",
            "EMP_ID",
            default="",
        )
    )

    employee_name = get_first_value(
        item,
        "employee_name",
        "emp_name",
        "EMP_Name",
        default="Unnamed",
    )

    employee_status = get_first_value(
        item,
        "employee_status",
        "emp_status",
        "EMP_Status",
        default="Active",
    )

    total_hours = safe_float(
        get_first_value(
            item,
            "total_hours",
            "Total_Hours",
            default=0,
        )
    )

    total_days = safe_float(
        get_first_value(
            item,
            "total_days",
            "Total_Days",
            default=0,
        )
    )

    base_monthly_comp = safe_float(
        get_first_value(
            item,
            "base_monthly_comp",
            "base_monthly_salary",
            "Base_Monthly_Comp",
            default=0,
        )
    )

    shift_hours = safe_float(
        get_first_value(
            item,
            "shift_hours",
            "Shift_Hours",
            default=8,
        )
    )

    if shift_hours <= 0:
        shift_hours = 8.00

    existing_gross_payout = get_first_value(
        item,
        "gross_payout",
        "Gross_Payout",
        default=None,
    )

    if existing_gross_payout is not None:
        gross_payout = money(
            existing_gross_payout
        )

        if total_hours > 0:
            hourly_rate = money(
                gross_payout / total_hours
            )
        else:
            hourly_rate = 0.00

    else:
        month_day_count = days_in_month(
            original_month
        )

        if (
            str(employee_status).upper() == "ACTIVE"
            and month_day_count > 0
            and shift_hours > 0
        ):
            daily_rate = (
                base_monthly_comp
                / month_day_count
            )

            hourly_rate = math.ceil(
                (daily_rate / shift_hours) * 100
            ) / 100.00

            gross_payout = money(
                total_hours * hourly_rate
            )

        else:
            hourly_rate = 0.00
            gross_payout = 0.00

    total_minutes = round(
        total_hours * 60,
        2,
    )

    actual_days_worked = round(
        total_hours / shift_hours,
        2,
    )

    adjustment = adjustment_lookup.get(
        (
            employee_id,
            database_month,
        ),
        {},
    )

    extra_work_quantity = safe_float(
        adjustment.get(
            "extra_work_quantity"
        )
    )

    extra_work_rate = safe_float(
        adjustment.get(
            "extra_work_rate"
        )
    )

    extra_earning = safe_float(
        adjustment.get(
            "extra_work_payment"
        )
    )

    advance_given = safe_float(
        adjustment.get(
            "advance_given"
        )
    )

    final_net_payable = calculate_final_net_payable(
        gross_payout,
        extra_earning,
        advance_given,
    )

    row = {
        "Month_Year": original_month,
        "DB_Month_Year": database_month,
        "EMP_ID": employee_id or "N/A",
        "EMP_Name": employee_name,

        "Total_Hours": total_hours,
        "Total_Minutes": total_minutes,
        "Total_Days": total_days,
        "Actual_Days_Worked": actual_days_worked,

        "Base_Monthly_Comp": base_monthly_comp,
        "Rate_Per_Hour": hourly_rate,
        "Gross_Payout": gross_payout,

        "Extra_Work_Type": (
            adjustment.get(
                "extra_work_type"
            )
            or ""
        ),

        "Extra_Work_Quantity": (
            extra_work_quantity
        ),

        "Extra_Work_Rate": (
            extra_work_rate
        ),

        "Rate_Unit": (
            adjustment.get(
                "rate_unit"
            )
            or "Fixed"
        ),

        "Extra_Earning": extra_earning,
        "Advance_Given": advance_given,
        "Final_Net_Payable": final_net_payable,

        "Adjustment_Status": (
            adjustment.get(
                "adjustment_status"
            )
            or "No UI Adjustment"
        ),

        "Adjustment_Source": (
            adjustment.get(
                "source_identifier"
            )
            or "NO_UI_ADJUSTMENT"
        ),

        "Adjustment_Notes": (
            adjustment.get(
                "adjustment_notes"
            )
            or ""
        ),

        "Payment_Status": get_first_value(
            item,
            "payment_status",
            "Payment_Status",
            default="Pending",
        ),

        "Start_Date": get_first_value(
            item,
            "start_date",
            "Start_Date",
            default="N/A",
        ),

        "Last_Date": get_first_value(
            item,
            "last_date",
            "last_working_date",
            "Last_Date",
            default="N/A",
        ),

        "EMP_Status": employee_status,

        "DB_Show_Flag": get_first_value(
            item,
            "show",
            "DB_Show_Flag",
            default=True,
        ),
    }

    attendance_days = (
        item.get("attendance_days")
        or []
    )

    for day_number in range(1, 32):
        column_name = (
            f"D{day_number:02d}"
        )

        if day_number <= len(
            attendance_days
        ):
            row[column_name] = (
                attendance_days[
                    day_number - 1
                ]
            )
        else:
            row[column_name] = ""

    processed_rows.append(row)


df = pd.DataFrame(processed_rows)


# ============================================================================
# FILTER DISPLAY DATA
# ============================================================================

if df.empty:
    filtered_df = pd.DataFrame()

else:
    filtered_df = df[
        df["DB_Show_Flag"] == True
    ].copy()

    if employee_id_filter:
        filtered_df = filtered_df[
            filtered_df["EMP_ID"]
            .astype(str)
            .str.contains(
                employee_id_filter,
                case=False,
                na=False,
            )
        ]

    if employee_name_filter:
        filtered_df = filtered_df[
            filtered_df["EMP_Name"]
            .astype(str)
            .str.contains(
                employee_name_filter,
                case=False,
                na=False,
            )
        ]

    if status_filter == "Active Only":
        filtered_df = filtered_df[
            filtered_df["EMP_Status"]
            .astype(str)
            .str.upper()
            == "ACTIVE"
        ]

    elif status_filter == "In-Active Only":
        filtered_df = filtered_df[
            filtered_df["EMP_Status"]
            .astype(str)
            .str.upper()
            == "IN-ACTIVE"
        ]


# ============================================================================
# ATTENDANCE TABLE PREPARATION
# ============================================================================

st.markdown("---")
st.header("Attendance")

day_columns = [
    f"D{day_number:02d}"
    for day_number in range(1, 32)
]

grid_columns = [
    "Month_Year",
    "EMP_ID",
    "EMP_Name",
]

grid_columns += day_columns

grid_columns += [
    "Total_Hours",
    "Total_Minutes",
    "Total_Days",
    "Actual_Days_Worked",
    "Base_Monthly_Comp",
    "Rate_Per_Hour",
    "Gross_Payout",
    "Extra_Earning",
    "Advance_Given",
    "Final_Net_Payable",
    "Payment_Status",
    "Start_Date",
    "Last_Date",
    "EMP_Status",
]

available_grid_columns = [
    column
    for column in grid_columns
    if column in filtered_df.columns
]

if filtered_df.empty:
    st.info(
        "No attendance records match "
        "the selected filters."
    )

    display_df = pd.DataFrame(
        columns=available_grid_columns
    )

else:
    display_df = filtered_df[
        available_grid_columns
    ].copy()
    # ============================================================================
# ATTENDANCE TABLE
# ============================================================================

column_config = {
    "Month_Year": st.column_config.TextColumn(
        "Month/Year",
        disabled=True,
    ),
    "EMP_ID": st.column_config.TextColumn(
        "Employee ID",
        disabled=True,
    ),
    "EMP_Name": st.column_config.TextColumn(
        "Employee Name",
        disabled=True,
    ),
    "Total_Hours": st.column_config.NumberColumn(
        "Total Hours",
        format="%.2f",
        disabled=True,
    ),
    "Total_Minutes": st.column_config.NumberColumn(
        "Total Minutes",
        format="%.2f",
        disabled=True,
    ),
    "Total_Days": st.column_config.NumberColumn(
        "Total Days",
        format="%.2f",
        disabled=True,
    ),
    "Actual_Days_Worked": st.column_config.NumberColumn(
        "Actual Days Worked",
        format="%.2f",
        disabled=True,
    ),
    "Base_Monthly_Comp": st.column_config.NumberColumn(
        "Base Monthly Comp",
        format="₹%.2f",
        disabled=True,
    ),
    "Rate_Per_Hour": st.column_config.NumberColumn(
        "Rate Per Hour",
        format="₹%.2f",
        disabled=True,
    ),
    "Gross_Payout": st.column_config.NumberColumn(
        "Gross Payout",
        format="₹%.2f",
        disabled=True,
    ),
    "Extra_Earning": st.column_config.NumberColumn(
        "Extra Earning",
        format="₹%.2f",
        disabled=True,
    ),
    "Advance_Given": st.column_config.NumberColumn(
        "Advance Given",
        format="₹%.2f",
        disabled=True,
    ),
    "Final_Net_Payable": st.column_config.NumberColumn(
        "Final Net Payable",
        format="₹%.2f",
        disabled=True,
    ),
    "Payment_Status": st.column_config.SelectboxColumn(
        "Payment Status",
        options=["Pending", "Done"],
        required=True,
    ),
    "Start_Date": st.column_config.TextColumn(
        "Start Date",
        disabled=True,
    ),
    "Last_Date": st.column_config.TextColumn(
        "Last Working Date",
        disabled=True,
    ),
    "EMP_Status": st.column_config.TextColumn(
        "Employee Status",
        disabled=True,
    ),
}

for day_column in day_columns:
    column_config[day_column] = st.column_config.TextColumn(
        day_column.replace("D", ""),
        width="small",
        disabled=True,
    )


edited_df = st.data_editor(
    display_df,
    hide_index=True,
    width="stretch",
    column_config=column_config,
    key="attendance_ledger_editor",
)


# ============================================================================
# ATTENDANCE DOWNLOADS
# ============================================================================

st.markdown("---")
st.header("Attendance Downloads")

download_col1, download_col2 = st.columns(2)

with download_col1:
    csv_df = edited_df.copy()

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

    csv_df.to_csv(
        csv_buffer,
        index=False,
    )

    st.download_button(
        "Download Attendance CSV",
        data=csv_buffer.getvalue(),
        file_name=(
            "attendance_ledger_"
            f"{datetime.date.today()}.csv"
        ),
        mime="text/csv",
        disabled=edited_df.empty,
        key="download_attendance_csv",
    )


with download_col2:
    available_pdf_columns = list(
        edited_df.columns
    )

    default_pdf_columns = [
        column
        for column in [
            "Month_Year",
            "EMP_ID",
            "EMP_Name",
            "Total_Hours",
            "Gross_Payout",
            "Extra_Earning",
            "Advance_Given",
            "Final_Net_Payable",
            "Payment_Status",
        ]
        if column in available_pdf_columns
    ]

    selected_pdf_columns = st.multiselect(
        "PDF columns",
        options=available_pdf_columns,
        default=default_pdf_columns,
        key="attendance_pdf_columns",
    )

    if selected_pdf_columns and not edited_df.empty:
        pdf_data = generate_pdf(
            edited_df[selected_pdf_columns]
        )
    else:
        pdf_data = b""

    st.download_button(
        "Download Attendance PDF",
        data=pdf_data,
        file_name=(
            "attendance_ledger_"
            f"{datetime.date.today()}.pdf"
        ),
        mime="application/pdf",
        disabled=not bool(pdf_data),
        key="download_attendance_pdf",
    )


# ============================================================================
# PAYROLL ADJUSTMENT SECTION
# ============================================================================

st.markdown("---")

with st.expander(
    "Payroll Adjustment",
    expanded=False,
):
    st.header("Payroll Adjustment")

    st.caption(
        "Enter extra earnings or an advance for the selected employee "
        "and payroll month. Click Accept & Save to save the adjustment."
    )

    if df.empty:
        st.info(
            "No employees are available for payroll adjustment."
        )

    else:
        adjustment_source_df = df[
            df["DB_Show_Flag"] == True
        ].copy()

        employee_options = {}

        employee_rows = (
            adjustment_source_df[
                ["EMP_ID", "EMP_Name"]
            ]
            .drop_duplicates()
            .sort_values(
                by=["EMP_Name", "EMP_ID"],
                na_position="last",
            )
        )

        for _, employee_row in employee_rows.iterrows():
            employee_id_text = normalise_employee_id(
                employee_row["EMP_ID"]
            )

            numeric_employee_id = parse_bigint_employee_id(
                employee_id_text
            )

            if numeric_employee_id is None:
                continue

            employee_name = str(
                employee_row["EMP_Name"]
                or "Unnamed"
            )

            employee_options[employee_id_text] = (
                f"{employee_name} "
                f"(Employee ID: {employee_id_text})"
            )

        if not employee_options:
            st.error(
                "No numeric employee IDs are available. "
                "The payroll_adjustments_live.employee_id "
                "column requires BIGINT values."
            )

        else:
            adjustment_col1, adjustment_col2 = st.columns(2)

            with adjustment_col1:
                selected_employee_id = st.selectbox(
                    "Employee",
                    options=list(
                        employee_options.keys()
                    ),
                    format_func=lambda value: (
                        employee_options[value]
                    ),
                    key="payroll_adjustment_employee",
                )

            employee_month_rows = adjustment_source_df[
                adjustment_source_df["EMP_ID"].astype(str)
                == str(selected_employee_id)
            ]

            available_months = []

            for month_value in employee_month_rows[
                "DB_Month_Year"
            ].dropna().unique():

                canonical_value = canonical_month(
                    month_value
                )

                if canonical_value:
                    available_months.append(
                        canonical_value
                    )

            available_months = sorted(
                set(available_months),
                reverse=True,
            )

            if not available_months:
                st.warning(
                    "No payroll months are available "
                    "for this employee."
                )

            else:
                with adjustment_col2:
                    selected_month = st.selectbox(
                        "Payroll Month",
                        options=available_months,
                        format_func=display_month,
                        key="payroll_adjustment_month",
                    )

                lookup_key = (
                    normalise_employee_id(
                        selected_employee_id
                    ),
                    selected_month,
                )

                existing_adjustment = (
                    adjustment_lookup.get(
                        lookup_key,
                        {},
                    )
                )

                matching_rows = df[
                    (
                        df["EMP_ID"].astype(str)
                        == str(selected_employee_id)
                    )
                    & (
                        df["DB_Month_Year"].astype(str)
                        == str(selected_month)
                    )
                ]

                if matching_rows.empty:
                    regular_gross = 0.00
                else:
                    regular_gross = safe_float(
                        matching_rows.iloc[0].get(
                            "Gross_Payout",
                            0,
                        )
                    )

                form_col1, form_col2, form_col3 = st.columns(3)

                with form_col1:
                    extra_work_type = st.text_input(
                        "Extra Work Type",
                        value=(
                            existing_adjustment.get(
                                "extra_work_type"
                            )
                            or ""
                        ),
                        key=(
                            "adjustment_work_type_"
                            f"{selected_employee_id}_"
                            f"{selected_month}"
                        ),
                    )

                    extra_work_quantity = st.number_input(
                        "Extra Work Quantity",
                        min_value=0.00,
                        value=safe_float(
                            existing_adjustment.get(
                                "extra_work_quantity"
                            )
                        ),
                        step=0.01,
                        format="%.2f",
                        key=(
                            "adjustment_quantity_"
                            f"{selected_employee_id}_"
                            f"{selected_month}"
                        ),
                    )

                with form_col2:
                    extra_work_rate = st.number_input(
                        "Extra Work Rate",
                        min_value=0.00,
                        value=safe_float(
                            existing_adjustment.get(
                                "extra_work_rate"
                            )
                        ),
                        step=0.01,
                        format="%.2f",
                        key=(
                            "adjustment_rate_"
                            f"{selected_employee_id}_"
                            f"{selected_month}"
                        ),
                    )

                    existing_rate_unit = (
                        existing_adjustment.get(
                            "rate_unit"
                        )
                        or "Fixed"
                    )

                    if existing_rate_unit not in (
                        ADJUSTMENT_RATE_UNITS
                    ):
                        existing_rate_unit = "Fixed"

                    rate_unit = st.selectbox(
                        "Rate Unit",
                        options=ADJUSTMENT_RATE_UNITS,
                        index=ADJUSTMENT_RATE_UNITS.index(
                            existing_rate_unit
                        ),
                        key=(
                            "adjustment_rate_unit_"
                            f"{selected_employee_id}_"
                            f"{selected_month}"
                        ),
                    )

                with form_col3:
                    advance_given = st.number_input(
                        "Advance Given",
                        min_value=0.00,
                        value=safe_float(
                            existing_adjustment.get(
                                "advance_given"
                            )
                        ),
                        step=0.01,
                        format="%.2f",
                        key=(
                            "adjustment_advance_"
                            f"{selected_employee_id}_"
                            f"{selected_month}"
                        ),
                    )

                    existing_status = (
                        existing_adjustment.get(
                            "adjustment_status"
                        )
                        or "Pending"
                    )

                    if existing_status not in (
                        ADJUSTMENT_STATUSES
                    ):
                        existing_status = "Pending"

                    adjustment_status = st.selectbox(
                        "Adjustment Status",
                        options=ADJUSTMENT_STATUSES,
                        index=ADJUSTMENT_STATUSES.index(
                            existing_status
                        ),
                        key=(
                            "adjustment_status_"
                            f"{selected_employee_id}_"
                            f"{selected_month}"
                        ),
                    )

                adjustment_notes = st.text_area(
                    "Adjustment Notes",
                    value=(
                        existing_adjustment.get(
                            "adjustment_notes"
                        )
                        or ""
                    ),
                    key=(
                        "adjustment_notes_"
                        f"{selected_employee_id}_"
                        f"{selected_month}"
                    ),
                )

                extra_earning = calculate_extra_work_payment(
                    extra_work_quantity,
                    extra_work_rate,
                    rate_unit,
                )

                final_net_payable = calculate_final_net_payable(
                    regular_gross,
                    extra_earning,
                    advance_given,
                )

                metric_col1, metric_col2, metric_col3 = st.columns(3)

                with metric_col1:
                    st.metric(
                        "Regular Gross",
                        f"₹{regular_gross:,.2f}",
                    )

                with metric_col2:
                    st.metric(
                        "Extra Earning",
                        f"₹{extra_earning:,.2f}",
                    )

                with metric_col3:
                    st.metric(
                        "Final Net Payable",
                        f"₹{final_net_payable:,.2f}",
                    )

                st.info(
                    f"Regular gross ₹{regular_gross:,.2f} "
                    f"+ extra earning ₹{extra_earning:,.2f} "
                    f"- advance ₹{advance_given:,.2f} "
                    f"= final net payable "
                    f"₹{final_net_payable:,.2f}"
                )
                                if st.button(
                    "Accept & Save",
                    type="primary",
                    use_container_width=True,
                    key=(
                        "save_adjustment_"
                        f"{selected_employee_id}_"
                        f"{selected_month}"
                    ),
                ):
                    numeric_employee_id = parse_bigint_employee_id(
                        selected_employee_id
                    )

                    if numeric_employee_id is None:
                        st.error(
                            "The selected employee ID must be numeric "
                            "because the database column uses BIGINT."
                        )

                    elif not selected_month:
                        st.error(
                            "A valid payroll month is required."
                        )

                    else:
                        approved_by = None
                        approved_at = None

                        if adjustment_status == "Approved":
                            approved_by = APP_USER
                            approved_at = (
                                datetime.datetime.now(
                                    datetime.timezone.utc
                                ).isoformat()
                            )

                        payload = {
                            "employee_id": numeric_employee_id,
                            "month_year": selected_month,
                            "extra_work_type": (
                                extra_work_type.strip()
                            ),
                            "extra_work_quantity": round(
                                float(extra_work_quantity),
                                2,
                            ),
                            "extra_work_rate": round(
                                float(extra_work_rate),
                                2,
                            ),
                            "rate_unit": rate_unit,
                            "extra_work_payment": round(
                                float(extra_earning),
                                2,
                            ),
                            "advance_given": round(
                                float(advance_given),
                                2,
                            ),
                            "adjustment_notes": (
                                adjustment_notes.strip()
                            ),
                            "adjustment_status": adjustment_status,
                            "source_identifier": SOURCE_IDENTIFIER,
                            "created_by": APP_USER,
                            "approved_by": approved_by,
                            "approved_at": approved_at,
                        }

                        with st.spinner(
                            "Saving payroll adjustment..."
                        ):
                            save_success, save_result = (
                                save_payroll_adjustment(payload)
                            )

                        if save_success:
                            st.success(
                                "Payroll adjustment saved successfully."
                            )

                            st.cache_data.clear()
                            st.rerun()

                        else:
                            st.error(
                                "Unable to save payroll adjustment: "
                                f"{save_result}"
                            )
