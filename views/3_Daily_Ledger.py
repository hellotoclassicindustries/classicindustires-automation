import streamlit as st
import pandas as pd

# 🔒 RECONCILIATION FIREWALL: Ensure user is logged in before mounting confidential data
if not st.session_state.get("authenticated", False):
    st.title("🔒 Restricted Corporate Node")
    st.error("Access Denied. This terminal view contains confidential operational ledger values.")
    st.info("💡 Please use the sidebar authentication menu panel to log in first.")
    st.stop()

# Grab the live, cached database network stack from global state session variables
supabase = st.session_state.supabase

st.title("📝 Daily Transaction Register")
st.caption("Chronological Audit Ledger Portal & Row Data Archiver")
st.markdown("---")

# --------------------------------------------------------------------------
# 📡 DATA PIPELINE LAYER: CHRONOLOGICAL SEARCH PORTAL
# --------------------------------------------------------------------------
try:
    with st.spinner("Compiling chronological transaction matrix loops..."):
        # AUTOMATICALLY MASKS CANCELLATIONS: Isolates only clean, validated rows
        response = (
            supabase.table("staging_ledger")
            .select("*")
            .eq("is_validated", True)  # <-- Soft-delete protection gate active
            .order("date", desc=True)   # Pins newest entries to the top view automatically
            .execute()
        )
    
    ledger_data = response.data
    df_ledger = pd.DataFrame(ledger_data)
    
    if df_ledger.empty:
        st.info("ℹ️ Transaction log registers are currently clear.")
    else:
        # 🔍 DYNAMIC SEARCH INTERACTIVE CONSOLE
        search_query = st.text_input(
            "🔍 Dynamic Ledger Search Console", 
            placeholder="Type Part Number, Description, or Challan No to filter instantly..."
        )
        
        # Apply filter strings dynamically across multiple dataset targets simultaneously
        if search_query:
            df_filtered = df_ledger[
                df_ledger["part_number"].str.contains(search_query, case=False, na=False) |
                df_ledger["challan_no"].str.contains(search_query, case=False, na=False) |
                df_ledger["description"].str.contains(search_query, case=False, na=False) |
                df_ledger["entry_type"].str.contains(search_query, case=False, na=False)
            ]
        else:
            df_filtered = df_ledger
            
        st.markdown("###")
        
        # Display the interactive grid canvas with streamlined visibility
        st.dataframe(
            df_filtered, 
            use_container_width=True, 
            hide_index=True,
            column_order=[
                "date", "entry_type", "challan_no", "part_number", 
                "description", "qty_nos", "vehicle_no", "eway_bill", "gross_total"
            ]
        )
        
        # --------------------------------------------------------------------------
        # 📥 OPERATIONAL DATA EXPORTER PANEL
        # --------------------------------------------------------------------------
        st.markdown("---")
        st.subheader("📥 Data Export Utility")
        st.caption("Download the filtered data selection below straight into a localized Excel/CSV spreadsheet format.")
        
        # Convert active grid state directly to whole UTF-8 binary streams
        csv_payload = df_filtered.to_csv(index=False).encode('utf-8')
        
        st.download_button(
            label="📥 Export Filtered Ledger Spreadsheet (.CSV)",
            data=csv_payload,
            file_name="ClassicIndustries_Filtered_Ledger.csv",
            mime="text/csv",
            use_container_width=False
        )

except Exception as e:
    st.error(f"🚨 Register transmission failure fetching profiles from Supabase: {str(e)}")
