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
# INITIALIZATION & SECURE DATABASE GATEWAYS
# ============================================================================
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

# Helper utility to cleanly extract fields without dropping into string conversion crashes
def clean_db_val(row_dict, key_name, fallback_text):
    val = row_dict.get(key_name)
    if val is None or str(val).strip() == "" or str(val).lower() == "none":
        return fallback_text
    return str(val).strip()
# ============================================================================
# BLOCK 1: SOURCE COMPANY DETAILS (LEFT) & SHIPPING CLIENT DETAILS (RIGHT)
# ============================================================================
st.subheader("🏛️ Block 1: Corporate Entity Address Profiles")
col_s1, col_s2 = st.columns(2)

with col_s1:
    st.markdown("**🛡️ Source Company Details (Seller End)**")
    owner_df = corporate_df[corporate_df["cmp_number"].str.lower() == "own01"] if not corporate_df.empty else pd.DataFrame()
    owner_records = owner_df.to_dict(orient="records") if not owner_df.empty else []
    
    # 🔍 ARRAY EXTRACTION FIX: Extract the actual dictionary item index out of the records list
    o_row = owner_records[0] if len(owner_records) > 0 else {}
    
    src_name = st.text_input("Seller Legal Name", clean_db_val(o_row, "company_name", "CLASSIC INDUSTRIES"))
    src_address = st.text_area("Full Corporate Factory Address", clean_db_val(o_row, "billing_address", "KH-267, H.No.-08, Chipiyana Bujurg, Ghaziabad – 201009, Uttar Pradesh"))
    src_gstin = st.text_input("Seller GSTIN Code Token", clean_db_val(o_row, "gstin", "09ENRPS7521A1ZN"))
    src_mobile = st.text_input("Seller Contact Mobile", clean_db_val(o_row, "contact_number", "9999999999"))
    src_email = st.text_input("Seller Operations Email", clean_db_val(o_row, "email_address", "billing@classicindustries.in"))
    invoice_hsn_input = st.text_input("Active Billing HSN/SAC Codes (Left Panel Override)", value=clean_db_val(o_row, "hsn_number", "998349"))

with col_s2:
    st.markdown("**🏢 Shipping Client Details (Buyer End)**")
    buyer_only_df = corporate_df[corporate_df["profile_type"].str.lower() != "owner"] if not corporate_df.empty else pd.DataFrame()
    buyer_records = buyer_only_df.to_dict(orient="records") if not buyer_only_df.empty else []
    
    if len(buyer_records) > 0:
        corp_options = [r["company_name"] for r in buyer_records]
        selected_client_name = st.selectbox("Select Customer from Cloud Registry", corp_options)
        
        c_match = [r for r in buyer_records if r["company_name"] == selected_client_name]
        c_row = c_match[0] if c_match else {}
        
        bill_name = st.text_input("Buyer Registered Corporate Name", clean_db_val(c_row, "company_name", "REVENT METALCAST LIMITED"))
        bill_gstin = st.text_input("Buyer GSTIN Token", clean_db_val(c_row, "gstin", "08AAACA8504G2ZW"))
        bill_address = st.text_area("Buyer Corporate Billing Address", clean_db_val(c_row, "billing_address", "SPA-1195, RIICO Industrial Area, Phase IV, Bhiwadi, Alwar, Rajasthan, 301019"))
        bill_person = st.text_input("Attn / Customer Contact Person", clean_db_val(c_row, "contact_person", "Operations Head"))
        bill_no = st.text_input("Buyer Contact Phone Number", clean_db_val(c_row, "contact_number", "9999999999"))
        
        st_code = str(c_row.get('state_code', '08')).zfill(2)
        st_name = str(c_row.get('state_name', 'RAJASTHAN')).upper()
        base_pos = f"{st_code}-{st_name}"
    else:
        bill_name = st.text_input("Buyer Registered Corporate Name", "REVENT METALCAST LIMITED")
        bill_gstin = st.text_input("Buyer GSTIN Token", "08AAACA8504G2ZW")
        bill_address = st.text_area("Buyer Corporate Billing Address", "SPA-1195, RIICO Industrial Area, Phase IV, Bhiwadi, Alwar, Rajasthan, 301019")
        bill_person = st.text_input("Attn / Customer Contact Person", "Operations Head")
        bill_no = st.text_input("Buyer Contact Phone Number", "9999999999")
        base_pos = "08-RAJASTHAN"

# ============================================================================
# BLOCK 2: FLEXIBLE DATE RANGE & TRANSACTION METRIC FILTERS
# ============================================================================
st.markdown("---")
st.subheader("🗓️ TimelineFilters")
col_d1, col_d2, col_d3 = st.columns(3)

with col_d1:
    today = date.today()
    default_start = today - timedelta(days=30)
    selected_range = st.date_input("Select Dispatch Range Window", value=(default_start, today), key="invoice_date_range")
    start_date, end_date = selected_range if (isinstance(selected_range, tuple) and len(selected_range) == 2) else (today - timedelta(days=30), today)

with col_d2:
    catalog_df["display_name"] = catalog_df["part_number"].astype(str) + " - " + catalog_df["description"].astype(str).str.upper()
    dropdown_options = ["ALL COMPONENT DISPATCHED RUNS"] + list(catalog_df["display_name"].unique())
    selected_display = st.selectbox("Filter Dispatch by Component Scope", dropdown_options, index=0)
    is_filtered_run = selected_display != "ALL COMPONENT DISPATCHED RUNS"

with col_d3:
    selected_txn_type = st.selectbox("Transaction Flow Type", ["Outward", "Inward", "All Transactions"], index=0)

st.markdown("<br>", unsafe_allow_html=True)
col_l1, col_l2 = st.columns(2)

with col_l1:
    same_as_billing = st.checkbox("Shipping Destination matches Profile Billing Address Coordinates", value=True)
    ship_addr_override = st.text_area("Override Consignee Delivery Address", value=bill_address) if same_as_billing else st.text_area("Override Consignee Delivery Address", value="")
    place_of_supply = st.text_input("Place of Supply State Code Target", value=base_pos)

with col_l2:
    invoice_date_input = st.date_input("Invoice Structural Printing Date", today)
    due_date_input = st.date_input("Payment Due Target Date", today + timedelta(days=30))
    invoice_serial_no = st.text_input("Invoice Serial Sequential Number #", f"INV-{datetime.now().strftime('%M%S')}")
# ============================================================================
# BLOCK 3: LIVE INVOICE PREVIEW GRID (FILTERED FROM STAGING_LEDGER)
# ============================================================================
st.markdown("---")
st.subheader("⚙️ PrintPreview")

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
    ledger_records = ledger_response.data
    ledger_df = pd.DataFrame(ledger_records)
    
    if ledger_df.empty:
        st.info(f"📋 Operations Notice: Zero production records matched selection ({selected_txn_type}) between {start_date.strftime('%d-%b-%Y')} and {end_date.strftime('%d-%b-%Y')}.")
        st.stop()
        
    grouped_ledger = ledger_df.groupby("part_number").agg({
        "qty_nos": "sum",
        "date": [lambda x: pd.to_datetime(x).min().strftime("%Y-%m-%d"), lambda x: pd.to_datetime(x).max().strftime("%Y-%m-%d")],
        "hsn_code": "first",
        "description": "first"
    }).reset_index()
    
    grouped_ledger.columns = ["part_number", "qty_nos", "txn_start_raw", "txn_end_date_raw", "hsn_code", "description"]
    merged_summary = grouped_ledger.sort_values(by="part_number")
    
except Exception as e:
    iso_start = start_date.strftime("%Y-%m-%d")
    iso_end = end_date.strftime("%Y-%m-%d")
    merged_summary = pd.DataFrame([
        {"part_number": "458/20418P", "description": "DRIVE HEAD CASING", "hsn_code": "998349", "qty_nos": 121, "txn_start_raw": iso_start, "txn_end_date_raw": iso_end},
        {"part_number": "84262252.9", "description": "CHN TRACTOR HOUSING TRUMPET LH", "hsn_code": "998349", "qty_nos": 80, "txn_start_raw": iso_start, "txn_end_date_raw": iso_end},
        {"part_number": "84262253.9", "description": "CHN TRACTOR HOUSING TRUMPET RH", "hsn_code": "998349", "qty_nos": 84, "txn_start_raw": iso_start, "txn_end_date_raw": iso_end},
        {"part_number": "92180026", "description": "HOUSING MCH DC", "hsn_code": "998349", "qty_nos": 45, "txn_start_raw": iso_start, "txn_end_date_raw": iso_end},
        {"part_number": "9330093", "description": "EATON GEARCASE CASTING", "hsn_code": "998349", "qty_nos": 564, "txn_start_raw": iso_start, "txn_end_date_raw": iso_end},
        {"part_number": "W50217101Z1", "description": "CASE TRANSMISSION CASTING", "hsn_code": "998349", "qty_nos": 132, "txn_start_raw": iso_start, "txn_end_date_raw": iso_end}
    ])

for idx, row in merged_summary.iterrows():
    p_num = str(row["part_number"])
    if is_filtered_run and p_num.upper() not in selected_display.upper(): continue
        
    sim_qty = int(row["qty_nos"])
    p_desc = str(row["description"]).upper()
    
    # 🔍 DYNAMIC LOOKUP: Fetch direct match parameters out of master view schema
    match_part = catalog_df[catalog_df["part_number"] == p_num] if not catalog_df.empty else pd.DataFrame()
    
    if not match_part.empty:
        p_weight_kg = float(match_part["weight_kg"].values[0]) if pd.notna(match_part["weight_kg"].values[0]) else 28.0
        
        # Pull dynamic rate_per_ton metrics
        if "rate_per_ton" in match_part.columns and pd.notna(match_part["rate_per_ton"].values[0]):
            p_rate = float(match_part["rate_per_ton"].values[0])
        else:
            p_rate = 2650.00
            
        # Pull dynamic database HSN settings
        hsn_col_found = [c for c in match_part.columns if c in ["hsn_sac", "hsn_code"]]
        if hsn_col_found and pd.notna(match_part[hsn_col_found[0]].values[0]):
            db_hsn = str(match_part[hsn_col_found[0]].values[0]).strip()
        else:
            db_hsn = "998349"
    else:
        p_weight_kg = 28.0
        p_rate = 2650.00
        db_hsn = "998349"
    
    if parsed_hsn_override_list:
        hsn_code = parsed_hsn_override_list[len(line_items_payload) % len(parsed_hsn_override_list)]
    else:
        hsn_code = db_hsn
        
    s_date_raw = str(row["txn_start_raw"])
    e_date_raw = str(row["txn_end_date_raw"])
    
    try:
        s_date_clean = datetime.strptime(s_date_raw.split(" ")[0], "%Y-%m-%d").strftime("%d-%b-%Y")
        e_date_clean = datetime.strptime(e_date_raw.split(" ")[0], "%Y-%m-%d").strftime("%d-%b-%Y")
        txn_date_range_display = f"{s_date_clean} to {e_date_clean}" if s_date_clean != e_date_clean else s_date_clean
    except:
        txn_date_range_display = f"{s_date_raw} to {e_date_raw}" if s_date_raw != e_date_raw else s_date_raw
    
    total_wt_mt = (sim_qty * p_weight_kg) / 1000.0
    taxable_val = total_wt_mt * p_rate
    tax_amt = taxable_val * 0.18
    
    item_node = {
        "item_no": len(line_items_payload) + 1, "txn_date": txn_date_range_display, "part_number": p_num, "description": p_desc, "hsn": hsn_code,
        "qty": sim_qty, "wt_pc": p_weight_kg, "total_wt_mt": total_wt_mt, "rate_mt": p_rate,
        "taxable_value": taxable_val, "tax_amt": tax_amt, "gross_amount": taxable_val + tax_amt
    }
    line_items_payload.append(item_node)
    
    if hsn_code not in hsn_summary_map: hsn_summary_map[hsn_code] = {"taxable_value": 0.0, "tax_amount": 0.0}
    hsn_summary_map[hsn_code]["taxable_value"] += taxable_val
    hsn_summary_map[hsn_code]["tax_amount"] += tax_amt

summary_df = pd.DataFrame(line_items_payload)

if not summary_df.empty:
    total_invoice_pieces = int(summary_df["qty"].sum())
    total_invoice_weight_mt = float(summary_df["total_wt_mt"].sum())
    total_taxable_subtotal = float(summary_df["taxable_value"].sum())
    total_tax_sum = float(summary_df["tax_amt"].sum())
    grand_invoice_total = total_taxable_subtotal + total_tax_sum
    
    try:
        rupees_integral = int(grand_invoice_total)
        paise_fractional = int(round((grand_invoice_total - rupees_integral) * 100))
        words_main = num2words(rupees_integral, lang='en_IN').title().replace("-", " ")
        invoice_total_words = f"{words_main} Rupees And {num2words(paise_fractional, lang='en_IN').title().replace('-', ' ')} Paise Only." if paise_fractional > 0 else f"{words_main} Rupees Only."
        tax_total_words = f"{num2words(int(total_tax_sum), lang='en_IN').title().replace('-', ' ')} Rupees Only."
    except:
        invoice_total_words, tax_total_words = "Amount Calculated Dynamically.", "Calculated Automatically."
    
    st.dataframe(
        summary_df[["item_no", "txn_date", "part_number", "description", "qty", "wt_pc", "total_wt_mt", "rate_mt", "taxable_value"]], 
        column_config={
            "item_no": "Sr No", "txn_date": "📅 Date of Transaction (Range Summary)", "part_number": "Part Number", 
            "description": "Part Description", "qty": "Total Quantity (Nos)", "wt_pc": "Weight/Pc (KG)", 
            "total_wt_mt": "Total Tonnage (MT)", "rate_mt": "Rate/MT", "taxable_value": "Amount"
        },
        width="stretch", hide_index=True
    )
else:
    total_invoice_pieces, total_invoice_weight_mt, total_taxable_subtotal, total_tax_sum, grand_invoice_total = 0, 0.0, 0.0, 0.0, 0.0
    invoice_total_words, tax_total_words = "Zero Rupees Only.", "Zero Rupees Only."
    st.info("📋 Operational Filter: No transaction records found matching active filter configurations.")

invoice_payload = {
    "invoice_no": str(invoice_serial_no), "start_date": invoice_date_input.strftime("%d-%b-%Y"), "end_date": due_date_input.strftime("%d-%b-%Y"),
    "place_of_supply": str(place_of_supply), "src_name": str(src_name), "src_address": str(src_address),
    "src_gstin": str(src_gstin), "src_mobile": str(src_mobile), "src_email": str(src_email), "bill_name": str(bill_name),
    "bill_contact_person": str(bill_person), "bill_address": str(bill_address), "bill_gstin": str(bill_gstin),
    "bill_mobile": str(bill_no), "ship_address": str(ship_addr_override), "line_items": line_items_payload,
    "taxable_amount": total_taxable_subtotal, "igst": total_tax_sum, "grand_total": grand_invoice_total,
    "total_words": invoice_total_words, "tax_total_words": tax_total_words, "hsn_map": hsn_summary_map,
    "total_invoice_weight_mt": total_invoice_weight_mt, "total_pieces": total_invoice_pieces
}
# ============================================================================
# SECTION 4: PDF BLOCKS MATRIX GENERATOR
# ============================================================================
def generate_invoice_pdf_file(data):
    pdf_filename = f"generated/Invoice_{data['invoice_no'].replace('/', '_')}.pdf"
    os.makedirs("generated", exist_ok=True)
    doc = SimpleDocTemplate(pdf_filename, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story = []
    
    title_style = ParagraphStyle('DocTitle', fontName='Helvetica-Bold', fontSize=12, leading=14, alignment=1)
    meta_lbl = ParagraphStyle('MetaLbl', fontName='Helvetica', fontSize=7, leading=9, textColor=colors.HexColor('#444444'))
    meta_bold = ParagraphStyle('MetaBold', fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.black)
    meta_body = ParagraphStyle('MetaBody', fontName='Helvetica', fontSize=8, leading=11, textColor=colors.black)
    hdr_style = ParagraphStyle('HdrCell', fontName='Helvetica-Bold', fontSize=7.5, leading=9, alignment=1)
    cell_center = ParagraphStyle('CellC', fontName='Helvetica', fontSize=8, leading=10, alignment=1)
    cell_left = ParagraphStyle('CellL', fontName='Helvetica', fontSize=8, leading=10, alignment=0)
    cell_right = ParagraphStyle('CellR', fontName='Helvetica', fontSize=8, leading=10, alignment=2)
    cell_right_bold = ParagraphStyle('CellRB', fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=2)
    
    story.append(Paragraph("Tax Invoice", title_style))
    story.append(Spacer(1, 6))
    
    src_p = Paragraph(f"<b>{data['src_name']}</b><br/>{data['src_address'].replace('\n','<br/>')}<br/><b>GSTIN/UIN:</b> {data['src_gstin']}", meta_body)
    header_data = [
        [src_p, Paragraph(f"Invoice No.<br/><b>{data['invoice_no']}</b>", meta_body), Paragraph(f"Dated<br/><b>{data['start_date']}</b>", meta_body)],
        ["", Paragraph("Delivery Note", meta_lbl), Paragraph("Mode/Terms of Payment", meta_lbl)],
        [Paragraph(f"<b>Consignee (Ship to)</b><br/><b>{data['bill_name']}</b><br/>{data['ship_address'].replace('\n','<br/>')}<br/><b>GSTIN/UIN:</b> {data['bill_gstin']}", meta_body), Paragraph("Reference No.", meta_lbl), Paragraph("Other References", meta_lbl)],
        ["", Paragraph("Buyer's Order No.", meta_lbl), Paragraph("Dated", meta_lbl)],
        ["", Paragraph("Dispatch Doc No.", meta_lbl), Paragraph("Delivery Note Date", meta_lbl)],
        [Paragraph(f"<b>Buyer (Bill to)</b><br/><b>{data['bill_name']}</b><br/>{data['bill_address'].replace('\n','<br/>')}<br/><b>GSTIN/UIN:</b> {data['bill_gstin']}", meta_body), Paragraph("Dispatched through", meta_lbl), Paragraph("Destination", meta_lbl)],
        ["", Paragraph("Terms of Delivery", meta_lbl), ""]
    ]
    top_table = Table(header_data, colWidths=[270, 135, 135])
    top_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#000000')),
        ('SPAN', (0,0), (0,1)), ('SPAN', (0,2), (0,4)), ('SPAN', (0,5), (0,6)), ('SPAN', (1,6), (2,6)), ('PADDING', (0,0), (-1,-1), 4)
    ]))
    story.append(top_table)
    story.append(Spacer(1, 8))
    
    table_content = [[Paragraph("SI<br/>No", hdr_style), Paragraph("Description of Goods", hdr_style), Paragraph("HSN/SAC", hdr_style), Paragraph("Quantity", hdr_style), Paragraph("Weight Per<br/>Pieces", hdr_style), Paragraph("Total Weight<br/>In Ton", hdr_style), Paragraph("Per<br/>Ton<br/>Rate", hdr_style), Paragraph("Amount", hdr_style)]]
    for idx, item in enumerate(data["line_items"]):
        table_content.append([Paragraph(str(idx+1), cell_center), Paragraph(f"<b>{item['part_number']}</b><br/>{item['description']}", cell_left), Paragraph(item["hsn"], cell_center), Paragraph(f"{item['qty']:,}", cell_center), Paragraph(f"{item['wt_pc']:.1f}KG", cell_center), Paragraph(f"{item['total_wt_mt']:.4f}", cell_center), Paragraph(f"{int(item['rate_mt'])}", cell_center), Paragraph(f"<b>₹ {item['taxable_value']:,.2f}</b>", cell_right)])
    table_content.append(["", Paragraph("<b>Total</b>", cell_left), "", Paragraph(f"<b>{data['total_pieces']}</b>", cell_center), "", Paragraph(f"<b>{data['total_invoice_weight_mt']:.4f}</b>", cell_center), "", Paragraph(f"<b>₹ {data['taxable_amount']:,.2f}</b>", cell_right_bold)])
    
    item_table = Table(table_content, colWidths=[25, 175, 55, 45, 50, 55, 45, 90], repeatRows=1)
    item_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#000000')), ('PADDING', (0,0), (-1,-1), 4)]))
    story.append(item_table)
    
    summary_data = [
        [Paragraph("Amount Chargeable (in words)", meta_lbl), Paragraph("E. & O.E", ParagraphStyle('Roe', fontName='Helvetica', fontSize=7, alignment=2))],
        [Paragraph(f"<b>{data['total_words']}</b>", meta_bold), ""],
        [Paragraph("HSN/SAC", hdr_style), Paragraph("Taxable Value", hdr_style), Paragraph("Integrated Tax Rate", hdr_style), Paragraph("Integrated Tax Amount", hdr_style), Paragraph("Total Tax Amount", hdr_style)]
    ]
    for hsn_code, vals in data["hsn_map"].items():
        summary_data.append([Paragraph(hsn_code, cell_center), Paragraph(f"₹ {vals['taxable_value']:,.2f}", cell_right), Paragraph("18%", cell_center), Paragraph(f"₹ {vals['tax_amount']:,.2f}", cell_right), Paragraph(f"₹ {vals['tax_amount']:,.2f}", cell_right)])
    summary_data.append([Paragraph("<b>Total</b>", cell_center), Paragraph(f"<b>₹ {data['taxable_amount']:,.2f}</b>", cell_right_bold), "", Paragraph(f"<b>₹ {data['igst']:,.2f}</b>", cell_right_bold), Paragraph(f"<b>₹ {data['igst']:,.2f}</b>", cell_right_bold)])
    
    summary_table = Table(summary_data, colWidths=[100, 110, 80, 125, 125])
    summary_table.setStyle(TableStyle([('SPAN', (0,0), (3,0)), ('SPAN', (0,1), (4,1)), ('GRID', (0,2), (-1,-1), 0.5, colors.HexColor('#000000')), ('PADDING', (0,0), (-1,-1), 4)]))
    story.append(summary_table)
    story.append(Spacer(1, 6))
    
    story.append(Paragraph(f"Tax Amount (in words) : <b>{data['tax_total_words']}</b>", meta_body))
    story.append(Spacer(1, 6))
    
    bank_p = Paragraph(f"<b>Company's Bank Details</b><br/>Bank Name: <b>Indian Bank</b><br/>A/c No: <b>8383467708</b><br/>IFS Code: <b>IDIB000P618</b>", meta_body)
    decl_p = Paragraph("<b>Declaration</b><br/>We declare that this invoice shows the actual price of the goods described and that all particulars are true and correct.", meta_body)
    sign_p = Paragraph(f"for <b>{data['src_name']}</b><br/><br/><br/><br/><b>Authorised Signatory</b>", ParagraphStyle('RSign', parent=meta_body, alignment=2))
    
    footer_table = Table([[bank_p, sign_p], [decl_p, ""]], colWidths=[300, 240])
    footer_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#000000')), ('PADDING', (0,0), (-1,-1), 5)]))
    story.append(footer_table)
    story.append(Spacer(1, 6))
    story.append(Paragraph("This is a Computer Generated Invoice", ParagraphStyle('WaiverText', fontName='Helvetica-Oblique', fontSize=7.5, alignment=1)))
    
    doc.build(story)
    return pdf_filename
# ============================================================================
# SECTION 5: DOWNLOAD/PRINT CENTER RUNTIME BUTTON
# ============================================================================
st.markdown("---")
st.subheader("📥 Download/Print Center")

if st.button("🚀 Compile Print-Ready GST Commercial Invoice PDF", width="stretch"):
    if not supabase:
        st.error("❌ Cannot complete operation: Database connection is unavailable.")
    elif summary_df.empty:
        st.error("❌ Cannot compile an empty invoice layout. Check your ledger filters.")
    else:
        f_path = generate_invoice_pdf_file(invoice_payload)
        try:
            dup_check = supabase.table("cntr_invoice_history").select("invoice_no").eq("invoice_no", invoice_payload["invoice_no"]).execute()
            is_duplicate = len(dup_check.data) > 0
        except Exception as table_err:
            is_duplicate = False
            
        if is_duplicate:
            st.error(f"⚠️ Validation Failure: Invoice serial number **{invoice_payload['invoice_no']}** already exists in the tracking log.")
        else:
            try:
                history_row = {
                    "invoice_no": invoice_payload["invoice_no"], "invoice_date": invoice_date_input.strftime("%Y-%m-%d"),
                    "buyer_name": invoice_payload["bill_name"], "buyer_gstin": invoice_payload["bill_gstin"],
                    "total_pieces": invoice_payload["total_pieces"], "total_weight_mt": invoice_payload["total_invoice_weight_mt"],
                    "taxable_amount": invoice_payload["taxable_amount"], "igst_amount": invoice_payload["igst"], "grand_total": invoice_payload["grand_total"]
                }
                supabase.table("cntr_invoice_history").insert(history_row).execute()
                st.success("🎉 Multi-item tax invoice compiled and saved to cloud registry successfully!")
            except Exception as save_err:
                st.warning("📋 Cloud Audit Notice: PDF compiled successfully but history row log bypass active.")
            
            with open(f_path, "rb") as f:
                st.download_button(label="📥 Download Official Job-Work GST Invoice PDF", data=f, file_name=f"Invoice_{invoice_payload['invoice_no'].replace('/', '_')}.pdf", mime="application/pdf", width="stretch")
