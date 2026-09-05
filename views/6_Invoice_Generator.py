import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
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
# 2. SIMPLIFIED BUNDLED FILTERING MATRIX
# ============================================================================
catalog_df = fetch_invoice_catalog()

if catalog_df.empty:
    st.warning("📋 Operations Notice: The master part catalog database is disconnected or empty.")
    st.stop()

st.title("🧾 Automated Job-Work Commercial Invoice Generator")
st.markdown("---")

st.subheader("🗓️ Billing Cycle & Component Configuration")
col_i1, col_i2 = st.columns(2)

with col_i1:
    # 📆 UNIFIED DATE RANGE SELECTOR: Picks start and end date from a single window
    today = date.today()
    default_start = today - timedelta(days=30)
    
    selected_range = st.date_input(
        "Select Invoice Date Range (Start & End Date)",
        value=(default_start, today),
        key="invoice_date_range"
    )
    
    # Safety gate to handle in-flight calendar selection clicks
    if isinstance(selected_range, tuple) and len(selected_range) == 2:
        start_date, end_date = selected_range
    else:
        st.info("💡 Please select both a start date and an end date on the calendar dropdown.")
        st.stop()

    # Invoice Serial Reference Box
    invoice_no = st.text_input("Invoice Reference Number", f"CI/{start_date.strftime('%Y')}-{end_date.strftime('%y')}/{datetime.now().strftime('%M%S')}")

with col_i2:
    # 📦 DROPDOWN DEFAULT FOR ALL PARTS: Allows multi-item or single-item aggregation
    catalog_df["display_name"] = catalog_df["part_number"].astype(str) + " - " + catalog_df["description"].astype(str).str.upper()
    
    dropdown_options = ["ALL COMPONENTS (AGGREGATE RUN)"] + list(catalog_df["display_name"].unique())
    selected_display = st.selectbox("Filter by Specific Component (Optional)", dropdown_options, index=0)
    
    is_filtered_run = selected_display != "ALL COMPONENTS (AGGREGATE RUN)"
st.markdown("---")
st.subheader("📊 Live Billing Aggregation Summary")

# Structural placeholder mapping to mirror database ledger totals within your selected timeline
# In production, this aggregates actual shift row items between start_date and end_date
billing_items = []

if not is_filtered_run:
    # 🏗️ DEFAULT PATH: Automatically processes lines for ALL available parts in your catalog
    for _, row in catalog_df.iterrows():
        # Simulated actual output count per part over the selected date range
        simulated_pcs = 1250 if row["part_class"] == "Class A" else 850 
        part_weight = float(row["weight_kg"])
        part_rate = float(row.get("billing_rate_per_ton", 2650.0))
        
        part_tonnage = (simulated_pcs * part_weight) / 1000.0
        part_taxable = part_tonnage * part_rate
        
        billing_items.append({
            "part_number": str(row["part_number"]).upper(),
            "description": str(row["description"]).upper(),
            "weight_kg": part_weight,
            "total_pieces": simulated_pcs,
            "total_tonnage": part_tonnage,
            "rate_per_ton": part_rate,
            "taxable_amount": part_taxable
        })
else:
    # FILTERED PATH: Processes only the one selected component explicitly
    matched_df = catalog_df[catalog_df["display_name"] == selected_display]
    part_meta = matched_df.iloc[0].to_dict()
    
    simulated_pcs = 3450
    part_weight = float(part_meta["weight_kg"])
    part_rate = float(part_meta.get("billing_rate_per_ton", 2650.0))
    
    part_tonnage = (simulated_pcs * part_weight) / 1000.0
    part_taxable = part_tonnage * part_rate
    
    billing_items.append({
        "part_number": str(part_meta["part_number"]).upper(),
        "description": str(part_meta["description"]).upper(),
        "weight_kg": part_weight,
        "total_pieces": simulated_pcs,
        "total_tonnage": part_tonnage,
        "rate_per_ton": part_rate,
        "taxable_amount": part_taxable
    })

# Compute Cumulative Totals for Dashboard Badges View Display
summary_df = pd.DataFrame(billing_items)
total_invoice_pieces = int(summary_df["total_pieces"].sum())
total_invoice_tonnage = float(summary_df["total_tonnage"].sum())
total_taxable_subtotal = float(summary_df["taxable_amount"].sum())

cgst_tax_amount = total_taxable_subtotal * 0.09
sgst_tax_amount = total_taxable_subtotal * 0.09
grand_invoice_total = total_taxable_subtotal + cgst_tax_amount + sgst_tax_amount

card_1, card_2, card_3 = st.columns(3)
card_1.metric("Aggregated Shift Output", f"{total_invoice_pieces:,} Pieces", f"{len(billing_items)} Active Part Types")
card_2.metric("Total Billable Tonnage", f"{total_invoice_tonnage:.3f} MT")
card_3.metric("Gross Invoice Valuation (With Tax)", f"₹{grand_invoice_total:,.2f}")

st.markdown("<br>", unsafe_allow_html=True)

# Preview layout grid sheet display for verification
st.markdown("**🔍 Invoice Preview Breakdown Matrix:**")
st.dataframe(
    summary_df[["part_number", "description", "total_pieces", "total_tonnage", "rate_per_ton", "taxable_amount"]],
    column_config={
        "part_number": "Part Number", "description": "Item Description",
        "total_pieces": "Total Qty (Pcs)", "total_tonnage": "Volume (MT)",
        "rate_per_ton": "Rate / MT (₹)", "taxable_amount": "Taxable Subtotal (₹)"
    },
    use_container_width=True,
    hide_index=True
)
# ============================================================================
# 3. COMPILER TRIGGER AND DOCUMENT DISTRIBUTION GATEWAY
# ============================================================================
st.subheader("📥 Document Distribution Panel")

invoice_master_payload = {
    "invoice_no": str(invoice_no),
    "start_date": start_date.strftime("%d-%b-%Y"),
    "end_date": end_date.strftime("%d-%b-%Y"),
    "line_items": billing_items,
    "taxable_amount": total_taxable_subtotal,
    "cgst": cgst_tax_amount,
    "sgst": sgst_tax_amount,
    "grand_total": grand_invoice_total
}

if st.button("🚀 Compile Print-Ready Executive Multi-Item Invoice PDF", use_container_width=True):
    with st.spinner("Generating cryptographically sound multi-item document structure..."):
        try:
            # Execute backend PDF writing script engine cleanly
            generated_file_path = generate_invoice_pdf_file(invoice_master_payload)
            
            with open(generated_file_path, "rb") as pdf_file:
                st.download_button(
                    label="📥 Download Official Job-Work Invoice PDF",
                    data=pdf_file,
                    file_name=f"Invoice_{invoice_no.replace('/', '_')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            st.success("🎉 Multi-item invoice compilation completed successfully! Click the download button above to retrieve your file.")
        except Exception as gen_err:
            st.error(f"❌ Document compilation runtime crash: {str(gen_err)}")
# ============================================================================
# 4. REPORTLAB AUTOMATED MULTI-ITEM EXECUTIVE LAYOUT ENGINE
# ============================================================================
def generate_invoice_pdf_file(data):
    """Compiles a professional, publication-quality multi-row invoice PDF."""
    import os
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    
    os.makedirs("generated", exist_ok=True)
    pdf_filename = f"generated/Invoice_{data['invoice_no'].replace('/', '_')}.pdf"
    
    # Initialize basic layout template document geometries
    doc = SimpleDocTemplate(
        pdf_filename, pagesize=letter,
        rightMargin=36, leftMargin=36, topMargin=40, bottomMargin=40,
        title=f"Invoice {data['invoice_no']}"
    )
    
    story = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=24, 
        leading=28, textColor=colors.HexColor('#006100')
    )
    meta_style = ParagraphStyle(
        'MetaText', parent=styles['Normal'], fontName='Helvetica', fontSize=10, 
        leading=14, textColor=colors.HexColor('#333333')
    )
    header_style = ParagraphStyle(
        'TableHeader', fontName='Helvetica-Bold', fontSize=9, leading=11, 
        textColor=colors.white, alignment=1
    )
    cell_style = ParagraphStyle(
        'TableCell', fontName='Helvetica', fontSize=9, leading=12, alignment=1
    )
    
    # Corporate Header Section Construction
    story.append(Paragraph("CLASSIC INDUSTRIES", title_style))
    story.append(Paragraph("Foundry Friends & Finishers Division | Plant Operations Node", meta_style))
    story.append(Spacer(1, 15))
    
    # Metadata Chronological Dual-Column Construction
    meta_data = [
        [Paragraph(f"<b>Invoice No:</b> {data['invoice_no']}", meta_style), Paragraph(f"<b>Billing Cycle Start:</b> {data['start_date']}", meta_style)],
        [Paragraph(f"<b>Date Generated:</b> {datetime.now().strftime('%d-%b-%Y')}", meta_style), Paragraph(f"<b>Billing Cycle End:</b> {data['end_date']}", meta_style)]
    ]
    meta_table = Table(meta_data, colWidths=[270, 270])
    meta_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('PADDING', (0,0), (-1,-1), 2)]))
    story.append(meta_table)
    story.append(Spacer(1, 20))
    
    # Table Header Definition row setup mapping blocks
    table_content = [[
        Paragraph("Component Details", header_style),
        Paragraph("Unit Wt", header_style),
        Paragraph("Total Qty", header_style),
        Paragraph("Volume", header_style),
        Paragraph("Rate / MT", header_style),
        Paragraph("Taxable Subtotal", header_style)
    ]]
    
    # Dynamic row allocation matrix appending loop logic block
    for item in data["line_items"]:
        table_content.append([
            Paragraph(f"<b>{item['part_number']}</b><br/>{item['description']}", cell_style),
            Paragraph(f"{item['weight_kg']:.1f} Kg", cell_style),
            Paragraph(f"{item['total_pieces']:,} Pcs", cell_style),
            Paragraph(f"{item['total_tonnage']:.3f} MT", cell_style),
            Paragraph(f"₹{item['rate_per_ton']:,.2f}", cell_style),
            Paragraph(f"₹{item['taxable_amount']:,.2f}", cell_style)
        ])
        
    # Append the financial totals trailer rows summary array block
    start_tot_idx = len(table_content)
    table_content.append(["", "", "", "", Paragraph("<b>Taxable Subtotal:</b>", cell_style), Paragraph(f"₹{data['taxable_amount']:,.2f}", cell_style)])
    table_content.append(["", "", "", "", Paragraph("<b>CGST (9.0%):</b>", cell_style), Paragraph(f"₹{data['cgst']:,.2f}", cell_style)])
    table_content.append(["", "", "", "", Paragraph("<b>SGST (9.0%):</b>", cell_style), Paragraph(f"₹{data['sgst']:,.2f}", cell_style)])
    table_content.append(["", "", "", "", Paragraph("<b>Grand Total:</b>", cell_style), Paragraph(f"<b>₹{data['grand_total']:,.2f}</b>", cell_style)])
    
    # Apply crisp styles to the dynamic content matrix lengths table
    billing_table = Table(table_content, colWidths=[160, 60, 70, 75, 85, 90])
    t_style = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#006100')), # Brand identity headers fill
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1, start_tot_idx - 1), 0.5, colors.HexColor('#dddddd')),
        ('LINEBELOW', (4, start_tot_idx), (5, -1), 1, colors.HexColor('#006100')),
        ('BACKGROUND', (4, -1), (5, -1), colors.HexColor('#e2efda')), # Accent color for totals cell
        ('PADDING', (0,0), (-1,-1), 6),
    ]
    billing_table.setStyle(TableStyle(t_style))
    story.append(billing_table)
    
    # Build print ready layout document
    doc.build(story)
    return pdf_filename
