# ============================================================================
# VIEWS/7_ATTENDANCE_LEDGER.PY
# PAYROLL & ATTENDANCE WORKFLOW
# ============================================================================

import calendar
import datetime
import io
import math
import re
from xml.sax.saxutils import escape

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
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# ============================================================================
# SUPABASE CONFIGURATION
# ============================================================================

try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"].strip("/")
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

except Exception:
    st.error(
        "❌ Missing SUPABASE_URL or SUPABASE_KEY in Streamlit secrets."
    )
    st.stop()


HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


# ============================================================================
# GLOBAL HELPERS
# ============================================================================

def safe_float(value, default=0.00):
    """Safely convert any value to float."""

    if value is None:
        return default

    if isinstance(value, bool):
        return float(value)

    try:
        value_text = str(value).strip()

        if not value_text:
            return default

        if value_text.lower() in {"none", "nan", "null"}:
            return default

        return float(value_text)

    except (TypeError, ValueError):
        return default


def money(value):
    """Format a value as Indian currency."""

    return f"₹{safe_float(value):,.2f}"


def parse_row_date(month_year_value):
    """
    Convert values such as:

    September-2026
    September/2026
    Sep-2026
    09-2026
    2026-09

    into datetime.date(year, month, 1).
    """

    if month_year_value is None:
        return None

    text = str(month_year_value).strip()

    if not text or text.upper() == "N/A":
        return None

    normalized = text.replace("/", "-").replace("_", "-")
    normalized_upper = normalized.upper()

    year_match = re.search(r"\b(20\d{2})\b", normalized)

    if year_match:
        year = int(year_match.group(1))
    else:
        year = datetime.date.today().year

    for month_number in range(1, 13):
        full_name = calendar.month_name[month_number].upper()
        short_name = calendar.month_abbr[month_number].upper()

        if (
            re.search(rf"\b{full_name}\b", normalized_upper)
            or re.search(rf"\b{short_name}\b", normalized_upper)
        ):
            return datetime.date(year, month_number, 1)

    numeric_values = re.findall(r"\b(\d{1,2})\b", normalized)

    for numeric_value in numeric_values:
        month_number = int(numeric_value)

        if 1 <= month_number <= 12:
            return datetime.date(year, month_number, 1)

    return None


def get_days_in_month(month_year_value):
    """Return the actual number of days for a month-year value."""

    row_date = parse_row_date(month_year_value)

    if row_date:
        return calendar.monthrange(
            row_date.year,
            row_date.month,
        )[1]

    return 31


def month_key_from_date(value):
    return value.strftime("%Y-%m")


def month_key_from_value(value):
    row_date = parse_row_date(value)

    if row_date:
        return row_date.strftime("%Y-%m")

    return None


def adjustment_key(month_key, employee_id):
    return f"{month_key}:{str(employee_id)}"


# ============================================================================
# SUPABASE FUNCTIONS
# ============================================================================

@st.cache_data(ttl=2)
def fetch_vw_attendance_ledger():
    """Fetch attendance ledger data."""

    endpoint = (
        f"{SUPABASE_URL}/rest/v1/vw_attendance_ledger"
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

        st.error(
            "Attendance ledger request failed with HTTP "
            f"{response.status_code}: {response.text}"
        )
        return []

    except requests.RequestException as error:
        st.error(f"Unable to connect to Supabase: {error}")
        return []


def update_db_payment_status(
    employee_id,
    month_year,
    new_status,
):
    """Update payment status in raw_attendance_feed."""

    endpoint = (
        f"{SUPABASE_URL}/rest/v1/raw_attendance_feed"
        "?employee_id=eq."
        f"{employee_id}"
        "&month_year=eq."
        f"{month_year}"
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

        return response.status_code in {200, 201, 204}

    except requests.RequestException:
        return False


# ============================================================================
# PDF GENERATION
# ============================================================================

def generate_ledger_pdf(dataframe):
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
        rightMargin=18,
        leftMargin=18,
        topMargin=25,
        bottomMargin=25,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "LedgerTitle",
        parent=styles["Heading1"],
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#1A365D"),
    )

    header_style = ParagraphStyle(
        "LedgerHeader",
        parent=styles["Normal"],
        fontSize=5.5,
        leading=7,
        textColor=colors.white,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
    )

    cell_style = ParagraphStyle(
        "LedgerCell",
        parent=styles["Normal"],
        fontSize=5,
        leading=6.5,
        textColor=colors.black,
        alignment=TA_CENTER,
    )

    story = [
        Paragraph(
            "Payroll & Attendance Ledger",
            title_style,
        ),
        Spacer(1, 8),
    ]

    headers = list(dataframe.columns)

    table_data = [
        [
            Paragraph(
                escape(str(column)),
                header_style,
            )
            for column in headers
        ]
    ]

    for _, row in dataframe.iterrows():
        table_row = []

        for column in headers:
            value = row[column]

            if pd.isna(value):
                value = ""

            if isinstance(value, float):
                value_text = f"{value:.2f}"
            else:
                value_text = str(value)

            table_row.append(
                Paragraph(
                    escape(value_text),
                    cell_style,
                )
            )

        table_data.append(table_row)

    available_width = 756
    column_count = len(headers)
    column_width = max(
        28,
        available_width / column_count,
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
                    3,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    3,
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

if not view_records_data:
    st.info(
        "📋 No records were found in vw_attendance_ledger."
    )
    st.stop()


# ============================================================================
# PAGE HEADER AND DATE FILTER
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

st.header("📋 Payroll & Attendance Workflow")

chosen_dates = st.date_input(
    "Select Payout Month:",
    value=(default_start, default_end),
    key="attendance_month_range_picker",
)

if isinstance(chosen_dates, (tuple, list)) and len(chosen_dates) == 2:
    start_cal, end_cal = chosen_dates
else:
    start_cal = default_start
    end_cal = default_end

selected_month_label = start_cal.strftime("%B %Y")
selected_month_key = month_key_from_date(start_cal)

selected_month_days = calendar.monthrange(
    start_cal.year,
    start_cal.month,
)[1]


# ============================================================================
# PAYROLL ADJUSTMENTS
# EXTRA EARNINGS AND ADVANCE PAYMENT
# ============================================================================

if "payroll_adjustments" not in st.session_state:
    st.session_state["payroll_adjustments"] = {}


adjustment_employee_options = {}

for item in view_records_data:
    item_month_key = month_key_from_value(
        item.get("month_year")
    )

    if item_month_key != selected_month_key:
        continue

    employee_id = str(
        item.get("employee_id") or "N/A"
    )

    employee_name = (
        item.get("employee_name")
        or "Unnamed"
    )

    adjustment_employee_options[employee_id] = (
        f"{employee_id} - {employee_name}"
    )


st.markdown("---")
st.header("💰 Payroll Adjustments")

st.caption(
    f"Extra earnings and advance payments for "
    f"{selected_month_label}"
)

if adjustment_employee_options:
    adjustment_employee_ids = sorted(
        adjustment_employee_options.keys()
    )

    selected_adjustment_employee = st.selectbox(
        "Select Employee:",
        options=adjustment_employee_ids,
        format_func=lambda employee_id: (
            adjustment_employee_options[employee_id]
        ),
        key="payroll_adjustment_employee",
    )

    current_adjustment_key = adjustment_key(
        selected_month_key,
        selected_adjustment_employee,
    )

    saved_adjustment = st.session_state[
        "payroll_adjustments"
    ].get(
        current_adjustment_key,
        {
            "entries": [],
            "advance_payment": 0.00,
            "total_extra_amount": 0.00,
        },
    )

    adjustment_col1, adjustment_col2 = st.columns(
        [2, 1]
    )

    saved_entries = saved_adjustment.get(
        "entries",
        [],
    )

    entry_rows = []

    for entry in saved_entries:
        entry_rows.append(
            {
                "Particular": entry.get(
                    "Particular",
                    "",
                ),
                "Quantity": safe_float(
                    entry.get(
                        "Quantity",
                        1.00,
                    )
                ),
                "Rate": safe_float(
                    entry.get(
                        "Rate",
                        0.00,
                    )
                ),
            }
        )

    # Display five rows initially.
    while len(entry_rows) < 5:
        entry_rows.append(
            {
                "Particular": "",
                "Quantity": 1.00,
                "Rate": 0.00,
            }
        )

    with adjustment_col1:
        st.subheader("1. Extra Earning")

        st.caption(
            "Add multiple entries. Each amount is "
            "Quantity × Rate."
        )

        extra_entries_df = st.data_editor(
            pd.DataFrame(entry_rows),
            hide_index=True,
            num_rows="dynamic",
            width="stretch",
            column_config={
                "Particular": st.column_config.TextColumn(
                    "1.a Particulars",
                    help=(
                        "Example: transport, special duty, "
                        "loading/unloading"
                    ),
                ),
                "Quantity": st.column_config.NumberColumn(
                    "1.b Quantity / Hours",
                    min_value=0.00,
                    step=0.50,
                    format="%.2f",
                ),
                "Rate": st.column_config.NumberColumn(
                    "1.c Rate",
                    min_value=0.00,
                    step=1.00,
                    format="₹%.2f",
                ),
            },
            key=(
                "extra_earning_entries_"
                f"{selected_month_key}_"
                f"{selected_adjustment_employee}"
            ),
        )

    with adjustment_col2:
        st.subheader("2. Advance Payment")

        st.caption(
            "This amount will be subtracted from "
            "the gross payout."
        )

        advance_payment = st.number_input(
            "2. Advance Payment Amount",
            min_value=0.00,
            value=safe_float(
                saved_adjustment.get(
                    "advance_payment",
                    0.00,
                )
            ),
            step=100.00,
            format="%.2f",
            key=(
                "advance_payment_"
                f"{selected_month_key}_"
                f"{selected_adjustment_employee}"
            ),
        )

    cleaned_entries = []
    breakdown_rows = []

    for _, entry in extra_entries_df.iterrows():
        particular = str(
            entry.get(
                "Particular",
                "",
            )
        ).strip()

        quantity = safe_float(
            entry.get(
                "Quantity",
                0.00,
            )
        )

        rate = safe_float(
            entry.get(
                "Rate",
                0.00,
            )
        )

        if not particular and quantity <= 0 and rate <= 0:
            continue

        extra_amount = round(
            quantity * rate,
            2,
        )

        cleaned_entries.append(
            {
                "Particular": particular,
                "Quantity": quantity,
                "Rate": rate,
                "Extra_Amount": extra_amount,
            }
        )

        breakdown_rows.append(
            {
                "Particular": particular or "Unnamed",
                "Quantity / Hours": quantity,
                "Rate": rate,
                "Extra Amount": extra_amount,
            }
        )

    total_extra_amount = round(
        sum(
            entry["Extra_Amount"]
            for entry in cleaned_entries
        ),
        2,
    )

    net_adjustment = round(
        total_extra_amount - advance_payment,
        2,
    )

    total_col1, total_col2, total_col3 = st.columns(3)

    with total_col1:
        st.metric(
            "1.d Total Extra Amount",
            money(total_extra_amount),
        )

    with total_col2:
        st.metric(
            "2. Advance Payment",
            money(advance_payment),
        )

    with total_col3:
        st.metric(
            "Net Adjustment",
            money(net_adjustment),
        )

    if breakdown_rows:
        st.markdown("#### Extra-Earning Breakdown")

        st.dataframe(
            pd.DataFrame(breakdown_rows),
            hide_index=True,
            width="stretch",
            column_config={
                "Quantity / Hours": st.column_config.NumberColumn(
                    format="%.2f",
                ),
                "Rate": st.column_config.NumberColumn(
                    format="₹%.2f",
                ),
                "Extra Amount": st.column_config.NumberColumn(
                    format="₹%.2f",
                ),
            },
        )

    if st.button(
        "💾 Save Payroll Adjustments",
        key=(
            "save_payroll_adjustments_"
            f"{selected_month_key}_"
            f"{selected_adjustment_employee}"
        ),
    ):
        st.session_state[
            "payroll_adjustments"
        ][current_adjustment_key] = {
            "entries": cleaned_entries,
            "advance_payment": round(
                advance_payment,
                2,
            ),
            "total_extra_amount": total_extra_amount,
        }

        st.success(
            "Payroll adjustments saved for "
            f"{selected_adjustment_employee}."
        )

        st.rerun()

else:
    st.info(
        "No employees are available for payroll "
        f"adjustments in {selected_month_label}."
    )


# ============================================================================
# EMPLOYEE FILTERS
# ============================================================================

filter_col1, filter_col2, filter_col3 = st.columns(3)

with filter_col1:
    search_employee_id = st.text_input(
        "Filter by Employee ID:",
        key="employee_id_filter",
    ).strip()

with filter_col2:
    search_employee_name = st.text_input(
        "Filter by Employee Name:",
        key="employee_name_filter",
    ).strip()

with filter_col3:
    status_filter = st.selectbox(
        "Filter by Employee Status:",
        [
            "All Statuses",
            "Active Only",
            "In-Active Only",
        ],
        key="employee_status_filter",
    )


# ============================================================================
# PAYROLL CALCULATION ENGINE
# ============================================================================

processed_rows = []

for item in view_records_data:
    month_year = item.get("month_year") or "N/A"
    row_date = parse_row_date(month_year)

    if row_date is not None:
        if not (start_cal <= row_date <= end_cal):
            continue

    employee_id = str(
        item.get("employee_id") or "N/A"
    )

    item_month_key = (
        row_date.strftime("%Y-%m")
        if row_date
        else selected_month_key
    )

    employee_adjustment = st.session_state[
        "payroll_adjustments"
    ].get(
        adjustment_key(
            item_month_key,
            employee_id,
        ),
        {
            "entries": [],
            "advance_payment": 0.00,
            "total_extra_amount": 0.00,
        },
    )

    total_extra_amount = safe_float(
        employee_adjustment.get(
            "total_extra_amount",
            0.00,
        )
    )

    advance_payment = safe_float(
        employee_adjustment.get(
            "advance_payment",
            0.00,
        )
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

    shift_hours = safe_float(
        item.get("shift_hours")
    )

    if shift_hours <= 0:
        shift_hours = 8.00

    employee_status = (
        item.get("employee_status")
        or "Active"
    )

    attendance_days = (
        item.get("attendance_days")
        or []
    )

    total_minutes_worked = round(
        total_hours_worked * 60.00,
        2,
    )

    month_days = get_days_in_month(month_year)

    actual_days_worked = round(
        total_hours_worked / shift_hours,
        2,
    )

    if (
        str(employee_status).upper() == "ACTIVE"
        and month_days > 0
        and shift_hours > 0
    ):
        daily_allocation_rate = (
            base_monthly_comp / month_days
        )

        unrounded_hourly_rate = (
            daily_allocation_rate / shift_hours
        )

        # Round upward to the nearest penny.
        hourly_rate = (
            math.ceil(
                unrounded_hourly_rate * 100
            )
            / 100.00
        )

        # Round upward to four decimal places.
        per_minute_rate = (
            math.ceil(
                (hourly_rate / 60.00) * 10000
            )
            / 10000.00
        )

        gross_payout = round(
            total_hours_worked * hourly_rate,
            2,
        )

    else:
        hourly_rate = 0.00
        per_minute_rate = 0.00
        gross_payout = 0.00

    final_payout = round(
        gross_payout
        + total_extra_amount
        - advance_payment,
        2,
    )

    row_dict = {
        "Month_Year": month_year,
        "EMP_ID": employee_id,
        "EMP_Name": (
            item.get("employee_name")
            or "Unnamed"
        ),
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
        "Start_Date": (
            item.get("start_date")
            or "N/A"
        ),
        "Last_Date": (
            item.get("last_day_of_work")
            or "N/A"
        ),
        "EMP_Status": employee_status,
        "Base_Monthly_Comp": base_monthly_comp,
        "Rate_Per_Hour": hourly_rate,
        "Rate_Per_Minute": per_minute_rate,
        "Gross_Payout": gross_payout,
        "Total_Extra_Amount": total_extra_amount,
        "Advance_Payment": advance_payment,
        "Final_Payout": final_payout,
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
            attendance_days
            and day_number - 1 < len(attendance_days)
        ):
            row_dict[day_column] = (
                attendance_days[day_number - 1]
            )
        else:
            row_dict[day_column] = ""

    processed_rows.append(row_dict)


df = pd.DataFrame(processed_rows)

if df.empty:
    st.warning(
        "⚠️ No attendance records match the selected month."
    )
    st.stop()


# ============================================================================
# FILTER DATA
# ============================================================================

filtered_df = df[
    df["DB_Show_Flag"] == True
].copy()

if search_employee_id:
    filtered_df = filtered_df[
        filtered_df["EMP_ID"]
        .astype(str)
        .str.contains(
            search_employee_id,
            case=False,
            na=False,
        )
    ]

if search_employee_name:
    filtered_df = filtered_df[
        filtered_df["EMP_Name"]
        .astype(str)
        .str.contains(
            search_employee_name,
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

if filtered_df.empty:
    st.warning(
        "⚠️ No ledger records match the selected filters."
    )
    st.stop()


# ============================================================================
# LEDGER TABLE
# ============================================================================

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
        "Total_Extra_Amount",
        "Advance_Payment",
        "Final_Payout",
        "Payment_Status",
        "Start_Date",
        "Last_Date",
        "EMP_Status",
    ]
)

validated_columns = [
    column
    for column in grid_columns_order
    if column in filtered_df.columns
]

render_df = filtered_df[
    validated_columns
].copy()


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
    "Over_Time": st.column_config.NumberColumn(
        "Extra Hrs",
        format="%.2f",
        disabled=True,
    ),
    "Less_Time": st.column_config.NumberColumn(
        "Short Hrs",
        format="%.2f",
        disabled=True,
    ),
    "Total_Hours": st.column_config.NumberColumn(
        "Total Hrs",
        format="%.2f",
        disabled=True,
    ),
    "Total_Minutes": st.column_config.NumberColumn(
        "Total Minutes",
        format="%.2f",
        disabled=True,
    ),
    "Total_Days": st.column_config.NumberColumn(
        "Raw Days Present",
        format="%.0f",
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
        "Hourly Rate",
        format="₹%.2f",
        disabled=True,
    ),
    "Rate_Per_Minute": st.column_config.NumberColumn(
        "Per Minute Rate",
        format="₹%.4f",
        disabled=True,
    ),
    "Gross_Payout": st.column_config.NumberColumn(
        "Gross Payout",
        format="₹%.2f",
        disabled=True,
    ),
    "Total_Extra_Amount": st.column_config.NumberColumn(
        "1.d Total Extra Amount",
        format="₹%.2f",
        disabled=True,
    ),
    "Advance_Payment": st.column_config.NumberColumn(
        "2. Advance Payment",
        format="₹%.2f",
        disabled=True,
    ),
    "Final_Payout": st.column_config.NumberColumn(
        "Final Payout",
        format="₹%.2f",
        disabled=True,
    ),
    "Payment_Status": st.column_config.SelectboxColumn(
        "Payment Status",
        options=[
            "Pending",
            "Done",
        ],
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

for day_column in all_day_columns:
    if day_column in validated_columns:
        column_config[day_column] = (
            st.column_config.TextColumn(
                day_column.replace("D", ""),
                disabled=True,
            )
        )


st.markdown("---")
st.subheader(
    f"Attendance Ledger — {selected_month_label}"
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

if edited_rows:
    for row_index_text, changes in edited_rows.items():
        if "Payment_Status" not in changes:
            continue

        row_index = int(row_index_text)

        if row_index >= len(render_df):
            continue

        target_employee = render_df.iloc[
            row_index
        ]["EMP_ID"]

        target_month = render_df.iloc[
            row_index
        ]["Month_Year"]

        new_status = changes["Payment_Status"]

        with st.spinner(
            f"Updating payment status for "
            f"{target_employee}..."
        ):
            update_successful = (
                update_db_payment_status(
                    target_employee,
                    target_month,
                    new_status,
                )
            )

        if update_successful:
            st.success(
                f"Payment status updated to "
                f"'{new_status}' for "
                f"Employee ID {target_employee}."
            )

            st.cache_data.clear()
            st.rerun()

        else:
            st.error(
                f"Unable to update payment status for "
                f"Employee ID {target_employee}."
            )


# ============================================================================
# EXPORTS
# ============================================================================

st.markdown("---")
st.header("📤 Payroll & Attendance Exports")

export_df = edited_df.copy()

export_col1, export_col2 = st.columns(2)


# ----------------------------------------------------------------------------
# CSV EXPORT
# ----------------------------------------------------------------------------

with export_col1:
    st.subheader("📊 CSV Export")

    csv_df = export_df.copy()

    for column in csv_df.columns:
        if (
            column.startswith("D")
            and column[1:].isdigit()
        ):
            csv_df[column] = csv_df[column].apply(
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
        label="⬇️ Download Ledger as CSV",
        data=csv_buffer.getvalue(),
        file_name=(
            "Historical_Attendance_Ledger_"
            f"{datetime.date.today()}.csv"
        ),
        mime="text/csv",
        key="ledger_csv_download",
    )


# ----------------------------------------------------------------------------
# PDF EXPORT
# ----------------------------------------------------------------------------

with export_col2:
    st.subheader("📄 PDF Export")

    available_pdf_columns = list(
        export_df.columns
    )

    default_pdf_columns = [
        column
        for column in [
            "Month_Year",
            "EMP_ID",
            "EMP_Name",
            "Total_Hours",
            "Actual_Days_Worked",
            "Base_Monthly_Comp",
            "Rate_Per_Hour",
            "Rate_Per_Minute",
            "Gross_Payout",
            "Total_Extra_Amount",
            "Advance_Payment",
            "Final_Payout",
            "Payment_Status",
            "EMP_Status",
        ]
        if column in available_pdf_columns
    ]

    selected_pdf_columns = st.multiselect(
        "Select PDF columns:",
        options=available_pdf_columns,
        default=default_pdf_columns,
        key="ledger_pdf_columns",
    )

    pdf_row_options = []
    pdf_row_lookup = {}

    for position, (_, row) in enumerate(
        export_df.iterrows()
    ):
        employee_id = row.get(
            "EMP_ID",
            "N/A",
        )

        employee_name = row.get(
            "EMP_Name",
            "Unnamed",
        )

        month_year = row.get(
            "Month_Year",
            "N/A",
        )

        label = (
            f"{position + 1}. "
            f"{employee_id} - "
            f"{employee_name} - "
            f"{month_year}"
        )

        pdf_row_options.append(label)
        pdf_row_lookup[label] = position

    selected_pdf_rows = st.multiselect(
        "Select PDF rows:",
        options=pdf_row_options,
        default=[],
        help=(
            "Leave empty to include all filtered rows."
        ),
        key="ledger_pdf_rows",
    )

    if selected_pdf_rows:
        selected_positions = [
            pdf_row_lookup[label]
            for label in selected_pdf_rows
        ]

        pdf_target_df = export_df.iloc[
            selected_positions
        ].copy()

    else:
        pdf_target_df = export_df.copy()

    if selected_pdf_columns:
        pdf_target_df = pdf_target_df[
            selected_pdf_columns
        ].copy()
    else:
        pdf_target_df = pd.DataFrame()

    if pdf_target_df.empty:
        st.warning(
            "Select at least one column and one "
            "available row for the PDF."
        )

        pdf_data = b""

    else:
        pdf_data = generate_ledger_pdf(
            pdf_target_df
        )

    st.download_button(
        label="⬇️ Download Ledger as PDF",
        data=pdf_data,
        file_name=(
            "Historical_Attendance_Ledger_"
            f"{datetime.date.today()}.pdf"
        ),
        mime="application/pdf",
        key="ledger_pdf_download",
        disabled=not bool(pdf_data),
    )


# ============================================================================
# CALCULATION FORMULAS
# ============================================================================

st.markdown("---")
st.header("🧮 Calculation Formulas")

formula_col1, formula_col2, formula_col3 = st.columns(3)


# ----------------------------------------------------------------------------
# HOURLY RATE FORMULA
# ----------------------------------------------------------------------------

with formula_col1:
    st.markdown("**1. Hourly Rate Calculation**")

    example_base_monthly_comp = 25000.00
    example_shift_hours = 8.00

    example_daily_allocation_rate = (
        example_base_monthly_comp
        / selected_month_days
    )

    example_unrounded_hourly_rate = (
        example_daily_allocation_rate
        / example_shift_hours
    )

    example_hourly_rate = (
        math.ceil(
            example_unrounded_hourly_rate * 100
        )
        / 100.00
    )

    example_per_minute_rate = (
        math.ceil(
            (example_hourly_rate / 60.00) * 10000
        )
        / 10000.00
    )

    st.latex(
        r"\mathrm{Daily\ Allocation\ Rate}"
        r" = \frac{\mathrm{Base\ Monthly\ Compensation}}"
        r"{\mathrm{Days\ in\ Selected\ Month}}"
    )

    st.latex(
        r"\mathrm{Rate\ Per\ Hour}"
        r" = \left\lceil"
        r"\frac{\mathrm{Daily\ Allocation\ Rate}}"
        r"{\mathrm{Shift\ Hours}}"
        r"\times 100\right\rceil \div 100"
    )

    st.caption(
        "The hourly rate is rounded upward to the "
        "nearest penny."
    )

    with st.expander(
        f"🔍 View Hourly Rate Example for "
        f"{selected_month_label}"
    ):
        st.markdown(
            f"""
            #### Hourly Rate Example

            - **Selected Payout Month:** {selected_month_label}
            - **Days in Month:** {selected_month_days}
            - **Base Monthly Compensation:** {money(example_base_monthly_comp)}
            - **Configured Shift:** {example_shift_hours:.0f} hours
            """
        )

        st.latex(
            rf"\frac{{{money(example_base_monthly_comp)}}}"
            rf"{{{selected_month_days}}}"
            rf" = {money(example_daily_all
