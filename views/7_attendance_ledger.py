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
]


# ============================================================================
# GENERAL HELPERS
# ============================================================================

def safe_float(value):
    """Safely convert a value to float."""

    if value is None:
        return 0.00

    value_text = str(value).strip()

    if value_text == "" or value_text.lower() in ["none", "nan"]:
        return 0.00

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.00


def money(value):
    """Return a value rounded to two decimal places."""

    return round(safe_float(value), 2)


def normalise_employee_id(value):
    """Normalise employee IDs for comparison and database use."""

    if value is None:
        return ""

    value_text = str(value).strip()

    if value_text.endswith(".0"):
        value_text = value_text[:-2]

    return value_text


def parse_row_date(month_year_value):
    """
    Convert supported month formats into datetime.date(year, month, 1).

    Supported examples:
        2026-09
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

    # Check month names first.
    for month_number in range(1, 13):
        full_month_name = calendar.month_name[month_number].upper()
        short_month_name = calendar.month_abbr[month_number].upper()

        if (
            full_month_name in normalized_upper
            or short_month_name in normalized_upper
        ):
            return datetime.date(year, month_number, 1)

    # Handle YYYY-MM.
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

    # Handle numeric formats such as 09-2026.
    numeric_values = re.findall(r"\b(\d{1,2})\b", normalized)

    for numeric_value in numeric_values:
        month_number = int(numeric_value)

        if 1 <= month_number <= 12:
            return datetime.date(year, month_number, 1)

    return None


def canonical_month_year(month_year_value):
    """
    Convert a month value into the database format YYYY-MM.
    """

    row_date = parse_row_date(month_year_value)

    if row_date is None:
        return None

    return row_date.strftime("%Y-%m")


def display_month_year(month_year_value):
    """Convert YYYY-MM into a readable month label."""

    row_date = parse_row_date(month_year_value)

    if row_date is None:
        return str(month_year_value or "N/A")

    return row_date.strftime("%B-%Y")


def get_days_in_month(month_year_value):
    """Return the number of days in a payroll month."""

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
    Calculate extra-work payment in Streamlit memory.

    For Fixed, the rate is treated as the complete fixed payment.
    For all other units, payment equals quantity multiplied by rate.
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
    """
    Calculate final net payable in Streamlit memory.
    """

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

@st.cache_data(ttl=2)
def fetch_vw_attendance_ledger():
    """Fetch attendance ledger records."""

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
            f"status {response.status_code}: "
            f"{response.text[:300]}"
        )

        return []

    except requests.RequestException as error:
        st.warning(
            f"Unable to connect to the attendance database: {error}"
        )
        return []


@st.cache_data(ttl=2)
def fetch_payroll_adjustments():
    """Fetch live payroll adjustment records."""

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
            f"status {response.status_code}: "
            f"{response.text[:300]}"
        )

        return []

    except requests.RequestException as error:
        st.warning(
            f"Unable to load payroll adjustments: {error}"
        )
        return []


def save_payroll_adjustment(adjustment_payload):
    """
    Insert or update one employee/month adjustment.

    The database unique constraint is:

        employee_id + month_year
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
            json=adjustment_payload,
            timeout=30,
        )

        if response.status_code in (200, 201):
            try:
                response_data = response.json()
            except ValueError:
                response_data = []

            return True, response_data

        return False, (
            f"HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )

    except requests.RequestException as error:
        return False, str(error)


def update_db_payment_status(
    employee_id,
    month_year,
    new_status,
):
    """Update payment status in raw_attendance_feed."""

    endpoint = (
        f"{SUPABASE_URL.strip('/')}"
        "/rest/v1/raw_attendance_feed"
        f"?employee_id=eq.{employee_id}"
        f"&month_year=eq.{month_year}"
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


def build_adjustment_lookup(adjustment_records):
    """
    Build a lookup using:

        normalised employee_id + canonical YYYY-MM month
    """

    lookup = {}

    for record in adjustment_records or []:
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
# PDF EXPORT
# ============================================================================

def generate_ledger_matrix_pdf(dataframe):
    """Generate a landscape PDF from selected rows and columns."""

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
# LOAD DATABASE DATA
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
# PAYROLL FILTERS
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
        total_hours_worked * 60.0,
        2,
    )

    month_days = get_days_in_month(
        original_month_year
    )

    if configured_shift_hours > 0:
        actual_days_worked = round(
            total_hours_worked
            / configured_shift_hours,
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
            base_monthly_comp
            / float(month_days)
        )

        per_hour_rate = (
            math.ceil(
                (
                    daily_allocation_rate
                    / configured_shift_hours
                ) * 100
            ) / 100.0
        )

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
        "Extra_Work_Payment": adjustment_payment,
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
# PAYROLL ADJUSTMENT SECTION
# ============================================================================

st.markdown("---")
st.header("💰 Payroll Adjustment")

if df.empty:
    st.warning(
        "No attendance records are available for "
        "the selected payroll month."
    )
else:
    adjustment_source_df = df[
        df["DB_Show_Flag"] == True
    ].copy()

    if adjustment_source_df.empty:
        st.info(
            "No visible employees are available for "
            "the selected payroll month."
        )
    else:
        employee_rows = (
            adjustment_source_df
            .drop_duplicates(
                subset=["EMP_ID", "EMP_Name"]
            )
            .sort_values(
                by=["EMP_Name", "EMP_ID"]
            )
        )

        employee_options = {}

        for _, employee_row in employee_rows.iterrows():
            employee_id = normalise_employee_id(
                employee_row["EMP_ID"]
            )

            employee_name = employee_row["EMP_Name"]

            if not employee_id or employee_id == "N/A":
                continue

            employee_options[employee_id] = (
                f"{employee_name} "
                f"(ID: {employee_id})"
            )

        if not employee_options:
            st.info(
                "No valid BIGINT employee IDs are available."
            )
        else:
            adjustment_col1, adjustment_col2 = st.columns(2)

            with adjustment_col1:
                selected_emp_key = st.selectbox(
                    "Select Employee",
                    options=list(
                        employee_options.keys()
                    ),
                    format_func=lambda value: (
                        employee_options[value]
                    ),
                    key="adjustment_employee_select",
                )

            employee_month_rows = adjustment_source_df[
                adjustment_source_df["EMP_ID"].astype(str)
                == str(selected_emp_key)
            ].copy()

            available_adjustment_months = sorted(
                [
                    str(month)
                    for month in (
                        employee_month_rows[
                            "DB_Month_Year"
                        ]
                        .dropna()
                        .unique()
                    )
                    if month
                ],
                reverse=True,
            )

            with adjustment_col2:
                selected_adjustment_month = st.selectbox(
                    "Select Payroll Month",
                    options=available_adjustment_months,
                    format_func=display_month_year,
                    key="adjustment_month_select",
                )

            target_canonical_month = (
                selected_adjustment_month
            )

            matched_rows = df[
                (df["EMP_ID"].astype(str) == str(selected_emp_key))
                & (
                    df["DB_Month_Year"].astype(str)
                    == str(target_canonical_month)
                )
            ]

            if matched_rows.empty:
                regular_gross_payout = 0.00
            else:
                regular_gross_payout = safe_float(
                    matched_rows.iloc[0]["Gross_Payout"]
                )

            existing_adjustment = adjustment_lookup.get(
                (
                    normalise_employee_id(
                        selected_emp_key
                    ),
                    target_canonical_month,
                ),
                {},
            )

            existing_work_type = (
                existing_adjustment.get(
                    "extra_work_type"
                )
                or ""
            )

            existing_quantity = safe_float(
                existing_adjustment.get(
                    "extra_work_quantity"
                )
            )

            existing_rate = safe_float(
                existing_adjustment.get(
                    "extra_work_rate"
                )
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

            existing_advance = safe_float(
                existing_adjustment.get(
                    "advance_given"
                )
            )

            existing_notes = (
                existing_adjustment.get(
                    "adjustment_notes"
                )
                or ""
            )

            existing_status = (
                existing_adjustment.get(
                    "adjustment_status"
                )
                or "Approved"
            )

            if existing_status not in ADJUSTMENT_STATUSES:
                existing_status = "Approved"

            st.caption(
                "Only clicking 'Accept & Save' writes "
                "the adjustment to Supabase."
            )

            form_col1, form_col2, form_col3 = st.columns(3)

            with form_col1:
                input_work_type = st.text_input(
                    "Extra Work Type",
                    value=existing_work_type,
                    placeholder=(
                        "Example: Weekend shift"
                    ),
                    key="adjustment_work_type_input",
                )

                input_quantity = st.number_input(
                    "Extra Work Quantity",
                    min_value=0.00,
                    value=existing_quantity,
                    step=0.01,
                    format="%.2f",
                    key="adjustment_quantity_input",
                )

            with form_col2:
                input_rate = st.number_input(
                    "Extra Work Rate",
                    min_value=0.00,
                    value=existing_rate,
                    step=0.01,
                    format="%.2f",
                    key="adjustment_rate_input",
                )

                input_rate_unit = st.selectbox(
                    "Rate Unit",
                    options=ADJUSTMENT_RATE_UNITS,
                    index=ADJUSTMENT_RATE_UNITS.index(
                        existing_rate_unit
                    ),
                    key="adjustment_rate_unit_select",
                )

            with form_col3:
                input_advance = st.number_input(
                    "Advance Given",
                    min_value=0.00,
                    value=existing_advance,
                    step=0.01,
                    format="%.2f",
                    key="adjustment_advance_input",
                )

                input_status = st.selectbox(
                    "Adjustment Status",
                    options=ADJUSTMENT_STATUSES,
                    index=ADJUSTMENT_STATUSES.index(
                        existing_status
                    ),
                    key="adjustment_status_select",
                )

            input_notes = st.text_area(
                "Adjustment Notes",
                value=existing_notes,
                placeholder=(
                    "Enter extra-work and advance notes."
                ),
                key="adjustment_notes_input",
            )

            calculated_extra_payment = (
                calculate_extra_work_payment(
                    input_quantity,
                    input_rate,
                    input_rate_unit,
                )
            )

            calculated_net_payable = (
                calculate_final_net_payable(
                    regular_gross_payout,
                    calculated_extra_payment,
                    input_advance,
                )
            )

            preview_col1, preview_col2 = st.columns(2)

            with preview_col1:
                st.metric(
                    "Regular Gross Payout",
                    f"₹{regular_gross_payout:,.2f}",
                )

                st.metric(
                    "Extra-Work Payment",
                    f"₹{calculated_extra_payment:,.2f}",
                )

            with preview_col2:
                st.metric(
                    "Advance Given",
                    f"₹{input_advance:,.2f}",
                )

                st.metric(
                    "Final Net Payable",
                    f"₹{calculated_net_payable:,.2f}",
                )

            if calculated_net_payable < 0:
                st.warning(
                    "The advance is greater than the gross payout "
                    "plus extra-work payment. The calculated net "
                    "payable is negative."
                )

            st.info(
                f"Calculation preview: Regular gross "
                f"₹{regular_gross_payout:,.2f} + extra work "
                f"₹{calculated_extra_payment:,.2f} - advance "
                f"₹{input_advance:,.2f} = final net payable "
                f"₹{calculated_net_payable:,.2f}"
            )

            if st.button(
                "✅ Accept & Save",
                type="primary",
                use_container_width=True,
                key="save_adjustment_action_btn",
            ):
                selected_emp_id_text = (
                    normalise_employee_id(
                        selected_emp_key
                    )
                )

                if not selected_emp_id_text.isdigit():
                    st.error(
                        "The selected employee ID is not a "
                        "valid BIGINT value."
                    )
                elif not target_canonical_month:
                    st.error(
                        "A valid payroll month must be selected."
                    )
                else:
                    approved_at = None
                    approved_by = None
