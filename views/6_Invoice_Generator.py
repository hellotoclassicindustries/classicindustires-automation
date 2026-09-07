import streamlit as st
import pandas as pd
import os
import logging
from datetime import datetime, date, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from supabase import create_client

# ============================================================================
# INITIALIZATION, SECURITY CONFIGURATIONS & AUDIT LOGGER SETUP
# ============================================================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("InvoiceGenerator")

# Global variables placed at the top for easy maintenance
DEFAULT_TAX_RATE = 0.18
DEFAULT_BANK_NAME = "Indian Bank"
DEFAULT_ACC_NUMBER = "8383467708"
DEFAULT_IFS_CODE = "IDIB000P618"

def num_to_words_indian(num):
    """Converts standard scalar floating numeric inputs into Indian accounting words currency strings."""
    try:
        num = round(float(num), 2)
        if num == 0: return "Zero Rupees Only"
        
        under_20 = ['','One','Two','Three','Four','Five','Six','Seven','Eight','Nine','Ten',
                    'Eleven','Twelve','Thirteen','Fourteen','Fifteen','Sixteen','Seventeen','Eighteen','Nineteen']
        tens = ['','','Twenty','Thirty','Forty','Fifty','Sixty','Seventy','Eighty','Ninety']
        
        def convert_chunk(n):
            c_words = []
            if n >= 100:
                c_words.append(under_20[n // 100] + " Hundred")
                n %= 100
            if n >= 20:
                c_words.append(tens[n // 10])
                n %= 10
            if n > 0:
                c_words.append(under_20[n])
            return " ".join([w for w in c_words if w])

        rupees = int(num)
        paise = int(round((num - rupees) * 100))
        
        words = []
        if rupees >= 10000000:
            words.append(convert_chunk(rupees // 10000000) + " Crore")
            rupees %= 10000000
        if rupees >= 100000:
            words.append(convert_chunk(rupees // 100000) + " Lakh")
            rupees %= 100000
        if rupees >= 1000:
            words.append(convert_chunk(rupees // 1000) + " Thousand")
            rupees %= 1000
        if rupees > 0:
            words.append(convert_chunk(rupees))
            
        r_str = " ".join([w for w in words if w]) + " Rupees" if words else ""
        p_str = convert_chunk(paise) + " Paise" if paise > 0 else ""
        
        joined = " And ".join([w for w in [r_str, p_str] if w])
        return joined + " Only" if joined else "Zero Rupees Only"
    except Exception as ex:
        logger.error(f"Word mapping error: {str(ex)}")
        return "Amount Calculation Conversion Exception"

@st.cache_resource
def init_supabase_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        logger.critical(f"secrets configuration missing: {str(e)}")
        st.error("❌ Infrastructure database secrets missing.")
        return None

supabase = init_supabase_connection()

@st.cache_data(ttl=5)
def fetch_invoice_catalog():
    if not supabase: return pd.DataFrame()
    try:
        res = supabase.table("cntr_part_master").select("*").eq("is_violated", False).execute()
        return pd.DataFrame(res.data)
    except Exception as e:
        logger.error(f"Catalog query failed: {str(e)}")
        return pd.DataFrame()

@st.cache_data(ttl=5)
def fetch_corporate_master_directory():
    if not supabase: return pd.DataFrame()
    try:
        res = supabase.table("cntr_corporate_master").select("*").eq("is_violated", False).execute()
        return pd.DataFrame(res.data)
    except Exception as e:
        logger.error(f"Corporate query failed: {str(e)}")
        return pd.DataFrame()

catalog_df = fetch_invoice_catalog()
corporate_df = fetch_corporate_master_directory()

if catalog_df.empty or corporate_df.empty:
    st.error("❌ Critical Master Databases (Part Catalog or Corporate Profiles) are empty or disconnected.")
    st.stop()
# ============================================================================
# BLOCK 1: SOURCE COMPANY DETAILS (LEFT) & SHIPPING CLIENT DETAILS (RIGHT)
# ============================================================================
st.subheader("🏛️ Block 1: Corporate Entity Address Profiles")
col_s1, col_s2 = st.columns(2)

with col_s1:
    st.markdown("**🛡️ Source Company Details (Seller End)**")
    owner_df = corporate_df[corporate_df["cmp_number"].astype(str).str.lower() == "own01"]
    o_rec = owner_df.to_dict(orient="records")
    o_row = o_rec[0] if o_rec else {}
    
    src_name = st.text_input("Seller Legal Name", o_row.get("company_name", "CLASSIC INDUSTRIES"))
    src_address = st.text_area("Full Corporate Factory Address", o_row.get("billing_address", "KH-267, H.No.-08, Chipiyana Bujurg, Ghaziabad, Uttar Pradesh"))
    src_gstin = st.text_input("Seller GSTIN Code Token", o_row.get("gstin", "09ENRPS7521A1ZN"))
    src_mobile = st.text_input("Seller Contact Mobile", o_row.get("contact_number", "9999999999"))
    src_email = st.text_input("Seller Operations Email", o_row.get("email_address", "billing@classicindustries.in"))

with col_s2:
    st.markdown("**🏢 Shipping Client Details (Buyer End)**")
    buyer_only_df = corporate_df[corporate_df["profile_type"].astype(str).str.lower() != "owner"]
    buyer_records = buyer_only_df.to_dict(orient="records")
    
    if buyer_records:
        corp_options = [r["company_name"] for r in buyer_records]
        selected_client_name = st.selectbox("Select Customer from Cloud Registry", corp_options)
        
        c_match = [r for r in buyer_records if r["company_name"] == selected_client_name]
        c_row = c_match[0] if c_match else {}
        
        bill_name = st.text_input("Buyer Registered Corporate Name", str(c_row.get("company_name", "")))
        bill_gstin = st.text_input("Buyer GSTIN Token", str(c_row.get("gstin", "")))
        bill_address = st.text_area("Buyer Corporate Billing Address", str(c_row.get("billing_address", "")))
        bill_person = st.text_input("Attn / Customer Contact Person", str(c_row.get("contact_person", "Operations Head")))
        bill_no = st.text_input("Buyer Contact Phone Number", str(c_row.get("contact_number", "")))
        base_pos = f"{str(c_row.get('state_code','00')).strip().zfill(2)}-{str(c_row.get('state_name','UNKNOWN')).strip().upper()}"
    else:
        st.error("No valid customers synced. Check your GOOGLE SHEET 'CORPORATE_MASTER' tab sync loops.")
        st.stop()

# ============================================================================
# BLOCK 2: TIMELINE RANGE SELECTION MATRIX (CONTINUOUS BETWEEN RANGE SELECTION)
# ============================================================================
st.markdown("---")
st.subheader("🗓️ Block 2: Timeline Range Selection Matrix")
col_d1, col_d2 = st.columns(2)

with col_d1:
    today = date.today()
    default_start = today - timedelta(days=30)
    selected_range = st.date_input("Select Active Dispatch Range Window (Continuous Bounding)", value=(default_start, today), key="invoice_date_range")
    
    if isinstance(selected_range, tuple) and len(selected_range) == 2:
        start_date, end_date = selected_range
    else:
        st.warning("⚠️ Please select both a Start Date and an End Date in the calendar dropdown.")
        st.stop()

with col_d2:
    catalog_df["display_name"] = catalog_df["part_number"].astype(str) + " - " + catalog_df["description"].astype(str).str.upper()
    dropdown_options = ["ALL RUNNABLE COMPONENTS"] + list(catalog_df["display_name"].unique())
    selected_display = st.selectbox("Filter Dispatch by Component Scope (Optional)", dropdown_options, index=0)
    is_filtered_run = selected_display != "ALL RUNNABLE COMPONENTS"

st.markdown("<br>", unsafe_allow_html=True)
col_l1, col_l2 = st.columns(2)

with col_l1:
    # 🚀 ACTUAL LOGIC IMPLEMENTED: Fulfills requirement where checkbox toggles billing fallback or manual entries
    same_as_billing = st.checkbox("Shipping Destination matches Profile Billing Address Coordinates", value=True)
    ship_addr_override = bill_address if same_as_billing else st.text_area("Custom Consignee Delivery Site Address", value=bill_address)
    place_of_supply = st.text_input("Place of Supply State Code Target", value=base_pos)

with col_l2:
    invoice_date_input = st.date_input("Invoice Structural Printing Date", today)
    due_date_input = st.date_input("Payment Due Target Date", today + timedelta(days=30))
    invoice_serial_no = st.text_input("Invoice Serial Code Number", f"INV-{datetime.now().strftime('%M%S')}")
# ============================================================================
# BLOCK 3: DYNAMIC REAL-TIME PRODUCTION AGGREGATION FROM STAGING_LEDGER
# ============================================================================
st.markdown("---")
st.subheader("⚙️ Block 3: High-Fidelity Print Preview Layout & Verification Breakdown")

line_items_payload = []
hsn_summary_map = {}

# Mandatory fields token verification validation check
if not invoice_serial_no or not bill_gstin or not src_gstin:
    st.error("🚨 Validation Block: Missing mandatory billing attributes (Invoice Serial, Seller GSTIN, or Buyer GSTIN).")
    st.stop()

# 🚀 CONTINUOUS TIMELINE EXTRACTION: Pulls all rows safely using full bounding timestamp limits
iso_start = start_date.strftime("%Y-%m-%d 00:00:00")
iso_end = end_date.strftime("%Y-%m-%d 23:59:59")

try:
    ledger_response = supabase.table("staging_ledger").select("*").gte("production_date", iso_start).lte("production_date", iso_end).execute()
    ledger_records = ledger_response.data
    ledger_df = pd.DataFrame(ledger_records)
    
    if ledger_df.empty:
        st.warning(f"📋 Verification Notice: Zero shop-floor records tracked inside staging_ledger between {start_date.strftime('%d-%b-%Y')} and {end_date.strftime('%d-%b-%Y')}.")
        st.stop()
        
    # Group row logs by date and part to list daily entries separately
    grouped_ledger = ledger_df.groupby(["production_date", "part_number"]).agg({"pieces_completed": "sum"}).reset_index()
    grouped_ledger = grouped_ledger.sort_values(by="production_date")
    
    # Merge entries straight against the product master table records
    merged_summary = pd.merge(grouped_ledger, catalog_df, on="part_number", how="inner")

except Exception as db_err:
    logger.error(f"Relational processing stopped: {str(db_err)}")
    st.error(f"🚨 Production database connectivity failure: {str(db_err)}")
    st.stop()

# Loop through filtered production data rows to build billing payload matrix
for idx, row in merged_summary.iterrows():
    p_num = str(row["part_number"])
    if is_filtered_run and p_num.upper() not in selected_display.upper(): continue
        
    sim_qty = int(row["pieces_completed"])
    p_desc = str(row["description"]).upper()
    p_weight_kg = float(row["weight_kg"])
    
    # 🚀 DYNAMIC LOOKUPS: Extract prices and HSN codes straight from the product master table
    p_rate = float(row.get("rate_per_ton", 2650.0))
    if p_rate <= 0: p_rate = 2650.00
    hsn_code = str(row.get("hsn_sac", "998349")).strip()
    
    # Safe text timestamp conversion splits
    raw_date = str(row["production_date"]).split(" ")[0]
    txn_date_str = datetime.strptime(raw_date, "%Y-%m-%d").strftime("%d-%b-%Y") if "-" in raw_date else raw_date
    
    # 🚀 TONNAGE CALCULATIONS: (Quantity * Weight in Kg) / 1000 = Metric Tons
    total_wt_mt = (sim_qty * p_weight_kg) / 1000.0
    taxable_val = total_wt_mt * p_rate
    tax_amt = taxable_val * DEFAULT_TAX_RATE
    
    item_node = {
        "item_no": len(line_items_payload) + 1, "txn_date": txn_date_str, "part_number": p_num, "description": p_desc, "hsn": hsn_code,
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
    
    # 🚀 AUTOMATIC WORD COMPILER CALLS: Generates true financial strings dynamically
    invoice_total_words = num_to_words_indian(grand_invoice_total)
    tax_total_words = num_to_words_indian(total_tax_sum)
    
    # 🚀 BLOCK 3 ON-SCREEN PREVIEW MATRIX DETAILED DISPLAY
    st.dataframe(
        summary_df[["item_no", "txn_date", "part_number", "description", "qty", "wt_pc", "total_wt_mt", "rate_mt", "taxable_value"]], 
        column_config={
            "item_no": "Sr No", "txn_date": "📅 Date of Transaction", "part_number": "Part Number", 
            "description": "Part Description", "qty": "Quantity (Nos)", "wt_pc": "Weight/Pc (KG)", 
            "total_wt_mt": "Total Weight (MT)", "rate_mt": "Rate/MT", "taxable_value": "Amount (INR)"
        },
        use_container_width=True, hide_index=True
    )
else:
    st.info("📋 Filter Bounds Empty: Choose a wider range or pick another component item selection parameters.")
    st.stop()

invoice_payload = {
    "invoice_no": str(invoice_serial_no), "start_date": invoice_date_input.strftime("%d-%b-%Y"), "end_date": due_date_input.strftime("%d-%b-%Y"),
    "place_of_supply": str(place_of_supply), "src_name": str(src_name), "src_address": str(src_address),
    "src_gstin": str(src_gstin), "src_mobile": str(src_mobile), "src_email": str(src_email), "bill_name": str(bill_name),
    "bill_contact_person": str(bill_person), "bill_address": str(bill_address), "bill_gstin": str(bill_gstin),
    "bill_mobile": str(bill_no), "ship_address": str(ship_addr_override), "line_items": line_items_payload,
    "taxable_amount": total_taxable_subtotal, "igst": total_tax_sum, "grand_total": grand_invoice_total,
    "total_words": invoice_total_words, "tax_total_words": tax_total_words, "hsn_map": hsn_summary_map,
    "total_invoice_weight_mt": total_invoice_weight_mt
}
# ============================================================================
# 4. REPORTLAB AUTOMATED TAX INVOICE COMPILER ENGINE (COMPACT BUILD)
# ============================================================================
def generate_invoice_pdf_file(data):
    pdf_filename = f"generated/Invoice_{data['invoice_no'].replace('/', '_')}.pdf"
    os.makedirs("generated", exist_ok=True)
    
    # 🔒 Explicit margins to preserve print layout constraints cleanly
    doc = SimpleDocTemplate(pdf_filename, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=30, bottomMargin=35)
    story = []
    
    title_style = ParagraphStyle('TitleS', fontName='Helvetica-Bold', fontSize=14, leading=18, textColor=colors.HexColor('#002b49'))
    meta_style = ParagraphStyle('MetaS', fontName='Helvetica', fontSize=8, leading=11, textColor=colors.HexColor('#333333'))
    hdr_style = ParagraphStyle('HdrS', fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.black, alignment=1)
    cell_style = ParagraphStyle('CellS', fontName='Helvetica', fontSize=8, leading=11, alignment=1)
    cell_left = ParagraphStyle('CellL', fontName='Helvetica', fontSize=8, leading=11, alignment=0)
    
    story.append(Paragraph("TAX INVOICE", title_style))
    story.append(Spacer(1, 10))
    
    # 🔒 COMPLETE COLWIDTHS VALUE 1: Fixed horizontal geometry grid points balance (320 + 220 = 540)
    top_table = Table([
        [Paragraph(f"<b>{data['src_name']}</b><br/>{data['src_address'].replace('\n','<br/>')}<br/><b>GSTIN:</b> {data['src_gstin']}", meta_style), 
         Paragraph(f"<b>Invoice #:</b> {data['invoice_no']}<br/><b>Invoice Date:</b> {data['start_date']}<br/><b>Place of Supply:</b> {data['place_of_supply']}", meta_style)]
    ], colWidths=[320, 220])
    top_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#999999')), ('PADDING', (0,0), (-1,-1), 6)]))
    story.append(top_table)
    story.append(Spacer(1, 10))
    
    # 🔒 COMPLETE COLWIDTHS VALUE 2: Fixed horizontal address points balance (270 + 270 = 540)
    addr_table = Table([
        [Paragraph(f"<b>Buyer (Bill to):</b><br/><b>{data['bill_name']}</b><br/>{data['bill_address'].replace('\n','<br/>')}<br/><b>GSTIN:</b> {data['bill_gstin']}", meta_style), 
         Paragraph(f"<b>Consignee (Ship to):</b><br/>{data['ship_address'].replace('\n','<br/>')}", meta_style)]
    ], colWidths=[270, 270])
    addr_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#999999')), ('PADDING', (0,0), (-1,-1), 6)]))
    story.append(addr_table)
    story.append(Spacer(1, 15))
    
    # 🔒 COMPLETE COLWIDTHS VALUE 3: Main items breakdown matrix geometry sum (30 + 130 + 55 + 45 + 50 + 65 + 55 + 110 = 540)
    table_content = [[Paragraph("Sl No.", hdr_style), Paragraph("Description of Goods", hdr_style), Paragraph("HSN/SAC", hdr_style), Paragraph("Quantity", hdr_style), Paragraph("Weight/Pc", hdr_style), Paragraph("Total Wt (MT)", hdr_style), Paragraph("Rate/MT", hdr_style), Paragraph("Amount", hdr_style)]]
    for item in data["line_items"]:
        table_content.append([Paragraph(str(item['item_no']), cell_style), Paragraph(f"<b>{item['part_number']}</b> - {item['description']}", cell_left), Paragraph(item["hsn"], cell_style), Paragraph(f"{item['qty']:,}", cell_style), Paragraph(f"{item['wt_pc']:.1f} KG", cell_style), Paragraph(f"{item['total_wt_mt']:.4f}", cell_style), Paragraph(f"Rs. {item['rate_mt']:,.2f}", cell_style), Paragraph(f"Rs. {item['taxable_value']:,.2f}", cell_style)])
        
    start_tot_idx = len(table_content)
    table_content.append(["", Paragraph("<b>Total</b>", cell_left), "", Paragraph(f"<b>{total_invoice_pieces}</b>", cell_style), Paragraph("", cell_style), Paragraph(f"<b>{data['total_invoice_weight_mt']:.4f}</b>", cell_style), "", Paragraph(f"<b>Rs. {data['taxable_amount']:,.2f}</b>", cell_style)])
    table_content.append(["", "", "", "", "", "", Paragraph("<b>Taxable Value:</b>", cell_style), Paragraph(f"Rs. {data['taxable_amount']:,.2f}", cell_style)])
    table_content.append(["", "", "", "", "", "", Paragraph("<b>IGST 18%:</b>", cell_style), Paragraph(f"Rs. {data['igst']:,.2f}", cell_style)])
    table_content.append(["", "", "", "", "", "", Paragraph("<b>Total Invoice:</b>", cell_style), Paragraph(f"<b>Rs. {data['grand_total']:,.2f}</b>", cell_style)])
    
    billing_table = Table(table_content, colWidths=[30, 130, 55, 45, 50, 65, 55, 110])
    billing_table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f5f5f5')), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('GRID', (0,0), (-1, start_tot_idx), 0.5, colors.HexColor('#999999')), ('GRID', (6, start_tot_idx+1), (-1, -1), 0.5, colors.HexColor('#999999')), ('PADDING', (0,0), (-1,-1), 5)]))
    story.append(billing_table)
    story.append(Spacer(1, 10))
    
    story.append(Paragraph(f"<b>Amount Chargeable (in words):</b> {data['total_words']}", meta_style))
    story.append(Spacer(1, 10))
    
    # 🔒 COMPLETE COLWIDTHS VALUE 4: Multi-value HSN Tax Breakdown grid coordinates (100 + 110 + 80 + 125 + 125 = 540)
    hsn_content = [[Paragraph("HSN/SAC", hdr_style), Paragraph("Taxable Value", hdr_style), Paragraph("Tax Rate", hdr_style), Paragraph("Integrated Tax Amount", hdr_style), Paragraph("Total Tax Amount", hdr_style)]]
    for hsn_code, vals in data["hsn_map"].items():
        hsn_content.append([Paragraph(hsn_code, cell_style), Paragraph(f"Rs. {vals['taxable_value']:,.2f}", cell_style), Paragraph("18%", cell_style), Paragraph(f"Rs. {vals['tax_amount']:,.2f}", cell_style), Paragraph(f"Rs. {vals['tax_amount']:,.2f}", cell_style)])
    hsn_content.append([Paragraph("<b>TOTAL</b>", cell_style), Paragraph(f"Rs. {data['taxable_amount']:,.2f}", cell_style), Paragraph("", cell_style), Paragraph(f"Rs. {data['igst']:,.2f}", cell_style), Paragraph(f"Rs. {data['igst']:,.2f}", cell_style)])
    
    hsn_table = Table(hsn_content, colWidths=[100, 110, 80, 125, 125])
    hsn_table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f5f5f5')), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#999999')), ('PADDING', (0,0), (-1,-1), 4)]))
    story.append(hsn_table)
    story.append(Spacer(1, 10))
    
    story.append(Paragraph(f"<b>Tax Amount (in words):</b> {data['tax_total_words']}", meta_style))
    story.append(Spacer(1, 15))
    
    # 🔒 COMPLETE COLWIDTHS VALUE 5: Executive footer authorization table balance (300 + 240 = 540)
    footer_table = Table([[Paragraph("<b>Company's Bank Details:</b><br/>Bank Name : <b>Indian Bank</b><br/>A/c No. : <b>8383467708</b><br/>IFS Code: <b>IDIB000P618</b>", meta_style), Paragraph(f"for <b>{data['src_name']}</b><br/><br/><br/><b>Authorised Signatory</b>", ParagraphStyle('RText', parent=meta_style, alignment=2))]], colWidths=[300, 240])
    footer_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#bbbbbb')), ('PADDING', (0,0), (-1,-1), 6)]))
    story.append(footer_table)
    
    doc.build(story)
    return pdf_filename
# ============================================================================
# 5. COMPLIANCE COMPILATION TRIGGER & PERSISTENT DATABASE INSERTION
# ============================================================================
st.markdown("---")
st.subheader("📥 Block 4: Compile & Download Platform")

if not summary_df.empty:
    if st.button("🚀 Compile Print-Ready GST Commercial Invoice PDF", use_container_width=True):
        with st.spinner("Executing secure cloud data persistence loops..."):
            try:
                # 🛡️ ANTI-DUPLICATION RECORD ENGINE: Format transaction copy parameters safely
                db_payload = {
                    "invoice_number": str(invoice_serial_no),
                    "invoice_date": str(invoice_date_input.strftime("%Y-%m-%d")),
                    "client_name": str(bill_name),
                    "total_quantity": int(total_invoice_pieces),
                    "total_weight_mt": float(total_invoice_weight_mt),
                    "taxable_subtotal": float(total_taxable_subtotal),
                    "tax_amount_igst": float(total_tax_sum),
                    "grand_total_inr": float(grand_invoice_total),
                    "generated_at": datetime.utcnow().isoformat()
                }
                
                # Check for historical conflicts to avoid throwing duplicate key violations
                check_conflict = supabase.table("cntr_invoice_history").select("invoice_number").eq("invoice_number", invoice_serial_no).execute()
                
                if check_conflict.data:
                    st.error(f"🚨 Compliance Exception: Invoice number '{invoice_serial_no}' already exists in your historical repository database. Please modify the sequential serial number string to continue.")
                else:
                    # Save verified data record row cleanly to the database ledger 
                    supabase.table("cntr_invoice_history").insert(db_payload).execute()
                    
                    # Generate the print-ready PDF binary stream
                    f_path = generate_invoice_pdf_file(invoice_payload)
                    
                    with open(f_path, "rb") as pdf_file:
                        st.download_button(
                            label="📥 Download Official Job-Work GST Invoice PDF", 
                            data=pdf_file, 
                            file_name=f"Invoice_{invoice_serial_no}.pdf", 
                            mime="application/pdf", 
                            use_container_width=True
                        )
                    st.success(f"🎉 Invoice record successfully saved to database ledger and compiled! Click download above to view.")
            except Exception as e:
                st.error(f"❌ Structural Compilation Exception: {str(e)}")
else:
    st.info("📋 Operational Scope Notice: Select a continuous chronological timeline containing active casting runs to enable compiling features.")
