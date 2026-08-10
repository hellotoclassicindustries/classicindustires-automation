import streamlit as st
import pandas as pd
import altair as alt

# 🔒 RECONCILIATION FIREWALL: Ensure user is logged in before mounting confidential data
if not st.session_state.get("authenticated", False):
    st.title("🔒 Restricted Corporate Node")
    st.error("Access Denied. This terminal view contains confidential operational ledger values.")
    st.info("💡 Please use the sidebar authentication menu panel to log in first.")
    st.stop()

# Grab the live, cached database network stack from global state session variables
supabase = st.session_state.supabase

st.title("📊 Stock Master Balance Ledger")
st.caption("Classic Industries — Foundry Friends & Finishers Division")
st.markdown("---")

# --------------------------------------------------------------------------
# 📡 DATA PIPELINE LAYER: FETCH SECURE ACTIVE METRICS FROM CLOUD
# --------------------------------------------------------------------------
try:
    with st.spinner("Extracting real-time floor inventory profiles..."):
        # SOFT-DELETE GATEWAY: Fetch all data but exclude any items marked FALSE or unchecked
        response = (
            supabase.table("staging_ledger")
            .select("*")
            .eq("is_validated", True)  # <-- Soft-delete protection filter active
            .execute()
        )
        
    raw_data = response.data
    df = pd.DataFrame(raw_data)
    
    if df.empty:
        st.info("ℹ️ No active inventory ledger metrics currently recorded on the shop floor.")
    else:
        # Standardize data parameters for numeric precision calculations
        df["qty_nos"] = pd.to_numeric(df["qty_nos"], errors="coerce").fillna(0)
        df["date"] = pd.to_datetime(df["date"])
        
        # Calculate dynamic WIP balances by separating transaction types
        inward_df = df[df["entry_type"].str.lower() == "inward"]
        outward_df = df[df["entry_type"].str.lower() == "outward"]
        
        inward_total = inward_df["qty_nos"].sum()
        outward_total = outward_df["qty_nos"].sum()
        current_wip_stock = inward_total - outward_total
        
        # Calculate active production lot metrics
        total_active_batches = df["challan_no"].nunique()
        
        # --------------------------------------------------------------------------
        # 🏢 HIGH-CONTRAST HEADLINE KPI TILES
        # --------------------------------------------------------------------------
        col1, col2 = st.columns(2)
        with col1:
            st.metric(
                label="Total Physical WIP Balance (Nos)", 
                value=f"{int(current_wip_stock):,}"
            )
        with col2:
            st.metric(
                label="Active Manufacturing Lots (Challans)", 
                value=total_active_batches
            )
            
        st.markdown("###")
        
        # --------------------------------------------------------------------------
        # 📈 HIGH-UTILITY VISUALIZATION PANEL: PART BREAKDOWN CHART
        # --------------------------------------------------------------------------
        st.subheader("🍩 Inventory Composition by Part Number")
        
        # Group by part number to see remaining available inventory balance allocations
        part_summary = df.groupby("part_number")["qty_nos"].sum().reset_index()
        
        donut_chart = (
            alt.Chart(part_summary)
            .mark_arc(innerRadius=60, stroke="#fff")
            .encode(
                theta=alt.Theta(field="qty_nos", type="quantitative", title="Total Quantity"),
                color=alt.Color(field="part_number", type="nominal", title="Part Number"),
                tooltip=["part_number", "qty_nos"]
            )
            .properties(width=400, height=300)
        )
        
        st.altair_chart(donut_chart, use_container_width=True)
        st.markdown("---")
        
        # --------------------------------------------------------------------------
        # 📋 WORKFLOW AGING DATA MATRIX
        # --------------------------------------------------------------------------
        st.subheader("📋 Active Work-in-Progress Ledger Entries")
        
        # Sort values cleanly so the newest logs pin to top views automatically
        df_display = df.sort_values(by="date", ascending=False)
        
        # Clean, organized view optimized for shop floor monitoring
        display_cols = ["date", "entry_type", "challan_no", "part_number", "qty_nos", "vehicle_no"]
        
        st.dataframe(
            df_display[display_cols].assign(
                date=df_display["date"].dt.strftime("%Y-%m-%d")
            ), 
            use_container_width=True, 
            hide_index=True
        )

except Exception as e:
    st.error(f"🚨 Network exception fetching ledger parameters from Supabase: {str(e)}")
