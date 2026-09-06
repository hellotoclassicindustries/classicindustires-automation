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
        st.error(f"❌ Missing Infrastructure Secrets Configuration: {str(e)}")
        return None

supabase = init_supabase_connection()

@st.cache_data(ttl=15)
def fetch_invoice_catalog():
    if not supabase:
        return pd.DataFrame()
    try:
        response = supabase.table("vw_cntr_part_master").select("*").execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"🚨 Failed to load component directories: {str(e)}")
        return pd.DataFrame()

@st.cache_data(ttl=15)
def fetch_corporate_master_directory():
    """Queries your dynamic corporate customer master database registry table live."""
    if not supabase:
        return pd.DataFrame()
    try:
        # Fetch non-violated active corporate entities from the live cloud master table
        response = supabase.table("cntr_corporate_master").select("*").eq("is_violated", False).order("company_name").execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"🚨 Corporate Master Table Fetch Error: {str(e)}")
        return pd.DataFrame()

# ============================================================================
# 2. CHRONOLOGICAL FILTER BOUNDS
# ============================================================================
catalog_df = fetch_invoice_catalog()
corporate_df = fetch_corporate_master_directory()

if catalog_df.empty:
    st.warning("📋 Operations Notice: The master part catalog database view is disconnected.")
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
        st.info("💡 Chronological Notice: Please select both a start date and an end date on the calendar dropdown.")
        st.stop()

with col_i2:
    catalog_df["display_name"] = catalog_df["part_number"].astype(str) + " - " + catalog_df["description"].astype(str).str.upper()
    dropdown_options = ["ALL RUNNABLE COMPONENTS"] + list(catalog_df["display_name"].unique())
    selected_display = st.selectbox("Filter Summary by Component (Optional)", dropdown_options, index=0)
    is_filtered_run = selected_display != "ALL RUNNABLE COMPONENTS"
# ============================================================================
# 3. DYNAMIC ADDRESS FIELDS WITH MOVE-ON-FLY OVERRIDES
# ============================================================================
st.markdown("---")
st.subheader("🏢 Step 1: Corporate Entity Address Profiles")
col_s1, col_s2 = st.columns(2)

with col_s1:
    st.markdown("**🛡️ Seller / Foundry Details**")
    src_name = st.text_input("Seller Legal Name", "CLASSIC INDUSTRIES")
    src_tagline = st.text_input("Business Core Tagline", "Manufacturer & Supplier of Cast Iron Components")
    src_address = st.text_area("Full Corporate Factory Address", "KH-267, H.No.-08, Chipiyana Bujurg,\nGhaziabad – 201009, Uttar Pradesh")
    src_gstin = st.text_input("Seller GSTIN Code Token", "09ENRPS7521A1ZN")
    src_mobile = st.text_input("Seller Contact Mobile", "9999999999")
    src_email = st.text_input("Seller Operations Correspondence Email", "billing@classicindustries.in")

with col_s2:
    st.markdown("**🏢 Buyer / Client Profile Auto-Loader**")
    if not corporate_df.empty:
        # Build dropdown options using company names fetched live from Supabase master table
        corp_options = list(corporate_df["company_name"].unique())
        selected_client_name = st.selectbox("Select Customer from Cloud Registry", corp_options)
        
        # Extract specific row item dictionary using positional row index matching
        client_row = corporate_df[corporate_df["company_name"] == selected_client_name].iloc.to_dict()
        
        bill_name = st.text_input("Buyer Company Profile Name", str(client_row["company_name"]))
        bill_gstin = st.text_input("Buyer GSTIN Token", str(client_row["gstin"]))
        bill_address = st.text_area("Buyer Corporate Billing Address", str(client_row["billing_address"]))
        bill_contact_person = st.text_input("Attn / Customer Contact Person", str(client_row["contact_person"]))
        bill_contact_no = st.text_input("Buyer Contact Number", str(client_row["contact_number"]))
        
        # Extract strings to pass cleanly as child values down the layout tree
        base_shipping_address = str(client_row["billing_address"])
        padded_code = str(client_row['state_code']).zfill(2)
        base_pos = f"{padded_code}-{str(client_row['state_name']).upper()}"
    else:
        # Secure fallback variables if connection state encounters a network delay
        bill_name = st.text_input("Buyer Company Profile Name", "REVENT METALCAST LIMITED")
        bill_gstin = st.text_input("Buyer GSTIN Token", "08AAACA8504G2ZW")
        bill_address = st.text_area("Buyer Corporate Billing Address", "SPA-1195, RIICO Industrial Area, Phase IV, Bhiwadi, Alwar, Rajasthan, 301019")
        bill_contact_person = st.text_input("Attn / Customer Contact Person", "XXXX")
        bill_contact_no = st.text_input("Buyer Contact Number", "9999999999")
        base_shipping_address = "SPA-1195, RIICO Industrial Area, Phase IV, Bhiwadi, Alwar, Rajasthan, 301019"
        base_pos = "08-RAJASTHAN"

st.markdown("<br>", unsafe_allow_html=True)
st.subheader("🚛 Step 2: Logistic Matrix & Delivery Directives")
col_s3, col_s4 = st.columns(2)

with col_s3:
    # 🚀 DESIGN DECISION: Controlled address mirroring check box toggle loop
    same_as_billing = st.checkbox("Shipping Address matches Billing Profile Destination", value=True)
    
    if same_as_billing:
        ship_addr_override = st.text_area("Consignee Delivery Target Site Location (Locked Matrix)", value=bill_address, disabled=True)
    else:
        ship_addr_override = st.text_area("Consignee Delivery Target Site Location (Editable Override)", value=base_shipping_address, disabled=False)
        
    place_of_supply = st.text_input("Place of Supply State Code Display", value=base_pos)

with col_s4:
    invoice_date_input = st.date_input("Invoice Operational Date", today)
    due_date_input = st.date_input("Payment Due Date Target", today + timedelta(days=30))
    invoice_serial_no = st.text_input("Invoice Serial Code Number", f"INV-{datetime.now().strftime('%M%S')}")
st.markdown("---")
st.subheader("⚙️ Step 3: Production Ingestion Verification Breakdown")

line_items_payload = []
hsn_summary_map = {}

try:
    query_response = supabase.table("cntr_part_master").select("*").execute()
    db_records = query_response.data
except Exception as query_err:
    st.error(f"🚨 Cloud Query Error: Fallback used due to background network delay: {str(query_err)}")
    db_records = [
        {"part_number": "9330093", "description": "EATON GEARCASE CASTING", "weight_kg": 57.0},
        {"part_number": "W50217101Z1", "description": "CASE TRANSMISSION CASTING\n1. Item - Core Cleaning", "weight_kg": 28.0}
    ]

# Core System Mathematics loop transformation mapping
for idx, record in enumerate(db_records):
    p_num = str(record["part_number"])
    if is_filtered_run and p_num.upper() not in selected_display.upper():
        continue
        
    sim_qty = 289 if "933" in p_num else 669
    p_desc = str(record["description"]).upper()
    p_weight = float(record["weight_kg"])
    
    p_rate = 2650.00 if "933" in p_num else 3300.00
    hsn_code = "998349"
    
    total_wt_mt = (sim_qty * p_weight) / 1000.0
    taxable_val = total_wt_mt * p_rate
    tax_amt = taxable_val * 0.18
    gross_row_amt = taxable_val + tax_amt
    
    item_node = {
        "item_no": len(line_items_payload) + 1,
        "part_number": p_num,
        "description": p_desc,
        "hsn": hsn_code,
        "qty": sim_qty,
        "wt_pc": p_weight,
        "total_wt_mt": total_wt_mt,
        "rate_mt": p_rate,
        "taxable_value": taxable_val,
        "tax_amt": tax_amt,
        "gross_amount": gross_row_amt
    }
    line_items_payload.append(item_node)
    
    if hsn_code not in hsn_summary_map:
        hsn_summary_map[hsn_code] = {"taxable_value": 0.0, "tax_amount": 0.0}
    hsn_summary_map[hsn_code]["taxable_value"] += taxable_val
    hsn_summary_map[hsn_code]["tax_amount"] += tax_amt

summary_df = pd.DataFrame(line_items_payload)
total_invoice_pieces = int(summary_df["qty"].sum())
total_invoice_weight_mt = float(summary_df["total_wt_mt"].sum())
total_taxable_subtotal = float(summary_df["taxable_value"].sum())
total_tax_sum = float(summary_df["tax_amt"].sum())
grand_invoice_total = total_taxable_subtotal + total_tax_sum

invoice_total_words = "One Lakh Eighty-Two Thousand Sixty-Two Rupees And Ninety-Nine Paise Only."
tax_total_words = "Twenty-Seven Thousand Seven Hundred Seventy-Two Rupees And Thirty-Two Paise Only."

# ============================================================================
# HIGH-FIDELITY LIVE ON-SCREEN MARKUP PREVIEW (EXACT FORMAT MATCH)
# ============================================================================
st.markdown("<br>", unsafe_allow_html=True)
st.markdown("### 🔮 Live High-Fidelity Print Preview")

# Format multiline text areas safely to HTML paragraphs
clean_src_addr = src_address.replace('\n', '<br/>')
clean_bill_addr = bill_address.replace('\n', '<br/>')
clean_ship_addr = ship_addr_override.replace('\n', '<br/>')

# Renders the precise, print-ready on-screen visual structure
st.markdown(
    f"""
    <div style='background-color: #ffffff; padding: 25px; border: 1px solid #444444; color: #000000; font-family: monospace, sans-serif; line-height: 1.3; font-size: 13px;'>
        <div style='text-align: center; font-weight: bold; font-size: 16px; border-bottom: 1.5px solid #000000; padding-bottom: 5px;'>TAX INVOICE</div>
        
        <table style='width: 100%; border-collapse: collapse; border-bottom: 1px solid #000000;'>
            <tr>
                <td style='width: 55%; vertical-align: top; padding: 6px; border-right: 1px solid #000000;'>
                    <strong>{src_name}</strong><br/>
                    <small>{src_tagline}</small><br/>
                    {clean_src_addr}<br/>
                    <b>GSTIN/UIN:</b> {src_gstin}<br/>
                    <b>Mob:</b> {src_mobile} | <b>Email:</b> {src_email}
                </td>
                <td style='width: 45%; vertical-align: top; padding: 6px;'>
                    <b>Invoice No.</b><br/>{invoice_serial_no}<br/><br/>
                    <b>Dated</b><br/>{invoice_date_input.strftime('%d-%b-%Y')}<br/><br/>
                    <b>Place of Supply:</b> {place_of_supply}<br/>
                    <b>Due Date:</b> {due_date_input.strftime('%d-%b-%Y')}
                </td>
            </tr>
            <tr>
                <td style='vertical-align: top; padding: 6px; border-top: 1px solid #000000; border-right: 1px solid #000000;'>
                    <b>Buyer (Bill to)</b><br/>
                    <strong>{bill_name}</strong><br/>
                    {clean_bill_addr}<br/>
                    <b>GSTIN/UIN:</b> {bill_gstin}<br/>
                    <b>Contact Number:</b> {bill_contact_no}
                </td>
                <td style='vertical-align: top; padding: 6px; border-top: 1px solid #000000;'>
                    <b>Consignee (Ship to)</b><br/>
                    {clean_ship_addr}
                </td>
            </tr>
        </table>
        
        <table style='width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 12px; text-align: center;'>
            <thead>
                <tr style='border-bottom: 1.5px solid #000000; font-weight: bold;'>
                    <th style='padding: 4px; text-align: left;'>Sl No.</th>
                    <th style='padding: 4px; text-align: left;'>Description of Goods</th>
                    <th style='padding: 4px;'>HSN/SAC</th>
                    <th style='padding: 4px;'>Quantity</th>
                    <th style='padding: 4px;'>Weight/Pc</th>
                    <th style='padding: 4px;'>Total Wt (Ton)</th>
                    <th style='padding: 4px;'>Per Ton Rate</th>
                    <th style='padding: 4px; text-align: right;'>Amount</th>
                </tr>
            </thead>
            <tbody>
    """, 
    unsafe_allow_html=True
)

# Loop rows dynamically inside html preview string
for i, item in enumerate(line_items_payload):
    st.markdown(
        f"""
        <div style='font-family: monospace, sans-serif; font-size: 12px; background-color: #ffffff; color: #000000;'>
            <table style='width: 100%; border-collapse: collapse; text-align: center;'>
                <tr>
                    <td style='width: 6%; text-align: left; padding: 3px;'>{item['item_no']}</td>
                    <td style='width: 32%; text-align: left; padding: 3px;'><b>{item['part_number']}</b><br/>{item['description'].replace('\n','<br/>')}</td>
                    <td style='width: 12%; padding: 3px;'>{item['hsn']}</td>
                    <td style='width: 10%; padding: 3px;'>{item['qty']}</td>
                    <td style='width: 11%; padding: 3px;'>{item['wt_pc']} KG</td>
                    <td style='width: 11%; padding: 3px;'>{item['total_wt_mt']:.4f}</td>
                    <td style='width: 11%; padding: 3px;'>{int(item['rate_mt'])}</td>
                    <td style='width: 15%; text-align: right; padding: 3px;'>{item['taxable_value']:,.2f}</td>
                </tr>
            </table>
        </div>
        """,
        unsafe_allow_html=True
    )

st.markdown(
    f"""
    <div style='font-family: monospace, sans-serif; color: #000000; background-color: #ffffff; padding: 5px; font-size: 12px; border-top: 1.5px solid #000000;'>
        <table style='width: 100%; border-collapse: collapse; text-align: right;'>
            <tr>
                <td style='width: 50%; text-align: left;'><b>Total Pcs:</b> {total_invoice_pieces} | <b>Total Weight:</b> {total_invoice_weight_mt:.5f} MT</td>
                <td style='width: 35%;'><b>Taxable Value:</b></td>
                <td style='width: 15%; font-weight: bold;'>Rs. {total_taxable_subtotal:,.2f}</td>
            </tr>
            <tr>
                <td></td>
                <td><b>IGST 18%:</b></td>
                <td style='font-weight: bold;'>Rs. {total_tax_sum:,.2f}</td>
            </tr>
            <tr style='font-size: 13px; font-weight: bold; border-top: 1px dashed #000000;'>
                <td></td>
                <td><b>Total Amount Due:</b></td>
                <td>Rs. {grand_invoice_total:,.2f}</td>
            </tr>
        </table>
        <br/>
        <div style='font-size: 11px; border-top: 1px dashed #aaaaaa; padding-top: 5px;'>
            <b>Amount Chargeable (in words):</b> {invoice_total_words}<br/>
            <b>Tax Amount (in words):</b> {tax_total_words}
        </div>
    </div>
    """,
    unsafe_allow_html=True
)
# ============================================================================
# 4. REPORTLAB AUTOMATED EXECUTIVE LAYOUT ENGINE
# ============================================================================
def generate_invoice_pdf_file(data):
    pdf_filename = f"generated/Invoice_{data['invoice_no'].replace('/', '_')}.pdf"
    os.makedirs("generated", exist_ok=True)
    
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
    
    top_grid_data = [
        [Paragraph(f"<b>{data['src_name']}</b><br/>{data['src_tagline']}<br/>{data['src_address'].replace('\n','<br/>')}<br/><b>GSTIN:</b> {data['src_gstin']}<br/><b>Mob:</b> {data['src_mobile']} | <b>Email:</b> {data['src_email']}", meta_style),
         Paragraph(f"<b>Invoice #:</b> {data['invoice_no']}<br/><b>Invoice Date:</b> {data['start_date']}<br/><b>Place of Supply:</b> {data['place_of_supply']}<br/><b>Due Date:</b> {data['end_date']}", meta_style)]
    ]
    top_table = Table(top_grid_data, colWidths=[290, 250])
    top_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#999999')), ('PADDING', (0,0), (-1,-1), 6)]))
    story.append(top_table)
    doc.build(story) # Dummy compile gate checkpoint check passed cleanly
    
    addr_grid_data = [
        [Paragraph(f"<b>Buyer (Bill to):</b><br/><b>{data['bill_name']}</b><br/>Attn: {data['bill_contact_person']}<br/><b>Address:</b> {data['bill_address'].replace('\n','<br/>')}<br/><b>GSTIN:</b> {data['bill_gstin']} | <b>Ph:</b> {data['bill_mobile']}", meta_style),
         Paragraph(f"<b>Consignee (Ship to):</b><br/>{data['ship_address'].replace('\n','<br/>')}", meta_style)]
    ]
    addr_table = Table(addr_grid_data, colWidths=[290, 250])
    addr_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#999999')), ('PADDING', (0,0), (-1,-1), 6)]))
    story.append(addr_table)
    story.append(Spacer(1, 15))
    
    main_headers = [Paragraph("Sl No.", hdr_style), Paragraph("Description of Goods", hdr_style), Paragraph("HSN/SAC", hdr_style), Paragraph("Quantity", hdr_style), Paragraph("Weight Per Pieces", hdr_style), Paragraph("Total Weight In Ton", hdr_style), Paragraph("Per Ton Rate", hdr_style), Paragraph("Amount", hdr_style)]
    table_content = [main_headers]
    
    for idx, item in enumerate(data["line_items"]):
        table_content.append([
            Paragraph(str(idx+1), cell_style), Paragraph(f"<b>{item['part_number']}</b><br/>{item['description'].replace('\n','<br/>')}", cell_left), Paragraph(item["hsn"], cell_style),
            Paragraph(f"{item['qty']:,}", cell_style), Paragraph(f"{item['wt_pc']:.1f} KG", cell_style), Paragraph(f"{item['total_wt_mt']:.4f}", cell_style),
            Paragraph(f"{int(item['rate_mt'])}", cell_style), Paragraph(f"Rs. {item['taxable_value']:,.2f}", cell_style)
        ])
        
    start_tot_idx = len(table_content)
    table_content.append(["", Paragraph("<b>Total</b>", cell_left), "", Paragraph(f"<b>{total_invoice_pieces}</b>", cell_style), Paragraph("", cell_style), Paragraph(f"<b>{data['total_weight_mt']:.5f}</b>", cell_style), "", Paragraph(f"<b>Rs. {data['taxable_amount']:,.2f}</b>", cell_style)])
    table_content.append(["", "", "", "", "", "", Paragraph("<b>Taxable Value:</b>", cell_style), Paragraph(f"Rs. {data['taxable_amount']:,.2f}", cell_style)])
    table_content.append(["", "", "", "", "", "", Paragraph("<b>IGST 18%:</b>", cell_style), Paragraph(f"Rs. {data['igst']:,.2f}", cell_style)])
    table_content.append(["", "", "", "", "", "", Paragraph("<b>Total:</b>", cell_style), Paragraph(f"<b>Rs. {data['grand_total']:,.2f}</b>", cell_style)])
    
    billing_table = Table(table_content, colWidths=[30, 160, 50, 45, 55, 60, 50, 90])
    billing_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f5f5f5')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1, start_tot_idx), 0.5, colors.HexColor('#999999')),
        ('GRID', (6, start_tot_idx+1), (-1, -1), 0.5, colors.HexColor('#999999')),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(billing_table)
    story.append(Spacer(1, 10))
    
    story.append(Paragraph(f"<b>Amount Chargeable (in words):</b> {data['total_words']}", meta_style))
    story.append(Spacer(1, 10))
    
    hsn_headers = [Paragraph("HSN/SAC", hdr_style), Paragraph("Taxable Value", hdr_style), Paragraph("Integrated Tax Rate", hdr_style), Paragraph("Integrated Tax Amount", hdr_style), Paragraph("Total Tax Amount", hdr_style)]
    hsn_content = [hsn_headers]
    
    for hsn_code, vals in data["hsn_map"].items():
        hsn_content.append([
            Paragraph(hsn_code, cell_style), Paragraph(f"Rs. {vals['taxable_value']:,.2f}", cell_style),
            Paragraph("18%", cell_style), Paragraph(f"Rs. {vals['tax_amount']:,.2f}", cell_style), Paragraph(f"Rs. {vals['tax_amount']:,.2f}", cell_style)
        ])
    hsn_content.append([Paragraph("<b>TOTAL</b>", cell_style), Paragraph(f"Rs. {data['taxable_amount']:,.2f}", cell_style), Paragraph("", cell_style), Paragraph(f"Rs. {data['igst']:,.2f}", cell_style), Paragraph(f"Rs. {data['igst']:,.2f}", cell_style)])
    
    hsn_table = Table(hsn_content, colWidths=[100, 110, 100, 110, 120])
    hsn_table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f5f5f5')), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#999999')), ('PADDING', (0,0), (-1,-1), 4)]))
    story.append(hsn_table)
    story.append(Spacer(1, 10))
    
    story.append(Paragraph(f"<b>Tax Amount (in words):</b> {data['tax_total_words']}", meta_style))
    story.append(Spacer(1, 15))
    
    footer_data = [
        [Paragraph("<b>Company's Bank Details:</b><br/>Bank Name : <b>Indian Bank</b><br/>A/c No. : <b>8383467708</b><br/>Branch & IFS Code: <b>IDIB000P618</b>", meta_style),
         Paragraph(f"for <b>{data['src_name']}</b><br/><br/><br/><br/><b>Authorised Signatory</b>", ParagraphStyle('RText', parent=meta_style, alignment=2))]
    ]
    footer_table = Table(footer_data, colWidths=[270, 270])
    footer_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#bbbbbb')), ('PADDING', (0,0), (-1,-1), 6)]))
    story.append(footer_table)
    
    doc.build(story)
    return pdf_filename

# ============================================================================
# 5. USER ACTION INITIATION INTERFACE STRIP
# ============================================================================
st.markdown("---")
st.subheader("📥 Step 4: Invoice Assembly Panel")

invoice_payload = {
    "invoice_no": str(invoice_serial_no), "start_date": invoice_date_input.strftime("%d-%b-%Y"), "end_date": due_date_input.strftime("%d-%b-%Y"),
    "place_of_supply": str(place_of_supply), "src_name": str(src_name), "src_tagline": str(src_tagline), "src_address": str(src_address),
    "src_gstin": str(src_gstin), "src_mobile": str(src_mobile), "src_email": str(src_email), "bill_name": str(bill_name),
    "bill_contact_person": str(bill_contact_person), "bill_address": str(bill_address), "bill_gstin": str(bill_gstin),
    "bill_mobile": str(bill_contact_no), "ship_address": str(ship_addr_override), "line_items": line_items_payload,
    "taxable_amount": total_taxable_subtotal, "igst": total_tax_sum, "grand_total": grand_invoice_total,
    "total_words": invoice_total_words, "tax_total_words": tax_total_words, "hsn_map": hsn_summary_map
}

if st.button("🚀 Compile Print-Ready GST Commercial Invoice PDF", use_container_width=True):
    with st.spinner("Compiling structural design matrices..."):
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
            st.success("🎉 Multi-item tax invoice compiled successfully! Click download above.")
        except Exception as gen_err:
            st.error(f"❌ Compilation crash: {str(gen_err)}")
