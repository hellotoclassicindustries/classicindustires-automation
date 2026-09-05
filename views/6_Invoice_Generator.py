import streamlit as st
import pandas as pd
import os
from datetime import datetime, date, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from supabase import create_client

# ============================================================================
# 1. DATABASE CONNECTIVITY LAYER
# ============================================================================
@st.cache_resource
def init_supabase_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"❌ Missing Infrastructure Secrets: {str(e)}")
        return None

supabase = init_supabase_connection()

@st.cache_data(ttl=30)
def fetch_invoice_catalog():
    if not supabase:
        return pd.DataFrame()
    try:
        response = supabase.table("vw_cntr_part_master").select("*").execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"🚨 Failed to load component parameters: {str(e)}")
        return pd.DataFrame()

# ============================================================================
# 2. DATE FILTER & DROPDOWN PARAMETERS
# ============================================================================
catalog_df = fetch_invoice_catalog()

if catalog_df.empty:
    st.warning("📋 Operations Notice: The master part catalog database is disconnected or empty.")
    st.stop()

st.title("🧾 Commercial Tax Invoice Generator")
st.markdown("---")

st.subheader("🗓️ Date Bounds & Component Scope")
col_i1, col_i2 = st.columns(2)

with col_i1:
    today = date.today()
    default_start = today - timedelta(days=30)
    selected_range = st.date_input(
        "Select Invoice Date Range (Start & End Date)",
        value=(default_start, today),
        key="invoice_date_range"
    )
    if isinstance(selected_range, tuple) and len(selected_range) == 2:
        start_date, end_date = selected_range
    else:
        st.info("💡 Please select both a start date and an end date on the calendar dropdown.")
        st.stop()

with col_i2:
    catalog_df["display_name"] = catalog_df["part_number"].astype(str) + " - " + catalog_df["description"].astype(str).str.upper()
    dropdown_options = ["ALL COMPONENTS (AGGREGATE RUN)"] + list(catalog_df["display_name"].unique())
    selected_display = st.selectbox("Filter by Specific Component (Optional)", dropdown_options, index=0)
    is_filtered_run = selected_display != "ALL COMPONENTS (AGGREGATE RUN)"

st.markdown("---")
st.subheader("🏢 Step 1: Corporate Entity Address Profiles")
col_s1, col_s2 = st.columns(2)

with col_s1:
    st.markdown("**🛡️ 1) Source Company Details (Seller)**")
    src_name = st.text_input("Seller Legal Entity Name", "CLASSIC INDUSTRIES")
    src_tagline = st.text_input("Business Line Tagline", "Manufacturer & Supplier of Cast Iron Components")
    src_address = st.text_area("Full Corporate Factory Address", "KH-267, H.No.-08, Chipiyana Bujurg,\nGhaziabad – 201009, Uttar Pradesh")
    src_gstin = st.text_input("Seller GSTIN Token", "09ENRPS7521A1ZN")
    src_mobile = st.text_input("Seller Contact Mobile", "9999999999")
    src_email = st.text_input("Seller Operations Email", "billing@classicindustries.in")

with col_s2:
    st.markdown("**🏢 2) Bill To / Client Details (Buyer)**")
    bill_name = st.text_input("Buyer Company Profile Name", "TATA MOTORS LIMITED")
    bill_gstin = st.text_input("Buyer GSTIN Token", "27AAACT2727Q1ZW")
    bill_address = st.text_area("Buyer Corporate Billing Address", "Nigadi Bhosari Road, PIMPRI\nPune, Maharashtra, 411018")
    bill_contact_person = st.text_input("Attn / Customer Contact Person", "Natarajan Chandrasekaran")
    bill_mobile = st.text_input("Buyer Mobile / Phone No", "9999999999")

st.markdown("<br>", unsafe_allow_html=True)
st.subheader("🚛 Step 2: Logistic Matrix & Delivery Directives")
col_s3, col_s4 = st.columns(2)

with col_s3:
    st.markdown("**📍 Shipping Coordinates (Consignee)**")
    same_as_billing = st.checkbox("Shipping Destination matches Billing Address", value=False)
    if same_as_billing:
        ship_addr_str = bill_address
    else:
        ship_addr_str = st.text_area("Consignee Delivery Site Address", "Survey 115/1, ISB Rd, Financial District\nGachibowli, Nanakramguda\nHyderabad, TELANGANA, 500032")
    place_of_supply = st.text_input("Place of Supply State Code", "36-TELANGANA")

with col_s4:
    st.markdown("**🔢 Invoice Serial & Chronological Controls**")
    invoice_date_input = st.date_input("Invoice Operational Date", today)
    due_date_input = st.date_input("Payment Due Date Target", today + timedelta(days=30))
    invoice_serial_no = st.text_input("Invoice Serial Code #", f"INV-{datetime.now().strftime('%M%S')}")
# ============================================================================
# 3. LIVE TRANSACTION AGGREGATION & TAX CORES
# ============================================================================
st.markdown("---")
st.subheader("⚙️ Step 3: Component Line-Items Data Input")

simulated_jobwork_records = [
    {"item_no": 1, "part_number": "9330093", "description": "EATON GEARCASE CASTING", "hsn": "87038070", "qty": 70, "wt_pc": 57.00, "rate_mt": 72000.00},
    {"item_no": 2, "part_number": "W50217101Z1", "description": "CASE TRANSMISSION CASTIN\n1. Item - Core Cleaning\n2. Item - Chipping Line Run", "hsn": "87089900", "qty": 100, "wt_pc": 28.00, "rate_mt": 65000.00}
]

line_items_payload = []
hsn_summary_map = {}

for row in simulated_jobwork_records:
    if is_filtered_run and str(row["part_number"]).upper() not in selected_display.upper():
        continue
        
    total_wt_mt = (row["qty"] * row["wt_pc"]) / 1000.0
    taxable_val = total_wt_mt * row["rate_mt"]
    tax_amt = taxable_val * 0.18
    gross_row_amt = taxable_val + tax_amt
    
    item_node = {
        "item_no": len(line_items_payload) + 1,
        "part_number": row["part_number"],
        "description": row["description"],
        "hsn": row["hsn"],
        "qty": row["qty"],
        "wt_pc": row["wt_pc"],
        "total_wt_mt": total_wt_mt,
        "rate_mt": row["rate_mt"],
        "taxable_value": taxable_val,
        "tax_amt": tax_amt,
        "gross_amount": gross_row_amt
    }
    line_items_payload.append(item_node)
    
    if row["hsn"] not in hsn_summary_map:
        hsn_summary_map[row["hsn"]] = {"taxable_value": 0.0, "tax_amount": 0.0}
    hsn_summary_map[row["hsn"]]["taxable_value"] += taxable_val
    hsn_summary_map[row["hsn"]]["tax_amount"] += tax_amt

summary_df = pd.DataFrame(line_items_payload)
if summary_df.empty:
    st.warning("⚠️ No records found matching active component filter scope.")
    st.stop()

total_invoice_pieces = int(summary_df["qty"].sum())
total_invoice_weight_mt = float(summary_df["total_wt_mt"].sum())
total_taxable_subtotal = float(summary_df["taxable_value"].sum())
total_tax_sum = float(summary_df["tax_amt"].sum())
grand_invoice_total = total_taxable_subtotal + total_tax_sum
invoice_total_words = "INR Nine Lakh, Fifty-Two Thousand, Three Hundred And Ninety-Nine Rupees Only."

card_1, card_2, card_3 = st.columns(3)
card_1.metric("Total Quantity Dispatched", f"{total_invoice_pieces:,} Nos")
card_2.metric("Total Shipment Weight", f"{total_invoice_weight_mt:.3f} MT")
card_3.metric("Gross Invoice Total (INR)", f"₹{grand_invoice_total:,.2f}")

st.markdown("<br>", unsafe_allow_html=True)
st.markdown("**🔍 Live Challan-Wise Invoice Preview Breakdown:**")
st.dataframe(summary_df[["item_no", "part_number", "description", "hsn", "qty", "wt_pc", "total_wt_mt", "rate_mt", "taxable_value"]], use_container_width=True, hide_index=True)
# ============================================================================
# 4. AUTOMATED REPORTLAB PDF DOCUMENT BUILDER
# ============================================================================
def generate_invoice_pdf_file(data):
    pdf_filename = f"generated/Invoice_{data['invoice_no'].replace('/', '_')}.pdf"
    os.makedirs("generated", exist_ok=True)
    
    # Page Width Blueprint = 540 points print-safe layout area
    doc = SimpleDocTemplate(pdf_filename, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=30, bottomMargin=35)
    story = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('TitleS', fontName='Helvetica-Bold', fontSize=15, leading=18, textColor=colors.HexColor('#002b49'))
    meta_style = ParagraphStyle('MetaS', fontName='Helvetica', fontSize=8, leading=11, textColor=colors.HexColor('#333333'))
    hdr_style = ParagraphStyle('HdrS', fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.black, alignment=1)
    cell_style = ParagraphStyle('CellS', fontName='Helvetica', fontSize=8, leading=11, alignment=1)
    cell_left = ParagraphStyle('CellL', fontName='Helvetica', fontSize=8, leading=11, alignment=0)
    
    story.append(Paragraph("TAX INVOICE", title_style))
    story.append(Spacer(1, 10))
    
    # 🔒 Width Fixed: [270, 270] = 540 total point width balance
    top_grid_data = [
        [Paragraph(f"<b>{data['src_name']}</b><br/>{data['src_tagline']}<br/>{data['src_address'].replace('\n','<br/>')}<br/><b>GSTIN:</b> {data['src_gstin']}<br/><b>Mob:</b> {data['src_mobile']} | <b>Email:</b> {data['src_email']}", meta_style),
         Paragraph(f"<b>Invoice #:</b> {data['invoice_no']}<br/><b>Invoice Date:</b> {data['start_date']}<br/><b>Place of Supply:</b> {data['place_of_supply']}<br/><b>Due Date:</b> {data['end_date']}", meta_style)]
    ]
    top_table = Table(top_grid_data, colWidths=[270, 270])
    top_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#999999')), ('PADDING', (0,0), (-1,-1), 6)]))
    story.append(top_table)
    story.append(Spacer(1, 10))
    
    # 🔒 Width Fixed: [270, 270] = 540 total point width balance
    addr_grid_data = [
        [Paragraph(f"<b>Customer Details:</b><br/><b>{data['bill_name']}</b><br/>Attn: {data['bill_contact_person']}<br/><b>Billing Address:</b><br/>{data['bill_address'].replace('\n','<br/>')}<br/><b>GSTIN:</b> {data['bill_gstin']} | <b>Ph:</b> {data['bill_mobile']}", meta_style),
         Paragraph(f"<b>Shipping Address:</b><br/>{data['ship_address'].replace('\n','<br/>')}", meta_style)]
    ]
    addr_table = Table(addr_grid_data, colWidths=[270, 270])
    addr_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#999999')), ('PADDING', (0,0), (-1,-1), 6)]))
    story.append(addr_table)
    story.append(Spacer(1, 15))
    
    # 🔒 Width Fixed: Sum of columns = 540 total point width balance
    main_headers = [Paragraph("#", hdr_style), Paragraph("Item Description", hdr_style), Paragraph("HSN/SAC", hdr_style), Paragraph("Rate/MT", hdr_style), Paragraph("Qty", hdr_style), Paragraph("Taxable Value", hdr_style), Paragraph("Tax Amount", hdr_style), Paragraph("Amount", hdr_style)]
    table_content = [main_headers]
    
    for idx, item in enumerate(data["line_items"]):
        table_content.append([
            Paragraph(str(idx+1), cell_style), Paragraph(f"<b>{item['part_number']}</b><br/>{item['description'].replace('\n','<br/>')}", cell_left), Paragraph(item["hsn"], cell_style),
            Paragraph(f"₹{item['rate_mt']:,.2f}", cell_style), Paragraph(f"{item['total_wt_mt']:.3f} MT", cell_style), Paragraph(f"₹{item['taxable_value']:,.2f}", cell_style),
            Paragraph(f"₹{item['tax_amt']:,.2f}", cell_style), Paragraph(f"₹{item['gross_amount']:,.2f}", cell_style)
        ])
        
    start_tot_idx = len(table_content)
    table_content.append(["", "", "", "", "", Paragraph("<b>Taxable Amount:</b>", cell_style), "", Paragraph(f"₹{data['taxable_amount']:,.2f}", cell_style)])
    table_content.append(["", "", "", "", "", Paragraph("<b>IGST 18.0%:</b>", cell_style), "", Paragraph(f"₹{data['igst']:,.2f}", cell_style)])
    table_content.append(["", "", "", "", "", Paragraph("<b>Total:</b>", cell_style), "", Paragraph(f"<b>₹{data['grand_total']:,.2f}</b>", cell_style)])
    
    billing_table = Table(table_content, colWidths=[25, 125, 55, 60, 50, 75, 75, 75])
    billing_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f5f5f5')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1, start_tot_idx-1), 0.5, colors.HexColor('#999999')),
        ('GRID', (5, start_tot_idx), (-1, -1), 0.5, colors.HexColor('#999999')),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(billing_table)
    story.append(Spacer(1, 10))
    
    story.append(Paragraph(f"<b>Total Amount (in words):</b> {data['total_words']}", meta_style))
    story.append(Spacer(1, 15))
    
    # 🔒 Width Fixed: Sum of columns = 540 total point width balance
    hsn_headers = [Paragraph("HSN/SAC", hdr_style), Paragraph("Taxable Value", hdr_style), Paragraph("Integrated Tax Rate", hdr_style), Paragraph("Integrated Tax Amount", hdr_style), Paragraph("Total Tax Amount", hdr_style)]
    hsn_content = [hsn_headers]
    
    for hsn_code, vals in data["hsn_map"].items():
        hsn_content.append([
            Paragraph(hsn_code, cell_style), Paragraph(f"₹{vals['taxable_value']:,.2f}", cell_style),
            Paragraph("18%", cell_style), Paragraph(f"₹{vals['tax_amount']:,.2f}", cell_style), Paragraph(f"₹{vals['tax_amount']:,.2f}", cell_style)
        ])
    hsn_content.append([Paragraph("<b>TOTAL</b>", cell_style), Paragraph(f"<b>₹{data['taxable_amount']:,.2f}</b>", cell_style), Paragraph("", cell_style), Paragraph(f"<b>₹{data['igst']:,.2f}</b>", cell_style), Paragraph(f"<b>₹{data['igst']:,.2f}</b>", cell_style)])
    
    hsn_table = Table(hsn_content, colWidths=[100, 110, 100, 110, 120])
    hsn_table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f5f5f5')), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#999999')), ('PADDING', (0,0), (-1,-1), 4)]))
    story.append(hsn_table)
    story.append(Spacer(1, 20))
    
    # 🔒 Width Fixed: [320, 220] = 540 total point width balance
    footer_data = [
        [Paragraph("<b>Bank Details:</b><br/>Bank: <b>YES BANK</b><br/>Account #: <b>667899992222445</b><br/>IFSC: <b>YESBBIN4567</b><br/>Branch: <b>Kodihalli</b>", meta_style),
         Paragraph(f"For <b>{data['src_name']}</b><br/><br/><br/><br/><b>Authorized Signatory</b>", ParagraphStyle('RText', parent=meta_style, alignment=2))]
    ]
    footer_table = Table(footer_data, colWidths=[320, 220])
    footer_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#bbbbbb')), ('PADDING', (0,0), (-1,-1), 6)]))
    story.append(footer_table)
    
    doc.build(story)
    return pdf_filename

# Document Trigger
st.markdown("---")
st.subheader("📥 Step 4: Invoice Assembly Panel")

invoice_payload = {
    "invoice_no": str(invoice_serial_no), "start_date": invoice_date_input.strftime("%d %b %Y"), "end_date": due_date_input.strftime("%d %b %Y"),
    "place_of_supply": str(place_of_supply), "src_name": str(src_name), "src_tagline": str(src_tagline), "src_address": str(src_address),
    "src_gstin": str(src_gstin), "src_mobile": str(src_mobile), "src_email": str(src_email), "bill_name": str(bill_name),
    "bill_contact_person": str(bill_contact_person), "bill_address": str(bill_address), "bill_gstin": str(bill_gstin),
    "bill_mobile": str(bill_mobile), "ship_address": str(ship_addr_str), "line_items": line_items_payload,
    "taxable_amount": total_taxable_subtotal, "igst": total_tax_sum, "grand_total": grand_invoice_total,
    "total_words": invoice_total_words, "hsn_map": hsn_summary_map
}

if st.button("🚀 Compile Print-Ready GST Commercial Invoice PDF", use_container_width=True):
    with st.spinner("Generating document layers..."):
        try:
            generated_file_path = generate_invoice_pdf_file(invoice_payload)
            with open(generated_file_path, "rb") as pdf_file:
                st.download_button(
                    label="📥 Download Official Job-Work GST Invoice PDF",
                    data=pdf_file,
                    file_name=f"Invoice_{invoice_serial_no}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            st.success("🎉 GST Commercial Tax Invoice compiled successfully! Click download above.")
        except Exception as gen_err:
            st.error(f"❌ Compilation crash: {str(gen_err)}")
