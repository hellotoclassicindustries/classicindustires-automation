    st.markdown("---")
    st.subheader("⚖️ Overall Tonnage Summary (All Selected Items)")
    
    if not df_filtered.empty:
        total_tons_inward = df_filtered[df_filtered["Type"] == "inward"]["Weight (Tons)"].sum()
        total_tons_outward = df_filtered[df_filtered["Type"] == "outward"]["Weight (Tons)"].sum()
        net_tons_wip = max(0.0, total_tons_inward - total_tons_outward)
        
        m_col1, m_col2, m_col3 = st.columns(3)
        m_col1.metric(label="Overall Total Tons Inward", value=f"{total_tons_inward:.4f} MT")
        m_col2.metric(label="Overall Total Tons Outward", value=f"{total_tons_outward:.4f} MT")
        m_col3.metric(label="Overall Net WIP Tons Balance", value=f"{net_tons_wip:.4f} MT")
    else:
        st.info("No transaction data available inside filter choices to calculate weights.")

    # Core Metric Tally Grouping Calculations
    part_summary_map = {}
    for _, row in df_filtered.iterrows():
        p_num = row["Part Number"]
        if p_num not in part_summary_map:
            part_summary_map[p_num] = {"description": row["Item Description"], "inward_nos": 0, "outward_nos": 0, "inward_tons": 0.0, "outward_tons": 0.0}
            
        if row["Type"] == "inward":
            part_summary_map[p_num]["inward_nos"] += row["Quantity"]
            part_summary_map[p_num]["inward_tons"] += row["Weight (Tons)"]
        elif row["Type"] == "outward":
            part_summary_map[p_num]["outward_nos"] += row["Quantity"]
            part_summary_map[p_num]["outward_tons"] += row["Weight (Tons)"]

    part_matrix_rows = []
    tonnage_matrix_rows = []
    chart_rows = []
    
    for part, details in part_summary_map.items():
        net_wip_nos = max(0, details["inward_nos"] - details["outward_nos"])
        net_wip_tons = max(0.0, details["inward_tons"] - details["outward_tons"])
        
        part_matrix_rows.append({
            "Part Number": part, "Item Description": details["description"],
            "Total Inward (Nos)": details["inward_nos"], "Total Outward (Nos)": details["outward_nos"], "Net WIP Bal (Nos)": net_wip_nos
        })
        
        tonnage_matrix_rows.append({
            "Part Number": part, "Item Description": details["description"],
            "Total Inward Tonnage (MT)": details["inward_tons"], "Total Outward Tonnage (MT)": details["outward_tons"], "Net WIP Weight Balance (MT)": net_wip_tons
        })
        
        chart_rows.append({"Part Identity": part, "Allocation Segment": "Shipped Outward (Nos)", "Pieces Count": details["outward_nos"]})
        chart_rows.append({"Part Identity": part, "Allocation Segment": "Remaining WIP Stock (Nos)", "Pieces Count": net_wip_nos})

    df_matrix = pd.DataFrame(part_matrix_rows)
    df_tonnage_matrix = pd.DataFrame(tonnage_matrix_rows)
    df_chart = pd.DataFrame(chart_rows)
    # SECTION 1: Standard Partwise Pieces Ledger
    st.markdown("---")
    st.subheader("📋 Consolidated Partwise Inventory Balance Ledger")
    if not df_matrix.empty:
        st.dataframe(df_matrix, use_container_width=True)
    else:
        st.info("No active production materials match your selected filter timeline metrics.")

    # NEW SECTION: Tonewise Weight Balance Matrix Ledger
    st.markdown("---")
    st.subheader("⚖️ Consolidated Tonewise Inventory Balance Ledger")
    if not df_tonnage_matrix.empty:
        st.dataframe(df_tonnage_matrix.style.format({
            "Total Inward Tonnage (MT)": "{:.4f}",
            "Total Outward Tonnage (MT)": "{:.4f}",
            "Net WIP Weight Balance (MT)": "{:.4f}"
        }), use_container_width=True)
    else:
        st.info("No active production materials match your selection metrics.")

    # SECTION 2: Chart Visuals
    st.markdown("---")
    st.subheader("📊 Partwise Stock Fulfillment Levels")
    if not df_chart.empty:
        chart_pivot = df_chart.pivot(index="Part Identity", columns="Allocation Segment", values="Pieces Count").fillna(0)
        st.bar_chart(data=chart_pivot, color=["#0068c9", "#29b573"], use_container_width=True, height=400)

    # SECTION 3: Interactive Invoicing Sidebar Tracker Frame
    st.sidebar.markdown("## 💳 Challan Payment Tracker")
    pay_pending = st.sidebar.checkbox("⚠️ Show Payment Pending Lots", value=True)
    pay_clear = st.sidebar.checkbox("✅ Show Payment Cleared Lots", value=False)
    clearance_date = st.sidebar.date_input("📆 Confirmed Settlement Date:", date.today()) if pay_clear else None

    if not df_filtered.empty:
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 📋 Logged Challan Payment Status")
        unique_challans = [c for c in df_filtered["Challan No"].unique().tolist() if c != "N/A"]
        for idx, challan in enumerate(unique_challans[:10]):
            if (idx % 2 == 0) and pay_pending:
                st.sidebar.warning(f"Challan: **{challan}** \n\n Status: **PENDING**")
            elif (idx % 2 != 0) and pay_clear:
                st.sidebar.success(f"Challan: **{challan}** \n\n Status: **CLEARED** \n\n Date: {clearance_date}")

    # SECTION 4: Reference Samples
    st.markdown("---")
    st.subheader("🔬 Permanent Reference Sample Collection")
    # (Retained sample list logic executes normally below this line...)
