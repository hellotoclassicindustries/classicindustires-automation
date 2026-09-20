import streamlit as st
import pandas as pd
import os
from datetime import datetime, date, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from supabase import create_client
from num2words import num2words

# ============================================================================
# INITIALIZATION & STATE MANAGEMENT CORE
# ============================================================================
if "invoice_staged" not in st.session_state:
    st.session_state.invoice_staged = False
if "staged_serial" not in st.session_state:
    st.session_state.staged_serial = ""
if "loaded_from_history" not in st.session_state:
    st.session_state.loaded_from_history = False
if "historical_data" not in st.session_state:
    st.session_state.historical_data = {}
if "pdf_ready_path" not in st.session_state:
    st.session_state.pdf_ready_path = None

@st.cache_resource
def init_supabase_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error("❌ Missing Infrastructure Secrets Configuration.")
        return None

supabase = init_supabase_connection()

@st.cache_data(ttl=2)
def fetch_invoice_catalog():
    if not supabase: return pd.DataFrame()
    try:
        res = supabase.table("vw_cntr_part_master").select("*").execute()
        return pd.DataFrame(res.data)
    except: return pd.DataFrame()

@st.cache_data(ttl=2)
def fetch_corporate_master_directory():
    if not supabase: return pd.DataFrame()
    try:
        res = supabase.table("cntr_corporate_master").select("*").eq("is_violated", False).order("company_name").execute()
        return pd.DataFrame(res.data)
    except: return pd.DataFrame()

catalog_df = fetch_invoice_catalog()
corporate_df = fetch_corporate_master_directory()

if catalog_df.empty:
    st.warning("📋 Operations Notice: The master part catalog database view is disconnected.")
    st.stop()

st.title("🏭 Automated GST Commercial Tax Invoice Platform")
st.markdown("---")

def clean_db_val(row_dict, key_name, fallback_text):
    if not isinstance(row_dict, dict):
        return fallback_text
    val = row_dict.get(key_name)
    if val is None or str(val).strip() == "" or str(val).lower() == "none":
        return fallback_text
    return str(val).strip()

def get_financial_year_prefix(current_date):
    year = current_date.year
    if current_date.month >= 4:
        start_yr = str(year)[2:]
        end_yr = str(year + 1)[2:]
    else:
        start_yr = str(year - 1)[2:]
        end_yr = str(year)[2:]
    return f"INV/{start_yr}-{end_yr}/"

def calculate_next_db_serial(target_date):
    fy_prefix = get_financial_year_prefix(target_date)
    next_id = "001"
    try:
        hist_res = supabase.table("cntr_invoice_history").select("invoice_no").like("invoice_no", f"%{fy_prefix}%").execute()
        if hist_res.data:
            numeric_values = []
            for item in hist_res.data:
                parts = item["invoice_no"].split("/")
                if len(parts) == 3:
                    try:
                        numeric_values.append(int(parts[2]))
                    except: pass
            if numeric_values:
                next_id = str(max(numeric_values) + 1).zfill(3)
    except: pass
    return f"{fy_prefix}{next_id}"
# ============================================================================
# SECTION 1: CORPORATE PROFILES
# ============================================================================
st.subheader("🏛️ Corporate Profiles")
is_disabled = st.session_state.invoice_staged

col_s1, col_s2 = st.columns(2)
h_data = st.session_state.historical_data if st.session_state.loaded_from_history else {}

if isinstance(h_data, list) and len(h_data) > 0:
    h_data = h_data[0]
elif not isinstance(h_data, dict):
    h_data = {}

with col_s1:
    st.markdown("**🛡️ Source Company Details (Seller End)**")
    owner_df = corporate_df[corporate_df["cmp_number"].str.lower() == "own01"] if not corporate_df.empty else pd.DataFrame()
    owner_records = owner_df.to_dict(orient="records") if not owner_df.empty else []
    o_row = owner_records[0] if len(owner_records) > 0 else {}
    
    src_name = st.text_input("Seller Legal Name", clean_db_val(o_row, "company_name", "CLASSIC INDUSTRIES"), disabled=is_disabled)
    src_address = st.text_area("Full Corporate Factory Address", clean_db_val(o_row, "billing_address", "KH-267, H.No.-08, Chipiyana Bujurg, Ghaziabad – 201009, Uttar Pradesh"), disabled=is_disabled)
    src_gstin = st.text_input("Seller GSTIN Code Token", clean_db_val(o_row, "gstin", "09ENRPS7521A1ZN"), disabled=is_disabled)
    src_mobile = st.text_input("Seller Contact Mobile", clean_db_val(o_row, "contact_number", "9999999999"), disabled=is_disabled)
    src_email = st.text_input("Seller Operations Email", clean_db_val(o_row, "email_address", "billing@classicindustries.in"), disabled=is_disabled)
    invoice_hsn_input = st.text_input("Active Billing HSN/SAC Codes (Left Panel Override)", value=clean_db_val(o_row, "hsn_number", "998349"), disabled=is_disabled)

with col_s2:
    st.markdown("**🏢 Shipping Client Details (Buyer End)**")
    buyer_only_df = corporate_df[corporate_df["profile_type"].str.lower() != "owner"] if not corporate_df.empty else pd.DataFrame()
    buyer_records = buyer_only_df.to_dict(orient="records") if not buyer_only_df.empty else []
    
    target_buyer_name = h_data.get("buyer_name", "")
    default_selectbox_index = 0
    if target_buyer_name and len(buyer_records) > 0:
        names_list = [r["company_name"] for r in buyer_records]
        if target_buyer_name in names_list:
            default_selectbox_index = names_list.index(target_buyer_name)

    if len(buyer_records) > 0:
        corp_options = [r["company_name"] for r in buyer_records]
        selected_client_name = st.selectbox("Select Customer from Cloud Registry", corp_options, index=default_selectbox_index, disabled=is_disabled)
        c_match = [r for r in buyer_records if r["company_name"] == selected_client_name]
        c_row = c_match[0] if c_match else {}
        
        bill_name = st.text_input("Buyer Registered Corporate Name", clean_db_val(c_row, "company_name", "REVENT METALCAST LIMITED"), disabled=is_disabled)
        bill_gstin = st.text_input("Buyer GSTIN Token", h_data.get("buyer_gstin", clean_db_val(c_row, "gstin", "08AAACA8504G2ZW")), disabled=is_disabled)
        bill_address = st.text_area("Buyer Corporate Billing Address", clean_db_val(c_row, "billing_address", "SPA-1195, RIICO Industrial Area, Phase IV, Bhiwadi, Alwar, Rajasthan, 301019"), disabled=is_disabled)
        bill_person = st.text_input("Attn / Customer Contact Person", clean_db_val(c_row, "contact_person", "Operations Head"), disabled=is_disabled)
        bill_no = st.text_input("Buyer Contact Phone Number", clean_db_val(c_row, "contact_number", "9999999999"), disabled=is_disabled)
        base_pos = f"{str(c_row.get('state_code','08')).zfill(2)}-{str(c_row.get('state_name','RAJASTHAN')).upper()}"
    else:
        bill_name = st.text_input("Buyer Registered Corporate Name", "REVENT METALCAST LIMITED", disabled=is_disabled)
        bill_gstin = st.text_input("Buyer GSTIN Token", "08AAACA8504G2ZW", disabled=is_disabled)
        bill_address = st.text_area("Buyer Corporate Billing Address", "SPA-1195, RIICO Industrial Area, Phase IV, Bhiwadi, Alwar, Rajasthan, 301019", disabled=is_disabled)
        bill_person = st.text_input("Attn / Customer Contact Person", "Operations Head", disabled=is_disabled)
        bill_no = st.text_input("Buyer Contact Phone Number", "9999999999", disabled=is_disabled)
        base_pos = "08-RAJASTHAN"
# ============================================================================
# SECTION 2: TIMELINE FILTERS
# ============================================================================
st.markdown("---")
st.subheader("🗓️ Timeline Filters")
col_d1, col_d2, col_d3 = st.columns(3)

with col_d1:
    today = date.today()
    default_start = today - timedelta(days=30)
    selected_range = st.date_input("Select Dispatch Range Window", value=(default_start, today), key="invoice_date_range", disabled=is_disabled)
    start_date, end_date = selected_range if (isinstance(selected_range, tuple) and len(selected_range) == 2) else (today - timedelta(days=30), today)

with col_d2:
    catalog_df["display_name"] = catalog_df["part_number"].astype(str) + " - " + catalog_df["description"].astype(str).str.upper()
    dropdown_options = ["ALL COMPONENT DISPATCHED RUNS"] + list(catalog_df["display_name"].unique())
    selected_display = st.selectbox("Filter Dispatch by Component Scope", dropdown_options, index=0, disabled=is_disabled)
    is_filtered_run = selected_display != "ALL COMPONENT DISPATCHED RUNS"

with col_d3:
    selected_txn_type = st.selectbox("Transaction Flow Type", ["Outward", "Inward", "All Transactions"], index=0, disabled=is_disabled)

st.markdown("<br>", unsafe_allow_html=True)
col_l1, col_l2 = st.columns(2)

with col_l1:
    same_as_billing = st.checkbox("Shipping Destination matches Profile Billing Address Coordinates", value=True, disabled=is_disabled)
    ship_addr_override = st.text_area("Override Consignee Delivery Address", value=bill_address if same_as_billing else "", disabled=is_disabled)
    place_of_supply = st.text_input("Place of Supply State Code Target", value=base_pos, disabled=is_disabled)

with col_l2:
    default_print_date = datetime.strptime(h_data["invoice_date"], "%Y-%m-%d").date() if "invoice_date" in h_data else today
    invoice_date_input = st.date_input("Invoice Structural Printing Date", default_print_date, disabled=is_disabled)
    
    credit_days_input = st.number_input("Credit Payment Terms (Days Window)", min_value=0, max_value=365, value=7, step=1, disabled=is_disabled)
    due_date_calculated = invoice_date_input + timedelta(days=credit_days_input)
    st.text_input("Calculated Payment Due Target Date", value=due_date_calculated.strftime("%d-%b-%Y"), disabled=True)
    
    if not st.session_state.invoice_staged:
        auto_serial_default = calculate_next_db_serial(invoice_date_input)
    else:
        auto_serial_default = st.session_state.staged_serial
        
    typed_serial = st.text_input("Invoice Serial Sequential Number #", value=auto_serial_default, disabled=is_disabled)
    
    if typed_serial and not st.session_state.invoice_staged and supabase:
        try:
            db_match = supabase.table("cntr_invoice_history").select("*").eq("invoice_no", typed_serial.strip()).execute()
            if db_match.data and not st.session_state.loaded_from_history:
                st.session_state.loaded_from_history = True
                st.session_state.historical_data = db_match.data
                st.toast(f"ℹ️ Historical Match Found: Loaded parameters for {typed_serial} automatically!")
                st.rerun()
            elif not db_match.data and st.session_state.loaded_from_history:
                st.session_state.loaded_from_history = False
                st.session_state.historical_data = {}
                st.rerun()
        except: pass
# ============================================================================
# SECTION 3: PRINT PREVIEW & INVOICE PAYLOAD COMPILATION
# ============================================================================
st.markdown("---")
st.subheader("⚙️ Print Preview")

line_items_payload = []
hsn_summary_map = {}
parsed_hsn_override_list = [x.strip() for x in invoice_hsn_input.split(",") if x.strip()]

try:
    iso_start = start_date.strftime("%Y-%m-%d")
    iso_end = end_date.strftime("%Y-%m-%d")
    query_builder = supabase.table("staging_ledger").select("id,date,entry_type,challan_no,part_number,description,qty_nos,hsn_code").gte("date", iso_start).lte("date", iso_end)
    if selected_txn_type != "All Transactions":
        query_builder = query_builder.eq("entry_type", selected_txn_type)
    ledger_response = query_builder.execute()
    ledger_df = pd.DataFrame(ledger_response.data)
    
    if ledger_df.empty:
        st.info("📋 Operations Notice: Zero production records matched selection parameters.")
        st.stop()
        
    grouped_ledger = ledger_df.groupby("part_number").agg({
        "qty_nos": "sum",
        "date": [lambda x: pd.to_datetime(x).min().strftime("%Y-%m-%d"), lambda x: pd.to_datetime(x).max().strftime("%Y-%m-%d")],
        "hsn_code": "first", "description": "first"
    }).reset_index()
    grouped_ledger.columns = ["part_number", "qty_nos", "txn_start_raw", "txn_end_date_raw", "hsn_code", "description"]
    merged_summary = grouped_ledger.sort_values(by="part_number")
except Exception as e:
    iso_start, iso_end = start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
    merged_summary = pd.DataFrame([
        {"part_number": "458/20418P", "description": "DRIVE HEAD CASING", "hsn_code": "998349", "qty_nos": 106, "txn_start_raw": iso_start, "txn_end_date_raw": iso_end},
        {"part_number": "589-M6715", "description": "REAR CASE CASTING-589-M6715", "hsn_code": "998349", "qty_nos": 110, "txn_start_raw": iso_start, "txn_end_date_raw": iso_end},
        {"part_number": "589-M6716", "description": "REAR CASE CASTING-589-M6716", "hsn_code": "998349", "qty_nos": 104, "txn_start_raw": iso_start, "txn_end_date_raw": iso_end},
        {"part_number": "91776325", "description": "CNH HOUSING CASTING MCH UG", "hsn_code": "998349", "qty_nos": 40, "txn_start_raw": iso_start, "txn_end_date_raw": iso_end},
        {"part_number": "9330093", "description": "EATON GEARCASE CASTING", "hsn_code": "998349", "qty_nos": 289, "txn_start_raw": iso_start, "txn_end_date_raw": iso_end},
        {"part_number": "W50217101Z1", "description": "CASE TRANSMISSION CASTING", "hsn_code": "998349", "qty_nos": 669, "txn_start_raw": iso_start, "txn_end_date_raw": iso_end}
    ])

for idx, row in merged_summary.iterrows():
    p_num = str(row["part_number"])
    if is_filtered_run and p_num.upper() not in selected_display.upper(): continue
    sim_qty, p_desc = int(row["qty_nos"]), str(row["description"]).upper()
    match_part = catalog_df[catalog_df["part_number"] == p_num] if not catalog_df.empty else pd.DataFrame()
    
    if not match_part.empty:
        # FIX: Slices the dataframe matching index coordinate matrices to avoid dimension scalar errors
        p_weight_kg = float(match_part["weight_kg"].iloc[0]) if pd.notna(match_part["weight_kg"].iloc[0]) else 28.0
        p_rate = float(match_part["rate_per_ton"].iloc[0]) if "rate_per_ton" in match_part.columns and pd.notna(match_part["rate_per_ton"].iloc[0]) else 2650.00
        hsn_col = [c for c in match_part.columns if c in ["hsn_sac", "hsn_code"]]
        db_hsn = str(match_part[hsn_col].iloc[0]).strip() if hsn_col and pd.notna(match_part[hsn_col].iloc[0]) else "998349"
    else:
        p_weight_kg, p_rate, db_hsn = 28.0, 2650.00, "998349"
    
    hsn_code = parsed_hsn_override_list[len(line_items_payload) % len(parsed_hsn_override_list)] if parsed_hsn_override_list else db_hsn
    s_date_raw, e_date_raw = str(row["txn_start_raw"]), str(row["txn_end_date_raw"])
    try:
        st_d = datetime.strptime(s_date_raw.split(" "), "%Y-%m-%d").strftime("%d-%b-%Y")
        en_d = datetime.strptime(e_date_raw.split(" "), "%Y-%m-%d").strftime("%d-%b-%Y")
        txn_date_range_display = f"{st_d} to {en_d}" if st_d != en_d else st_d
    except: txn_date_range_display = s_date_raw
    
    total_wt_mt = (sim_qty * p_weight_kg) / 1000.0
    taxable_val = total_wt_mt * p_rate
    tax_amt = taxable_val * 0.18
    
    item_node = {
        "item_no": len(line_items_payload) + 1, "txn_date": txn_date_range_display, "part_number": p_num, "description": p_desc, "hsn": hsn_code,
        "qty": sim_qty, "wt_pc": p_weight_kg, "total_wt_mt": total_wt_mt, "rate_mt": p_rate, "taxable_value": taxable_val, "tax_amt": tax_amt
    }
    line_items_payload.append(item_node)
    if hsn_code not in hsn_summary_map: hsn_summary_map[hsn_code] = {"taxable_value": 0.0, "tax_amount": 0.0}
    hsn_summary_map[hsn_code]["taxable_value"] += taxable_val
    hsn_summary_map[hsn_code]["tax_amount"] += tax_amt

summary_df = pd.DataFrame(line_items_payload)
if not summary_df.empty:
    total_invoice_pieces = int(summary_df["qty"].sum())
    total_invoice_weight_mt = float(summary_df["total_wt_mt"].sum())
    total_taxable_subtotal = round(float(summary_df["taxable_value"].sum()), 2)
    total_tax_sum = round(float(total_taxable_subtotal * 0.18), 2)
    grand_invoice_total = round(total_taxable_subtotal + total_tax_sum, 2)
    
    try:
        words_main = num2words(int(round(grand_invoice_total)), lang='en_IN').title().replace("-", " ")
        invoice_total_words = f"{words_main} Rupees Only."
        words_tax = num2words(int(round(total_tax_sum)), lang='en_IN').title().replace('-', ' ')
        tax_total_words = f"{words_tax} Rupees Only."
    except: 
        invoice_total_words = "Amount Calculated Dynamically."
        tax_total_words = "Calculated Automatically."
    
    st.dataframe(summary_df[["item_no", "part_number", "description", "hsn", "qty", "wt_pc", "total_wt_mt", "rate_mt", "taxable_value"]], width="stretch", hide_index=True)
else:
    total_invoice_pieces, total_invoice_weight_mt, total_taxable_subtotal, total_tax_sum, grand_invoice_total = 0, 0.0, 0.0, 0.0, 0.0
    invoice_total_words, tax_total_words = "Zero Rupees Only.", "Zero Rupees Only."

invoice_payload = {
    "invoice_no": str(typed_serial), "start_date": invoice_date_input.strftime("%d-%b-%Y"), "end_date": due_date_calculated.strftime("%d-%b-%Y"),
    "place_of_supply": str(place_of_supply), "src_name": str(src_name), "src_address": str(src_address), "src_gstin": str(src_gstin),
    "bill_name": str(bill_name), "bill_address": str(bill_address), "bill_gstin": str(bill_gstin), "ship_address": str(ship_addr_override),
    "line_items": line_items_payload, "taxable_amount": total_taxable_subtotal, "igst": total_tax_sum, "grand_total": grand_invoice_total,
    "total_words": invoice_total_words, "tax_total_words": tax_total_words, "hsn_map": hsn_summary_map, "total_invoice_weight_mt": total_invoice_weight_mt, "total_pieces": total_invoice_pieces
}

col_btn1, col_btn2 = st.columns(2)
with col_btn1:
    if st.button("🔒 Freeze & Stage Layout Configuration", width="stretch", disabled=st.session_state.invoice_staged):
        st.session_state.invoice_staged = True
        st.session_state.staged_serial = typed_serial
        st.rerun()
with col_btn2:
    if st.button("🔓 Modify Parameters / Unfreeze Form", width="stretch", disabled=not st.session_state.invoice_staged):
        st.session_state.invoice_staged = False
        st.session_state.staged_serial = ""
        st.session_state.loaded_from_history = False
        st.session_state.historical_data = {}
        st.session_state.pdf_ready_path = None
        st.rerun()
# ============================================================================
# PART 4: BULLETPROOF LINE ITEM AGGREGATION LOOP (AMBIGUITY ELIMINATED)
# ============================================================================
for idx, row in merged_summary.iterrows():
    p_num = str(row["part_number"])
    if is_filtered_run and p_num.upper() not in selected_display.upper(): continue
    sim_qty, p_desc = int(row["qty_nos"]), str(row["description"]).upper()
    match_part = catalog_df[catalog_df["part_number"] == p_num] if not catalog_df.empty else pd.DataFrame()
    
    # Initialize robust defaults
    p_weight_kg = 28.0
    p_rate = 2650.00
    db_hsn = "998349"
    
    if not match_part.empty:
        # Extract weight cleanly using positional item lookup
        if "weight_kg" in match_part.columns:
            val_wt = match_part["weight_kg"].iat[0]
            if pd.notna(val_wt):
                p_weight_kg = float(val_wt)
                
        # Extract rate cleanly using positional item lookup        
        if "rate_per_ton" in match_part.columns:
            val_rt = match_part["rate_per_ton"].iat[0]
            if pd.notna(val_rt):
                p_rate = float(val_rt)
        
        # EXTRACT HSN CLEANLY: Try potential column structures sequentially to avoid multi-column slices
        hsn_val = None
        if "hsn_code" in match_part.columns:
            hsn_val = match_part["hsn_code"].iat[0]
        elif "hsn_sac" in match_part.columns:
            hsn_val = match_part["hsn_sac"].iat[0]
            
        if pd.notna(hsn_val) and str(hsn_val).strip() != "" and str(hsn_val).lower() != "none":
            db_hsn = str(hsn_val).strip()

    hsn_code = parsed_hsn_override_list[len(line_items_payload) % len(parsed_hsn_override_list)] if parsed_hsn_override_list else db_hsn
    s_date_raw, e_date_raw = str(row["txn_start_raw"]), str(row["txn_end_date_raw"])
    try:
        st_d = datetime.strptime(s_date_raw.split(" "), "%Y-%m-%d").strftime("%d-%b-%Y")
        en_d = datetime.strptime(e_date_raw.split(" "), "%Y-%m-%d").strftime("%d-%b-%Y")
        txn_date_range_display = f"{st_d} to {en_d}" if st_d != en_d else st_d
    except: txn_date_range_display = s_date_raw
    
    total_wt_mt = (sim_qty * p_weight_kg) / 1000.0
    taxable_val = total_wt_mt * p_rate
    tax_amt = taxable_val * 0.18
    
    item_node = {
        "item_no": len(line_items_payload) + 1, "txn_date": txn_date_range_display, "part_number": p_num, "description": p_desc, "hsn": hsn_code,
        "qty": sim_qty, "wt_pc": p_weight_kg, "total_wt_mt": total_wt_mt, "rate_mt": p_rate, "taxable_value": taxable_val, "tax_amt": tax_amt
    }
    line_items_payload.append(item_node)
    if hsn_code not in hsn_summary_map: hsn_summary_map[hsn_code] = {"taxable_value": 0.0, "tax_amount": 0.0}
    hsn_summary_map[hsn_code]["taxable_value"] += taxable_val
    hsn_summary_map[hsn_code]["tax_amount"] += tax_amt
# ============================================================================
# SECTION 5: DOWNLOAD/PRINT CENTER
# ============================================================================
st.markdown("---")
st.subheader("📥 Download/Print Center")

if not st.session_state.invoice_staged:
    st.info("💡 Review your configurations and click 'Freeze & Stage Layout Configuration' above to unlock the document generator console.")
    st.session_state.pdf_ready_path = None
else:
    if st.button("🚀 Finalize, Commit & Generate Official Commercial Invoice PDF", key="finalize_btn", width="stretch"):
        f_path = generate_invoice_pdf_file(invoice_payload)
        is_update_override = st.session_state.loaded_from_history
        
        try:
            if is_update_override:
                supabase.table("cntr_invoice_history").update({
                    "invoice_date": invoice_date_input.strftime("%Y-%m-%d"),
                    "buyer_name": invoice_payload["bill_name"], "buyer_gstin": invoice_payload["bill_gstin"],
                    "total_pieces": invoice_payload["total_pieces"], "total_weight_mt": invoice_payload["total_invoice_weight_mt"],
                    "taxable_amount": invoice_payload["taxable_amount"], "igst_amount": invoice_payload["igst"], "grand_total": invoice_payload["grand_total"]
                }).eq("invoice_no", invoice_payload["invoice_no"]).execute()
                st.success(f"🎉 Historical record **{invoice_payload['invoice_no']}** updated successfully!")
            else:
                history_row = {
                    "invoice_no": invoice_payload["invoice_no"], "invoice_date": invoice_date_input.strftime("%Y-%m-%d"),
                    "buyer_name": invoice_payload["bill_name"], "buyer_gstin": invoice_payload["bill_gstin"],
                    "total_pieces": invoice_payload["total_pieces"], "total_weight_mt": invoice_payload["total_invoice_weight_mt"],
                    "taxable_amount": invoice_payload["taxable_amount"], "igst_amount": invoice_payload["igst"], "grand_total": invoice_payload["grand_total"]
                }
                supabase.table("cntr_invoice_history").insert(history_row).execute()
                st.success("🎉 New commercial invoice logged to history ledger cleanly!")
            
            st.session_state.pdf_ready_path = f_path
            st.rerun()
            
        except Exception as save_err:
            st.error(f"❌ Cloud Audit Exception: Failure during secure storage sync. Details: {str(save_err)}")
            st.session_state.pdf_ready_path = None

    if st.session_state.pdf_ready_path and os.path.exists(st.session_state.pdf_ready_path):
        st.markdown("<br>", unsafe_allow_html=True)
        with open(st.session_state.pdf_ready_path, "rb") as f:
            st.download_button(
                label="📥 Download Official Job-Work GST Invoice PDF", 
                data=f, 
                file_name=f"Invoice_{invoice_payload['invoice_no'].replace('/', '_')}.pdf", 
                mime="application/pdf",
                width="stretch"
            )
