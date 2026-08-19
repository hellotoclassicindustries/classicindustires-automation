import streamlit as st
import pandas as pd
from supabase import create_client, Client

# Initialize Secure Supabase Target Connections
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

def load_filtered_ledger_data():
    """
    Fetches raw transactional records from your Supabase staging table.
    Filters out rows that have been flagged as hidden (Is Validated = FALSE).
    """
    try:
        response = supabase.table("staging_ledger") \
            .select("date, entry_type, challan_no, part_number, ref_challan_no, description, remarks_notes, qty_nos, vehicle_no, eway_bill, gross_total, source_filename") \
            .eq("is_visible_on_dashboard", True) \
            .order("date", desc=True) \
            .execute()
            
        return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"🚨 Cloud database connection failure: {str(e)}")
        return pd.DataFrame()

# Set up Dashboard Grid Layout Presentation
st.set_page_config(page_title="ClassicIndustries | Daily Ledger", layout="wide")
st.title("📊 ClassicIndustries Live Operational Ledger")
st.markdown("---")

df = load_filtered_ledger_data()

if not df.empty:
    # Rename matching data configurations elegantly for layout presentation
    df.columns = [
        "Transaction Date", "Movement Type", "Challan Number", "Part Number", 
        "Reference Lot Link", "Master Description", "Item Remarks/Variants", 
        "Quantity (Nos)", "Vehicle Number", "Eway Bill", "Gross Total (₹)", "Source Document File"
    ]
    
    # Render Data Matrix Summary Cards
    total_qty = int(df["Quantity (Nos)"].sum())
    total_value = float(df["Gross Total (₹)"].sum())
    
    kpi_col1, kpi_col2, kpi_col3 = st.columns(3)
    kpi_col1.metric("📦 Total Quantity Managed", f"{total_qty:,} Nos")
    kpi_col2.metric("💰 Consolidated Ledger Gross", f"₹ {total_value:,.2f}")
    kpi_col3.metric("📂 Tracked Source Documents", f"{df['Source Document File'].nunique()} Active PDFs")
    st.markdown("---")
    
    # Interactive Table Filters
    search_query = st.text_input("🔍 Search ledger by Challan, Part, Lot Link, or Source File:")
    if search_query:
        df = df[
            df["Challan Number"].str.contains(search_query, case=False, na=False) |
            df["Part Number"].str.contains(search_query, case=False, na=False) |
            df["Reference Lot Link"].str.contains(search_query, case=False, na=False) |
            df["Source Document File"].str.contains(search_query, case=False, na=False)
        ]

    # Render data grid dataframe securely across elements
    st.dataframe(
        df, 
        use_container_width=True,
        column_config={
            "Gross Total (₹)": st.column_config.NumberColumn(format="₹ %.2f"),
            "Transaction Date": st.column_config.DateColumn(format="YYYY-MM-DD")
        }
    )
else:
    st.info("No active entries are currently authorized for visibility display on this dashboard view.")
