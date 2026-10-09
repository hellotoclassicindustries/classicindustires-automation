# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY
# PAYROLL & ATTENDANCE WORKFLOW
#
# Page order:
#   1. Attendance filters
#   2. Attendance ledger
#   3. CSV/PDF downloads
#   4. Payroll Adjustment expandable section
#
# Payroll adjustment values displayed in the attendance ledger:
#   - Extra_Earning
#   - Advance_Given
#   - Final_Net_Payable
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
from reportlab.lib.styles import (
    ParagraphStyle,
    getSampleStyleSheet,
)
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

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

SOURCE_IDENTIFIER = "STREAMLIT_LIVE_UI"

APP_USER = (
    st.session_state.get("user_name")
    or st.session_state.get("username")
    or "Streamlit User"
)


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
# GENERAL HELPERS
# ============================================================================

def safe_float(value):
    """Safely convert a value to float."""

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
    """Round a monetary amount to two decimal places."""
    return round(safe_float(value), 2)


def normalise_employee_id(value):
    """
    Convert employee IDs returned by PostgreSQL or pandas into
    a consistent string representation.
    """

    if value is None:
        return ""

    value_text = str(value).strip()

    if value_text.lower() in ["none", "nan", "null", "n/a"]:
        return ""

    # Convert values such as 123.0 to 123.
    if value_text.endswith(".0"):
        value_text = value_text[:-2]

    return value_text


def parse_bigint_employee_id(value):
    """
    Convert an employee ID to an integer compatible with PostgreSQL BIGINT.

    Returns None if the value is not numeric.
    """

    employee_id_text = normalise_employee_id(value)

    if not employee_id_text:
        return None

    try:
        return int(employee_id_text)
    except (TypeError, ValueError):
        return None


def parse_row_date(month_year_value):
    """
    Convert supported month formats to datetime.date(year, month, 1).

    Supported examples:

        2026-09
        2026-09-01
        09-2026
        September-2026
        September/2026
    """

    if month_year_value is None:
        return None

    month_year_text = str(month_year_value).strip()

    if not month_year_text:
        return None

    if month_year_text.upper() == "N/A":
        return None

    normalized = month_year_text.replace("/", "-")
    normalized_upper = normalized.upper()

    year_match = re.search(r"\b(20\d{2})\b", normalized)

    if year_match:
        year = int(year_match.group(1))
    else:
        year = datetime.date.today().year

    # Month names, for example September-2026.
    for month_number in range(1, 13):
        full_month_name = calendar.month_name[month_number].upper()
        short_month_name = calendar.month_abbr[month_number].upper()

        if (
            full_month_name in normalized_upper
            or short_month_name in normalized_upper
        ):
            return datetime.date(year, month_number, 1)

    # YYYY-MM.
    year_month_match = re.search(
        r"\b(20\d{2})-(0[1-9]|1[0-2])\b",
        normalized,
    )

    if year_month_match:
        return datetime.date(
            int(year_month_match.group(1)),
            int(year_month_match.group(2)),
            1,
        )

    # Numeric formats such as 09-2026.
    numeric_values = re.findall(
        r"\b(\d{1,2})\b",
        normalized,
    )

    for numeric_value in numeric_values:
        month_number = int(numeric_value)

        if 1 <= month_number <= 12:
            return datetime.date(year, month_number, 1)

    return None


def canonical_month_year(month_year_value):
    """Convert a month value to the database format YYYY-MM."""

    row_date = parse_row_date(month_year_value)

    if row_date is None:
        return None

    return row_date.strftime("%Y-%m")


def display_month_year(month_year_value):
    """Convert YYYY-MM to a readable month label."""

    row_date = parse_row_date(month_year_value)

    if row_date is None:
        return str(month_year_value or "N/A")

    return row_date.strftime("%B-%Y")


def get_days_in_month(month_year_value):
    """Return the actual number of days in the payroll month."""

    row_date = parse_row_date(month_year_value)

    if row_date:
        return calendar.monthrange(
            row_date.year,
            row_date.month,
        )[1]

    return 31


def calculate_extra_work_payment(
    quantity,
    rate,
    rate_unit,
):
    """
    Calculate extra-work payment in application memory.

    For Fixed:
        The rate is treated as the complete fixed amount.

    For other units:
        Quantity is multiplied by rate.
    """

    quantity = max(0.00, safe_float(quantity))
    rate = max(0.00, safe_float(rate))

    if rate_unit == "Fixed":
        return money(rate)

    return money(quantity * rate)


def calculate_final_net_payable(
    regular_gross_payout,
    extra_work_payment,
    advance_given,
):
    """Calculate regular gross plus extra earning minus advance."""

    regular_gross_payout = max(
        0.00,
        safe_float(regular_gross_payout),
    )

    extra_work_payment = max(
        0.00,
        safe_float(extra_work_payment),
    )

    advance_given = max(
        0.00,
        safe_float(advance_given),
    )

    return money(
        regular_gross_payout
        + extra_work_payment
        - advance_given
    )


# ============================================================================
# SUPABASE DATA FUNCTIONS
# ============================================================================

@st.cache_data(ttl=5)
def fetch_vw_attendance_ledger():
    """Fetch records from vw_attendance_ledger."""

    endpoint = (
        f"{SUPABASE_URL.strip('/')}"
        "/rest/v1/vw_attendance_ledger"
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
            "Attendance ledger request failed with HTTP "
            f"{response.status_code}: {response.text[:500]}"
        )

        return []

    except requests.RequestException as error:
        st.warning(
            f"Unable to connect to the attendance database: {error}"
        )
        return []


@st.cache_data(ttl=5)
def fetch_payroll_adjustments():
    """Fetch payroll adjustment records."""

    endpoint = (
        f"{SUPABASE_URL.strip('/')}"
        "/rest/v1/payroll_adjustments_live"
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
            "Payroll adjustment request failed with HTTP "
            f"{response.status_code}: {response.text[:500]}"
        )

        return []

    except requests.RequestException as error:
        st.warning(
            f"Unable to load payroll adjustments: {error}"
        )
        return []


def save_payroll_adjustment(payload):
    """
    Insert or update an adjustment using employee_id + month_year.

    This requires a unique constraint on:

        employee_id, month_year
    """

    endpoint = (
        f"{SUPABASE_URL.strip('/')}"
        "/rest/v1/payroll_adjustments_live"
        "?on_conflict=employee_id,month_year"
    )

    upsert_headers = {
        **HEADERS,
        "Prefer": (
            "resolution=merge-duplicates,"
            "return=representation"
        ),
    }

    try:
        response = requests.post(
            endpoint,
            headers=upsert_headers,
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


def update_db_payment_status(
    employee_id,
    month_year,
    new_status,
):
    """Update payment status in raw_attendance_feed."""

    canonical_month = canonical_month_year(month_year)

    if not canonical_month:
        return False

    endpoint = (
        f"{SUPABASE_URL.strip('/')}"
        "/rest/v1/raw_attendance_feed"
        f"?employee_id=eq.{employee_id}"
        f"&month_year=eq.{canonical_month}"
    )

    payload = {
        "payment_status": new_status,
    }

    try:
        response = requests.patch(
            endpoint,
            headers=HEADERS,
            json=payload,
            timeout=30,
        )

        return response.status_code in (200, 201, 204)

    except requests.RequestException:
        return False


def build_adjustment_lookup(records):
    """
    Build lookup using:

        normalized employee ID + canonical YYYY-MM
    """

    lookup = {}

    for record in records or []:
        employee_id = normalise_employee_id(
            record.get("employee_id")
        )

        month_year = canonical_month_year(
            record.get("month_year")
        )

        if not employee_id or not month_year:
            continue

        lookup[
            (
                employee_id,
                month_year,
            )
        ] = record

    return lookup


# ============================================================================
# PDF GENERATION
# ============================================================================

def generate_ledger_matrix_pdf(dataframe):
    """Generate a landscape PDF from a DataFrame."""

    if (
        dataframe is None
        or dataframe.empty
        or len(dataframe.columns) == 0
    ):
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

    story = [
        Paragraph(
            "Payroll & Attendance Ledger",
            title_style,
        ),
        Spacer(1, 10),
    ]

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

    column_width = max(
        20,
        available_width / max(column_count, 1),
    )

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
# LOAD DATA
# ============================================================================

view_records_data = fetch_vw_attendance_ledger()
adjustment_records_data = fetch_payroll_adjustments()

adjustment_lookup = build_adjustment_lookup(
    adjustment_records_data
)

if not view_records_data:
    st.info(
        "📋 No integrated database rows were found in "
        "vw_attendance_ledger."
    )
    st.stop()


# ============================================================================
# PAGE HEADER AND FILTERS
# ============================================================================

st.title("📋 Attendance Ledger")

st.caption(
    "Attendance is displayed first. Payroll adjustments are available "
    "below the attendance downloads."
)

today = datetime.date.today()
previous_month_date = today - relativedelta(months=1)

default_start = previous_month_date.replace(day=1)

default_end = previous_month_date.replace(
    day=calendar.monthrange(
        previous_month_date.year,
        previous_month_date.month,
    )[1]
)

chosen_dates = st.date_input(
    "Select Payout Month:",
    value=(default_start, default_end),
    key="attendance_calendar_range_picker",
)

if isinstance(chosen_dates, (tuple, list)) and len(chosen_dates) == 2:
    start_cal, end_cal = chosen_dates
else:
    start_cal = default_start
    end_cal = default_end


filter_col1, filter_col2, filter_col3 = st.columns(3)

with filter_col1:
    search_mat_id = st.text_input(
        "Filter by Employee ID:",
        "",
        key="attendance_employee_id_filter",
    ).strip()

with filter_col2:
    search_mat_name = st.text_input(
        "Filter by Employee Name:",
        "",
        key="attendance_employee_name_filter",
    ).strip()

with filter_col3:
    search_mat_status = st.selectbox(
        "Filter by Employee Status:",
        options=[
            "All Statuses",
            "Active Only",
            "In-Active Only",
        ],
        key="attendance_employee_status_filter",
    )


# ============================================================================
# BUILD ATTENDANCE AND PAYROLL DATA
# ============================================================================

processed_rows = []

for item in view_records_data:
    original_month_year = item.get("month_year") or "N/A"

    row_date = parse_row_date(original_month_year)
    database_month_year = canonical_month_year(
        original_month_year
    )

    if row_date:
        if not (start_cal <= row_date <= end_cal):
            continue

    employee_id_text = normalise_employee_id(
        item.get("employee_id")
    )

    employee_name = (
        item.get("employee_name")
        or "Unnamed"
    )

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
        total_hours_worked * 60.00,
        2,
    )

    month_days = get_days_in_month(
        original_month_year
    )

    actual_days_worked = round(
        total_hours_worked / configured_shift_hours,
        2,
    )

    if (
        str(current_status).upper() == "ACTIVE"
        and month_days > 0
        and configured_shift_hours > 0
    ):
        daily_allocation_rate = (
            base_monthly_comp / float(month_days)
        )

        # Hourly rate rounded upward to the nearest penny.
        per_hour_rate = (
            math.ceil(
                (
                    daily_allocation_rate
                    / configured_shift_hours
                ) * 100
            ) / 100.00
        )

        # Per-minute rate rounded upward to four decimals.
        per_minute_rate = (
            math.ceil(
                (per_hour_rate / 60.00) * 10000
            ) / 10000.00
        )

        calculated_gross_payout = money(
            total_hours_worked * per_hour_rate
        )

    else:
        per_hour_rate = 0.00
        per_minute_rate = 0.00
        calculated_gross_payout = 0.00

    adjustment = adjustment_lookup.get(
        (
            employee_id_text,
            database_month_year,
        ),
        {},
    )

    adjustment_quantity = safe_float(
        adjustment.get("extra_work_quantity")
    )

    adjustment_rate = safe_float(
        adjustment.get("extra_work_rate")
    )

    adjustment_payment = safe_float(
        adjustment.get("extra_work_payment")
    )

    adjustment_advance = safe_float(
        adjustment.get("advance_given")
    )

    final_net_payable = calculate_final_net_payable(
        calculated_gross_payout,
        adjustment_payment,
        adjustment_advance,
    )

    row_dict = {
        "Month_Year": original_month_year,
        "DB_Month_Year": database_month_year,
        "EMP_ID": employee_id_text or "N/A",
        "EMP_Name": employee_name,

        "Over_Time": safe_float(
            item.get("over_time")
        ),
        "Less_Time": safe_float(
            item.get("less_time")
        ),
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

        # Payroll adjustment data displayed in the attendance ledger.
        "Extra_Work_Type": (
            adjustment.get("extra_work_type")
            or ""
        ),
        "Extra_Work_Quantity": adjustment_quantity,
        "Extra_Work_Rate": adjustment_rate,
        "Rate_Unit": (
            adjustment.get("rate_unit")
            or "Fixed"
        ),
        "Extra_Earning": adjustment_payment,
        "Advance_Given": adjustment_advance,
        "Final_Net_Payable": final_net_payable,
        "Adjustment_Status": (
            adjustment.get("adjustment_status")
            or "No UI Adjustment"
        ),
        "Adjustment_Source": (
            adjustment.get("source_identifier")
            or "NO_UI_ADJUSTMENT"
        ),
        "Adjustment_Notes": (
            adjustment.get("adjustment_notes")
            or ""
        ),

        "Payment_Status": (
            item.get("payment_status")
            or "Pending"
        ),
        "DB_Show_Flag": (
            item.get("show")
            if item.get("show") is not None
            else True
        ),
    }

    for day_number in range(1, 32):
        day_column = f"D{day_number:02d}"

        if (
            days_list
            and day_number - 1 < len(days_list)
        ):
            row_dict[day_column] = (
                days_list[day_number - 1]
            )
        else:
            row_dict[day_column] = ""

    processed_rows.append(row_dict)


df = pd.DataFrame(processed_rows)


# ============================================================================
# ATTENDANCE FILTERING
# ============================================================================

if df.empty:
    st.warning(
        "⚠️ No attendance records match the selected date range."
    )
    filtered_df = pd.DataFrame()
else:
    filtered_df = df[
        df["DB_Show_Flag"] == True
    ].copy()

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


# ============================================================================
# ATTENDANCE LEDGER
# ============================================================================

st.markdown("---")
st.header("📋 Attendance Ledger")

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

        # Adjustment columns displayed in attendance.
        "Extra_Work_Type",
        "Extra_Work_Quantity",
        "Extra_Work_Rate",
        "Rate_Unit",
        "Extra_Earning",
        "Advance_Given",
        "Final_Net_Payable",
        "Adjustment_Status",
        "Adjustment_Source",
        "Adjustment_Notes",

        "Payment_Status",
        "Start_Date",
        "Last_Date",
        "EMP_Status",
    ]
)

if filtered_df.empty:
    st.warning(
        "⚠️ No ledger records match the active filters."
    )

    render_df = pd.DataFrame(
        columns=[
            column_name
            for column_name in grid_columns_order
        ]
    )

else:
    validated_columns = [
        column_name
        for column_name in grid_columns_order
        if column_name in filtered_df.columns
    ]

    render_df = filtered_df[
        validated_columns
    ].copy()


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
    "Extra_Work_Type": st.column_config.TextColumn(
        "Extra Work Type",
        width="medium",
        disabled=True,
    ),
    "Extra_Work_Quantity": st.column_config.NumberColumn(
        "Extra Work Qty",
        format="%.2f",
        width="small",
        disabled=True,
    ),
    "Extra_Work_Rate": st.column_config.NumberColumn(
        "Extra Work Rate",
        format="₹%.2f",
        width="small",
        disabled=True,
    ),
    "Rate_Unit": st.column_config.TextColumn(
        "Rate Unit",
        width="small",
        disabled=True,
    ),
    "Extra_Earning": st.column_config.NumberColumn(
        "Extra Earning",
        format="₹%.2f",
        width="medium",
        disabled=True,
    ),
    "Advance_Given": st.column_config.NumberColumn(
        "Advance Given",
        format="₹%.2f",
        width="medium",
        disabled=True,
    ),
    "Final_Net_Payable": st.column_config.NumberColumn(
        "Final Net Payable",
        format="₹%.2f",
        width="medium",
        disabled=True,
    ),
    "Adjustment_Status": st.column_config.TextColumn(
        "Adjustment Status",
        width="medium",
        disabled=True,
    ),
    "Adjustment_Source": st.column_config.TextColumn(
        "Adjustment Source",
        width="medium",
        disabled=True,
    ),
    "Adjustment_Notes": st.column_config.TextColumn(
        "Adjustment Notes",
        width="large",
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
    if day_column in render_df.columns:
        column_config[day_column] = st.column_config.TextColumn(
            day_column.replace("D", ""),
            width=45,
            disabled=True,
        )


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

if edited_rows and not render_df.empty:
    for row_index_text, altered_properties in edited_rows.items():
        try:
            row_index = int(row_index_text)
        except (TypeError, ValueError):
            continue

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
                f"Payment status updated to '{updated_status}' "
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
# ATTENDANCE DOWNLOADS
# ============================================================================

st.markdown("---")
st.header("📤 Attendance Downloads")

export_df = edited_df.copy()

download_col1, download_col2 = st.columns(2)


# ----------------------------------------------------------------------------
# CSV DOWNLOAD
# ----------------------------------------------------------------------------

with download_col1:
    st.subheader("📊 CSV Export")

    csv_df = export_df.copy()

    # Preserve values such as 11/30 when opened in Excel.
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
        label="⬇️ Download Attendance CSV",
        data=csv_buffer.getvalue(),
        file_name=(
            "Attendance_Ledger_"
            f"{datetime.date.today()}.csv"
        ),
        mime="text/csv",
        key="attendance_csv_download",
        disabled=export_df.empty,
    )


# ----------------------------------------------------------------------------
# PDF DOWNLOAD
# ----------------------------------------------------------------------------

with download_col2:
    st.subheader("📄 PDF Export")

    available_pdf_columns = list(
        export_df.columns
    )

    default_pdf_columns = [
        column_name
        for column_name in [
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
        if column_name in available_pdf_columns
    ]

    selected_pdf_columns = st.multiselect(
        "Select PDF columns:",
        options=available_pdf_columns,
        default=default_pdf_columns,
        key="attendance_pdf_columns",
    )

    if (
        selected_pdf_columns
        and not export_df.empty
    ):
        pdf_target_df = export_df[
            selected_pdf_columns
        ].copy()

        pdf_data = generate_ledger_matrix_pdf(
            pdf_target_df
        )

    else:
        pdf_data = b""

        if not selected_pdf_columns:
            st.warning(
                "Select at least one column for the PDF."
            )

    st.download_button(
        label="⬇️ Download Attendance PDF",
        data=pdf_data,
        file_name=(
            "Attendance_Ledger_"
            f"{datetime.date.today()}.pdf"
        ),
        mime="application/pdf",
        key="attendance_pdf_download",
        disabled=not bool(pdf_data),
    )


# ============================================================================
# PAYROLL ADJUSTMENT SECTION
# ============================================================================

st.markdown("---")

with st.expander(
    "💰 Payroll Adjustment",
    expanded=False,
):
    st.header("Payroll Adjustment")

    st.caption(
        "Enter extra earnings or an advance for an employee and "
        "payroll month. The adjustment is written to Supabase only "
        "after clicking Accept & Save."
    )

    adjustment_source_df = df[
        df["DB_Show_Flag"] == True
    ].copy()

    if adjustment_source_df.empty:
        st.info(
            "No visible employees are available for payroll adjustment."
        )

    else:
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

        employee_options = {}

        for _, employee_row in employee_rows.iterrows():
            employee_id_text = normalise_employee_id(
                employee_row["EMP_ID"]
            )

            numeric_employee_id = parse_bigint_employee_id(
                employee_id_text
            )

            # Only show IDs that can be stored in BIGINT.
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
                "The payroll adjustment employee_id column "
                "requires BIGINT values."
            )

        else:
            adjustment_col1, adjustment_col2 = st.columns(2)

            with adjustment_col1:
                selected_employee_id = st.selectbox(
                    "Employee",
                    options=list(
                        employee_options.keys()
                    ),
                    format_func=lambda value
