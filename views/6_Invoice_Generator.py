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
        st.error("❌ Missing Infrastructure Secrets Configuration.")
        return None

supabase = init_supabase_connection()

@st.cache_data(ttl=5)
def fetch_invoice_catalog():
    if not supabase: return pd.DataFrame()
    try:
        res = supabase.table("vw_cntr_part_master").select("*").execute()
        return pd.DataFrame(res.data)
    except Exception as e: return pd.DataFrame()

@st.cache_data(ttl=5)
def fetch_corporate_master_directory():
    if not supabase: return pd.DataFrame()
    try:
        res = supabase.table("cntr_corporate_master").select("*").eq("is_violated", False).order("company_name").execute()
        return pd.DataFrame(res.data)
    except Exception as e: return pd.DataFrame()

catalog_df = fetch_invoice_catalog()
corporate_df = fetch_corporate_master_directory()

if catalog_df.empty:
    st.warning("📋 Operations Notice: The master part catalog database view is disconnected.")
    st.stop()
# ============================================================================
# 2. DATE BOUNDS & CLIENT SELECTOR FILTERS
# ============================================================================
st.subheader("🗓️ Date Bounds & Component Scope")
col_i1, col_i2 = st.columns(2)

with col_i1:
    today = date.today()
    selected_range = st.date_input("Select Invoice Date Range", value=(today - timedelta(days=30), today), key="invoice_date_range")
    start_date, end_date = selected_range if (isinstance(selected_range, tuple) and len(selected_range) == 2) else (today - timedelta(days=30), today)

with col_i2:
    catalog_df["display_name"] = catalog_df["part_number"].astype(str) + " - " + catalog_df["description"].astype(str).str.upper()
    dropdown_options = ["ALL RUNNABLE COMPONENTS"] + list(catalog_df["display_name"].unique())
    selected_display = st.selectbox("Filter Summary by Component (Optional)", dropdown_options, index=0)
    is_filtered_run = selected_display != "ALL RUNNABLE COMPONENTS"

st.markdown("---")
st.subheader("🏢 Step 1: Corporate Entity Address Profiles")
col_s1, col_s2 = st.columns(2)

with col_s1:
    st.markdown("**🛡️ Seller / Foundry Details**")
    owner_df = corporate_df[corporate_df["cmp_number"] == "own01"]
    o_row = owner_df.iloc[0].to_dict() if not owner_df.empty else {}
    src_name = st.text_input("Seller Legal Name", o_row.get("company_name", "CLASSIC INDUSTRIES"))
    src_tagline = st.text_input("Tagline", "Manufacturer & Supplier of Cast Iron Components")
    src_address = st.text_area("Full Factory Address", o_row.get("billing_address", "KH-267, Ghaziabad, UP"))
    src_gstin = st.text_input("Seller GSTIN", o_row.get("gstin", "09ENRPS7521A1ZN"))
    src_mobile = st.text_input("Seller Mobile", o_row.get("contact_number", "9999999999"))
    src_email = st.text_input("Seller Email", o_row.get("email_address", "billing@classicindustries.in"))

with col_s2:
    st.markdown("**🏢 Buyer / Client Profile Auto-Loader**")
    buyer_only_df = corporate_df[corporate_df["profile_type"].str.lower() != "owner"]
    if not buyer_only_df.empty:
        selected_client_name = st.selectbox("Select Customer from Cloud Registry", list(buyer_only_df["company_name"].unique()))
        c_row = buyer_only_df[buyer_only_df["company_name"] == selected_client_name].iloc[0].to_dict()
        bill_name = st.text_input("Buyer Name", str(c_row.get("company_name", "")))
        bill_gstin = st.text_input("Buyer GSTIN", str(c_row.get("gstin", "")))
        bill_address = st.text_area("Buyer Billing Address", str(c_row.get("billing_address", "")))
        bill_person = st.text_input("Attn / Contact Person", str(c_row.get("contact_person", "Operations Head")))
        bill_no = st.text_input("Buyer Contact Number", str(c_row.get("contact_number", "")))
        raw_hsn_string = str(c_row.get("hsn_number", "998349"))
        base_pos = f"{str(c_row.get('state_code','00')).zfill(2)}-{str(c_row.get('state_name','UNKNOWN')).upper()}"
    else:
        bill_name = st.text_input("Buyer Name", "REVENT METALCAST LIMITED")
        bill_gstin = st.text_input("Buyer GSTIN", "08AAACA8504G2ZW")
        bill_address = st.text_area("Buyer Billing Address", "SPA-1195, RIICO Industrial Area, Bhiwadi, Rajasthan")
        bill_person = st.text_input("Attn", "Contact_Person")
        bill_no = st.text_input("Buyer Phone", "9999999999")
        raw_hsn_string = "998349"
        base_pos = "08-RAJASTHAN"
st.markdown("<br>", unsafe_allow_html=True)
st.subheader("🚛 Step 2: Logistic Matrix & Delivery Directives")
col_s3, col_s4 = st.columns(2)

with col_s3:
    same_as_billing = st.checkbox("Shipping Destination matches Billing Profile Address", value=True)
    ship_addr_override = st.text_area("Consignee Delivery Location", value=bill_address if same_as_billing else bill_address)
    place_of_supply = st.text_input("Place of Supply State Code Display", value=base_pos)

with col_s4:
    invoice_hsn_input = st.text_input("Active Billing HSN/SAC Codes (Comma Separated Override)", value=raw_hsn_string)
    invoice_date_input = st.date_input("Invoice Date", today)
    invoice_serial_no = st.text_input("Invoice Serial Code Number", f"INV-{datetime.now().strftime('%M%S')}")

st.markdown("---")
st.subheader("⚙️ Step 3: Production Ingestion Verification Breakdown")

line_items_payload = []
hsn_summary_map = {}

parsed_hsn_list = [x.strip() for x in invoice_hsn_input.split(",") if x.strip()]

# 🚀 THE CRITICAL AXIS FIX: Declared idx via enumerate to eliminate compilation errors
for idx, record in catalog_df.iterrows():
    p_num = str(record["part_number"])
    if is_filtered_run and p_num.upper() not in selected_display.upper(): continue
        
    sim_qty = 289 if "933" in p_num else 669
    p_desc = str(record["description"]).upper()
    p_weight = float(record["weight_kg"])
    p_rate = float(record.get("rate_per_ton", 2650.0))
    if p_rate <= 0: p_rate = 2650.00 if "933" in p_num else 3300.00
    
    # Priority extraction rule logic handles fallbacks cleanly
    hsn_code = parsed_hsn_list[idx] if (len(parsed_hsn_list) > 0 and idx < len(parsed_hsn_list)) else str(record.get("hsn_sac", "998349")).strip()
    
    total_wt_mt = (sim_qty * p_weight) / 1000.0
    taxable_val = total_wt_mt * p_rate
    tax_amt = taxable_val * 0.18
    
    item_node = {
        "item_no": len(line_items_payload) + 1, "part_number": p_num, "description": p_desc, "hsn": hsn_code,
        "qty": sim_qty, "wt_pc": p_weight, "total_wt_mt": total_wt_mt, "rate_mt": p_rate,
        "taxable_value": taxable_val, "tax_amt": tax_amt, "gross_amount": taxable_val + tax_amt
    }
    line_items_payload.append(item_node)
    
    if hsn_code not in hsn_summary_map: hsn_summary_map[hsn_code] = {"taxable_value": 0.0, "tax_amount": 0.0}
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

st.markdown("🔍 **Live On-Screen Print Preview Layout Matrix:**")
html_preview_box = f"""
<div style="background-color: #ffffff; padding: 20px; border: 1px solid #333333; color: #000000; font-family: sans-serif; font-size: 12px;">
    <div style="text-align: center; font-weight: bold; font-size: 15px; border-bottom: 1.5px solid #000000; padding-bottom: 5px; margin-bottom: 10px;">TAX INVOICE</div>
    <div style="display: flex; border: 1px solid #999999; margin-bottom: 10px;">
        <div style="width: 50%; padding: 8px; border-right: 1px solid #999999;">
            <b style="font-size: 14px; color: #002b49;">{src_name}</b><br/>{src_address.replace('\n', '<br/>')}<br/><b>GSTIN:</b> {src_gstin}
        </div>
        <div style="width: 50%; padding: 8px;">
            <b>Invoice #:</b> {invoice_serial_no}<br/><b>Dated:</b> {invoice_date_input.strftime('%d-%b-%Y')}<br/><b>Place of Supply:</b> {place_of_supply}
        </div>
    </div>
    <div style="display: flex; border: 1px solid #999999; margin-bottom: 15px;">
        <div style="width: 50%; padding: 8px; border-right: 1px solid #999999; background-color: #fafafa;">
            <b>{bill_name}</b><br/>{bill_address.replace('\n', '<br/>')}<br/><b>GSTIN:</b> {bill_gstin}
        </div>
        <div style="width: 50%; padding: 8px; background-color: #f7faf6;">
            <b>CONSIGNEE (SHIP TO)</b><br/>{ship_addr_override.replace('\n', '<br/>')}
        </div>
    </div>
</div>
"""
st.markdown(html_preview_box, unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)
st.dataframe(summary_df[["item_no", "part_number", "description", "hsn", "qty", "wt_pc", "total_wt_mt", "rate_mt", "taxable_value"]], use_container_width=True, hide_index=True)
# ============================================================================
# 4. REPORTLAB AUTOMATED TAX INVOICE COMPILER ENGINE
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
    
    top_table = Table([[Paragraph(f"<b>{data['src_name']}</b><br/>{data['src_address'].replace('\n','<br/>')}<br/><b>GSTIN:</b> {data['src_gstin']}", meta_style), Paragraph(f"<b>Invoice #:</b> {data['invoice_no']}<br/><b>Invoice Date:</b> {data['start_date']}<br/><b>Place of Supply:</b> {data['place_of_supply']}", meta_style)]], colWidths=[320, 220])
    top_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#999999')), ('PADDING', (0,0), (-1,-1), 6)]))
    story.append(top_table)
    story.append(Spacer(1, 10))
    
    addr_table = Table([[Paragraph(f"<b>Buyer (Bill to):</b><br/><b>{data['bill_name']}</b><br/>{data['bill_address'].replace('\n','<br/>')}<br/><b>GSTIN:</b> {data['bill_gstin']}", meta_style), Paragraph(f"<b>Consignee (Ship to):</b><br/>{data['ship_address'].replace('\n','<br/>')}", meta_style)]], colWidths=[270, 270])
    addr_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#999999')), ('PADDING', (0,0), (-1,-1), 6)]))
    story.append(addr_table)
    story.append(Spacer(1, 15))
    
    table_content = [[Paragraph("Sl No.", hdr_style), Paragraph("Description of Goods", hdr_style), Paragraph("HSN/SAC", hdr_style), Paragraph("Quantity", hdr_style), Paragraph("Weight Per Pieces", hdr_style), Paragraph("Total Weight In Ton", hdr_style), Paragraph("Per Ton Rate", hdr_style), Paragraph("Amount", hdr_style)]]
    for idx, item in enumerate(data["line_items"]):
        table_content.append([Paragraph(str(idx+1), cell_style), Paragraph(f"<b>{item['part_number']}</b><br/>{item['description']}", cell_left), Paragraph(item["hsn"], cell_style), Paragraph(f"{item['qty']:,}", cell_style), Paragraph(f"{item['wt_pc']:.1f} KG", cell_style), Paragraph(f"{item['total_wt_mt']:.4f}", cell_style), Paragraph(f"{int(item['rate_mt'])}", cell_style), Paragraph(f"Rs. {item['taxable_value']:,.2f}", cell_style)])
        
    start_tot_idx = len(table_content)
    table_content.append(["", Paragraph("<b>Total</b>", cell_left), "", Paragraph(f"<b>{total_invoice_pieces}</b>", cell_style), Paragraph("", cell_style), Paragraph(f"<b>{data['total_invoice_weight_mt']:.5f}</b>", cell_style), "", Paragraph(f"<b>Rs. {data['taxable_amount']:,.2f}</b>", cell_style)])
    table_content.append(["", "", "", "", "", "", Paragraph("<b>Taxable Value:</b>", cell_style), Paragraph(f"{data['taxable_amount']:,.2f}", cell_style)])
    table_content.append(["", "", "", "", "", "", Paragraph("<b>IGST 18%:</b>", cell_style), Paragraph(f"{data['igst']:,.2f}", cell_style)])
    table_content.append(["", "", "", "", "", "", Paragraph("<b>Total:</b>", cell_style), Paragraph(f"<b>Rs. {data['grand_total']:,.2f}</b>", cell_style)])
    
    billing_table = Table(table_content, colWidths=[30, 140, 50, 45, 45, 60, 50, 70])
    billing_table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f5f5f5')), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('GRID', (0,0), (-1, start_tot_idx), 0.5, colors.HexColor('#999999')), ('GRID', (6, start_tot_idx+1), (-1, -1), 0.5, colors.HexColor('#999999')), ('PADDING', (0,0), (-1,-1), 5)]))
    story.append(billing_table)
    story.append(Spacer(1, 10))
    
    hsn_content = [[Paragraph("HSN/SAC", hdr_style), Paragraph("Taxable Value", hdr_style), Paragraph("Integrated Tax Rate", hdr_style), Paragraph("Integrated Tax Amount", hdr_style), Paragraph("Total Tax Amount", hdr_style)]]
    for hsn_code, vals in data["hsn_map"].items():
        hsn_content.append([Paragraph(hsn_code, cell_style), Paragraph(f"Rs. {vals['taxable_value']:,.2f}", cell_style), Paragraph("18%", cell_style), Paragraph(f"Rs. {vals['tax_amount']:,.2f}", cell_style), Paragraph(f"Rs. {vals['tax_amount']:,.2f}", cell_style)])
    hsn_content.append([Paragraph("<b>TOTAL</b>", cell_style), Paragraph(f"Rs. {data['taxable_amount']:,.2f}", cell_style), Paragraph("", cell_style), Paragraph(f"Rs. {data['igst']:,.2f}", cell_style), Paragraph(f"Rs. {data['igst']:,.2f}", cell_style)])
    
    hsn_table = Table(hsn_content, colWidths=[100, 100, 80, 130, 130])
    hsn_table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f5f5f5')), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#999999')), ('PADDING', (0,0), (-1,-1), 4)]))
    story.append(hsn_table)
    story.append(Spacer(1, 15))
    
    footer_table = Table([[Paragraph("<b>Bank Details:</b><br/>Bank Name : <b>Indian Bank</b><br/>A/c No. : <b>8383467708</b><br/>IFS Code: <b>IDIB000P618</b>", meta_style), Paragraph(f"for <b>{data['src_name']}</b><br/><br/><br/><b>Authorised Signatory</b>", ParagraphStyle('RText', parent=meta_style, alignment=2))]], colWidths=[290, 250])
    footer_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#bbbbbb')), ('PADDING', (0,0), (-1,-1), 6)]))
    story.append(footer_table)
    
    doc.build(story)
    return pdf_filename

st.markdown("---")
st.subheader("📥 Step 4: Invoice Assembly Panel")

if st.button("🚀 Compile Print-Ready GST Commercial Invoice PDF", use_container_width=True):
    try:
        f_path = generate_invoice_pdf_file(invoice_payload)
        with open(f_path, "rb") as f:
            st.download_button(label="📥 Download Official Job-Work GST Invoice PDF", data=f, file_name=f"Invoice_{invoice_serial_no}.pdf", mime="application/pdf", use_container_width=True)
        st.success("🎉 Multi-item tax invoice compiled successfully! Click download above.")
    except Exception as e: st.error(f"❌ Compilation crash: {str(e)}")
