import streamlit as st
import pandas as pd
from supabase import create_client

# ============================================================================
# 1. SECURE DATABASE CONNECTION INTEGRATION
# ============================================================================
@st.cache_resource
def init_supabase_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"❌ Missing Streamlit Secrets Configuration: {str(e)}")
        return None

supabase = init_supabase_connection()

@st.cache_data(ttl=60)
def fetch_master_catalog():
    if not supabase:
        return pd.DataFrame()
    try:
        response = supabase.table("vw_cntr_part_master").select("*").execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"🚨 Failed to load part directory: {str(e)}")
        return pd.DataFrame()

# ============================================================================
# 2. DATA INGESTION & UI PARAMETER BLOCKS
# ============================================================================
catalog_df = fetch_master_catalog()

if catalog_df.empty:
    st.warning("📋 Operations Notice: The master part catalog database is empty.")
    st.stop()

st.title("🔮 Job-Work Forecast & Shift Performance Simulator")
st.markdown("---")

st.subheader("📊 Parameter / Input Block")
col_p1, col_p2, col_p3 = st.columns(3)

with col_p1:
    catalog_df["display_name"] = catalog_df["part_number"].astype(str) + " - " + catalog_df["description"].astype(str).str.upper()
    display_options = catalog_df["display_name"].unique()
    selected_display = st.selectbox("Select Component (Part Number & Description)", display_options)
    
    # 🚀 THE FIX: Use safe filtering and explicit positional item indexing
    matched_rows = catalog_df[catalog_df["display_name"] == selected_display].to_dict(orient="records")
    
    if len(matched_rows) > 0:
        part_meta = matched_rows[0]
    else:
        st.error("❌ Mapped part data could not be found.")
        st.stop()
        
    weight_kg = float(part_meta["weight_kg"])
    billing_rate_per_ton = float(part_meta["billing_rate_per_ton"])
    
    st.info(f"**Part Number:** {str(part_meta['part_number']).upper()}\n\n"
            f"**Casting Weight:** {weight_kg:.2f} Kg\n\n"
            f"**Weight Class:** {part_meta['part_class']}\n\n"
            f"**Hoist Requirement:** {str(part_meta['handling_requirement']).upper()}")
with col_p2:
    active_jhulas = int(st.number_input("Number of Active Jhula Machines", min_value=1, max_value=10, value=2, step=1))
    active_hours = float(st.number_input("Active Production Hours Per Shift", min_value=1.0, max_value=24.0, value=10.0, step=0.5))
    fixed_labor_payroll = float(st.number_input("Fixed Labor Shift Payroll (₹)", min_value=0.0, value=6400.0))
    variable_labor_per_ton = float(st.number_input("Per-Ton Variable Labor Payout (₹)", min_value=0.0, value=0.0))

with col_p3:
    monthly_factory_bills = float(st.number_input("Total Monthly Factory Bills (₹)", min_value=0.0, value=245000.0))
    slab_pct_input = float(st.number_input("Factory Maintenance Fund Allocation (%)", min_value=0.0, max_value=100.0, value=35.0))
    st.success(f"**Billing Rate Assigned:** ₹{billing_rate_per_ton:,.2f} / Ton")

st.markdown("---")

# ============================================================================
# 3. OPTIONAL DYNAMIC MACHINE COUNTERS INPUT MATRIX
# ============================================================================
st.subheader("🔢 Machine Output Entry Block (Optional)")
st.markdown("*Leave these counts at 0 to view pure Break-Even Forecasting values.*")

j_cols = st.columns(min(active_jhulas, 5))
actual_counts = []

for idx in range(active_jhulas):
    col_selector = j_cols[idx % 5]
    with col_selector:
        pcs = int(st.number_input(
            f"Actual Production Per Hour (Jhula{idx + 1}) (Pieces)", 
            min_value=0, 
            value=0, 
            step=1,
            key=f"jhula_{idx}"
        ))
        actual_counts.append(pcs)

# 🚀 SYSTEM MATHEMATICS RE-CALIBRATION: Evaluates full quantities flawlessly
total_hourly_pieces = sum(actual_counts)
total_shift_pieces = float(total_hourly_pieces * active_hours)
total_shift_tonnage = (total_shift_pieces * weight_kg) / 1000.0
gross_shift_revenue = total_shift_tonnage * billing_rate_per_ton
slab_factor = slab_pct_input / 100.0

is_simulation_mode = total_hourly_pieces > 0
total_variable_labor_cost = total_shift_tonnage * variable_labor_per_ton

has_slab = slab_pct_input > 0
has_bills = monthly_factory_bills > 0
# Core Calculations Matrix
maint_allocation_b = (monthly_factory_bills / 30.0) if has_bills else 0.0
net_margin_ton_b = billing_rate_per_ton - variable_labor_per_ton
min_ton_b = (maint_allocation_b + fixed_labor_payroll) / net_margin_ton_b if net_margin_ton_b > 0 else 0.0
min_pieces_b = (min_ton_b * 1000.0) / weight_kg if weight_kg > 0 else 0.0
total_shift_runtime_units = float(active_jhulas * active_hours)
min_rate_hr_b = min_pieces_b / total_shift_runtime_units if total_shift_runtime_units > 0 else 0.0
net_profit_b = gross_shift_revenue - (maint_allocation_b + fixed_labor_payroll + total_variable_labor_cost)

maint_allocation_d = gross_shift_revenue * slab_factor if has_slab else 0.0
net_margin_ton_d = (billing_rate_per_ton * (1.0 - slab_factor)) - variable_labor_per_ton
min_ton_d = fixed_labor_payroll / net_margin_ton_d if net_margin_ton_d > 0 else 0.0
min_pieces_d = (min_ton_d * 1000.0) / weight_kg if weight_kg > 0 else 0.0
min_rate_hr_d = min_pieces_d / total_shift_runtime_units if total_shift_runtime_units > 0 else 0.0
net_profit_d = gross_shift_revenue - (maint_allocation_d + fixed_labor_payroll + total_variable_labor_cost)

min_ton_payroll_only = fixed_labor_payroll / net_margin_ton_b if net_margin_ton_b > 0 else 0.0
min_pieces_payroll_only = (min_ton_payroll_only * 1000.0) / weight_kg if weight_kg > 0 else 0.0
min_rate_hr_payroll_only = min_pieces_payroll_only / total_shift_runtime_units if total_shift_runtime_units > 0 else 0.0
net_profit_payroll_only = gross_shift_revenue - (fixed_labor_payroll + total_variable_labor_cost)

if has_slab:
    active_model_desc = f"⚡ DYNAMIC VARIABLE SLAB MODEL ACTIVE ({slab_pct_input}%)"
    model_color = "#e2efda"
    border_color = "#006100"
elif has_bills:
    active_model_desc = f"📊 STANDARD FLAT BILLS MODEL ACTIVE (₹{monthly_factory_bills:,.2f}/Mo)"
    model_color = "#f8f9fa"
    border_color = "#595959"
else:
    active_model_desc = "⚠️ STAFF PAYROLL ONLY MODEL ACTIVE (No Factory Overhead Defined)"
    model_color = "#fff2cc"
    border_color = "#d6b656"

# ============================================================================
# 4. LIVE SHIFT FINANCIAL PERFORMANCE VISUALIZATION SUMMARY
# ============================================================================
if is_simulation_mode:
    st.subheader("💵 Live Shift Financial Performance Summary")
    
    if has_bills and has_slab:
        sim_col_b, sim_col_d = st.columns(2)
        with sim_col_b:
            st.markdown("<div style='background-color: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 5px solid #595959; font-weight: bold;'>📊 Standard Model Performance (Col B)</div>", unsafe_allow_html=True)
            st.write(f"**Gross Revenue:** ₹{gross_shift_revenue:,.2f}")
            st.write(f"**Fixed Maintenance Cost:** ₹{maint_allocation_b:,.2f}")
            st.metric("Net Shift Profit (Col B)", f"₹{net_profit_b:,.2f}")
        with sim_col_d:
            st.markdown("<div style='background-color: #e2efda; padding: 15px; border-radius: 8px; border-left: 5px solid #006100; font-weight: bold;'>⚡ Dynamic Slab Performance (Col D)</div>", unsafe_allow_html=True)
            st.write(f"**Gross Revenue:** ₹{gross_shift_revenue:,.2f}")
            st.write(f"**Slab Maintenance Cost:** ₹{maint_allocation_d:,.2f}")
            st.metric("Net Shift Profit (Col D)", f"₹{net_profit_d:,.2f}")
            
    elif has_slab:
        st.markdown(f"<div style='background-color: #e2efda; padding: 15px; border-radius: 8px; border-left: 5px solid #006100; font-weight: bold;'>{active_model_desc}</div>", unsafe_allow_html=True)
        f_col1, f_col2, f_col3 = st.columns(3)
        f_col1.metric("Gross Revenue", f"₹{gross_shift_revenue:,.2f}")
        f_col2.metric("Maint Overhead (Slab)", f"₹{maint_allocation_d:,.2f}")
        f_col3.metric("Net Shift Profit/Loss", f"₹{net_profit_d:,.2f}")
        
    elif has_bills:
        st.markdown(f"<div style='background-color: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 5px solid #595959; font-weight: bold;'>{active_model_desc}</div>", unsafe_allow_html=True)
        f_col1, f_col2, f_col3 = st.columns(3)
        f_col1.metric("Gross Revenue", f"₹{gross_shift_revenue:,.2f}")
        f_col2.metric("Maint Overhead (Flat)", f"₹{maint_allocation_b:,.2f}")
        f_col3.metric("Net Shift Profit/Loss", f"₹{net_profit_b:,.2f}")
        
    else:
        st.markdown(f"<div style='background-color: #fff2cc; padding: 15px; border-radius: 8px; border-left: 5px solid #d6b656; font-weight: bold;'>{active_model_desc}</div>", unsafe_allow_html=True)
        f_col1, f_col2, f_col3 = st.columns(3)
        f_col1.metric("Gross Revenue", f"₹{gross_shift_revenue:,.2f}")
        f_col2.metric("Maint Overhead Cost", "₹0.00")
        f_col3.metric("Net Shift Profit/Loss", f"₹{net_profit_payroll_only:,.2f}")
        
    st.markdown("---")
# ============================================================================
# 5. FORECASTING CAPACITY ENGINE BLOCK
# ============================================================================
st.subheader("🔮 Break-Even Target Forecasting Engine")

if has_bills and has_slab:
    st.markdown("<div style='color: #444444; font-weight: bold; margin-bottom: 15px;'>⚖️ Both Parameters Defined: Comparing Standard vs. Slab Models Side-by-Side</div>", unsafe_allow_html=True)
    left_column, right_column = st.columns(2)
    
    with left_column:
        st.markdown("<div style='background-color: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 5px solid #595959;'><h4 style='margin-top:0;'>📊 Standard Flat Model (Column B)</h4></div>", unsafe_allow_html=True)
        st.write(f"**Net Margin / Ton:** ₹{net_margin_ton_b:,.2f}")
        st.metric("Break-Even Target (Volume)", f"{min_ton_b:.3f} Tons")
        st.metric("Casting Pieces Needed", f"{int(min_pieces_b)} Pcs")
        st.success(f"**Target Floor Pace:** {min_rate_hr_b:.2f} Pcs / Hr / Machine")

    with right_column:
        st.markdown("<div style='background-color: #e2efda; padding: 15px; border-radius: 8px; border-left: 5px solid #006100;'><h4 style='margin-top:0; color: #006100;'>⚡ Dynamic Slab Model (Column D)</h4></div>", unsafe_allow_html=True)
        st.write(f"**Net Margin / Ton:** ₹{net_margin_ton_d:,.2f}")
        st.metric("Break-Even Target (Volume)", f"{min_ton_d:.3f} Tons")
        st.metric("Casting Pieces Needed", f"{int(min_pieces_d)} Pcs")
        st.success(f"**Target Floor Pace:** {min_rate_hr_d:.2f} Pcs / Hr / Machine")

elif has_slab:
    st.markdown("<div style='background-color: #e2efda; padding: 20px; border-radius: 8px; border-left: 6px solid #006100;'>", unsafe_allow_html=True)
    fc1, fc2 = st.columns(2)
    with fc1:
        st.markdown("<h4 style='margin-top:0; color: #006100;'>⚡ Dynamic Variable Slab Model Active</h4>", unsafe_allow_html=True)
        st.write(f"**Net Margin Retained / Ton:** ₹{net_margin_ton_d:,.2f}")
        st.write(f"**Fixed Labor Cost Applied:** ₹{fixed_labor_payroll:,.2f}")
    with fc2:
        st.metric("🎯 Break-Even Target (Volume)", f"{min_ton_d:.3f} Tons")
        st.metric("🎯 Total Casting Pieces Needed", f"{int(min_pieces_d)} Pcs")
        st.success(f"**🚀 Required Floor Pace:** {min_rate_hr_d:.2f} Pcs / Hour / Machine")
    st.markdown("</div>", unsafe_allow_html=True)

elif has_bills:
    st.markdown("<div style='background-color: #f8f9fa; padding: 20px; border-radius: 8px; border-left: 6px solid #595959;'>", unsafe_allow_html=True)
    fc1, fc2 = st.columns(2)
    with fc1:
        st.markdown("<h4 style='margin-top:0; color: #333333;'>📊 Standard Flat Bills Model Active</h4>", unsafe_allow_html=True)
        st.write(f"**Net Margin Retained / Ton:** ₹{net_margin_ton_b:,.2f}")
        st.write(f"**Flat Daily Overhead Cost:** ₹{maint_allocation_b:,.2f}")
        st.write(f"**Fixed Labor Cost Applied:** ₹{fixed_labor_payroll:,.2f}")
    with fc2:
        st.metric("🎯 Break-Even Target (Volume)", f"{min_ton_b:.3f} Tons")
        st.metric("🎯 Total Casting Pieces Needed", f"{int(min_pieces_b)} Pcs")
        st.success(f"**🚀 Required Floor Pace:** {min_rate_hr_b:.2f} Pcs / Hour / Machine")
    st.markdown("</div>", unsafe_allow_html=True)

else:
    st.markdown("<div style='background-color: #fff2cc; padding: 20px; border-radius: 8px; border-left: 6px solid #d6b656;'>", unsafe_allow_html=True)
    fc1, fc2 = st.columns(2)
    with fc1:
        st.markdown("<h4 style='margin-top:0; color: #7f6000;'>⚠️ Staff Payroll Only Model Active</h4>", unsafe_allow_html=True)
        st.write(f"**Net Margin Retained / Ton:** ₹{net_margin_ton_b:,.2f}")
        st.write(f"**Fixed Labor Cost Applied:** ₹{fixed_labor_payroll:,.2f}")
    with fc2:
        st.metric("🎯 Break-Even Target (Volume)", f"{min_ton_payroll_only:.3f} Tons")
        st.metric("🎯 Total Casting Pieces Needed", f"{int(min_pieces_payroll_only)} Pcs")
        st.success(f"**🚀 Required Floor Pace:** {min_rate_hr_payroll_only:.2f} Pcs / Hour / Machine")
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("---")

with st.expander("📝 View Active Costing Hierarchy Equations & Operational Formulas"):
    st.markdown("### 🏭 Global Production Equations")
    st.latex(r"\text{Total Pieces Processed} = \sum (\text{Actual Pieces Per Jhula}) \times \text{Active Production Hours}")
    st.latex(r"\text{Total Tonnage (MT)} = \frac{\text{Total Pieces} \times \text{Casting Weight (Kg)}}{1000}")
    st.latex(r"\text{Gross Revenue (₹)} = \text{Total Tonnage} \times \text{Billing Rate Per Ton}")
    st.markdown("---")
    if has_bills:
        st.markdown("### 📊 Standard Flat Bills Model Formulas (Column B)")
        st.latex(r"\text{Flat Daily Overhead (₹)} = \frac{\text{Total Monthly Factory Bills}}{30}")
        st.latex(r"\text{Net Margin / Ton (Col B)} = \text{Billing Rate} - \text{Variable Labor Per Ton}")
        st.latex(r"\text{Break Even Tonnage (Col B)} = \frac{\text{Flat Daily Overhead} + \text{Fixed Labor Shift Payroll}}{\text{Net Margin / Ton (Col B)}}")
        st.latex(r"\text{Pieces Required (Col B)} = \frac{\text{Break Even Tonnage (Col B)} \times 1000}{\text{Casting Weight (Kg)}}")
        st.latex(r"\text{Target Floor Pace (Col B)} = \frac{\text{Pieces Required (Col B)}}{\text{Active Jhulas} \times \text{Active Production Hours}}")
        st.markdown("---")
    if has_slab:
        st.markdown("### ⚡ Dynamic Variable Slab Model Formulas (Column D)")
        st.latex(r"\text{Variable Maintenance Cost (₹)} = \text{Gross Revenue} \times \text{Allocation \%}")
        st.latex(r"\text{Net Margin / Ton (Col D)} = [\text{Billing Rate} \times (1 - \text{Allocation \%})] - \text{Variable Labor Per Ton}")
        st.latex(r"\text{Break Even Tonnage (Col D)} = \frac{\text{Fixed Labor Shift Payroll}}{\text{Net Margin / Ton (Col D)}}")
        st.latex(r"\text{Pieces Required (Col D)} = \frac{\text{Break Even Tonnage (Col D)} \times 1000}{\text{Casting Weight (Kg)}}")
        st.latex(r"\text{Target Floor Pace (Col D)} = \frac{\text{Pieces Required (Col D)}}{\text{Active Jhulas} \times \text{Active Production Hours}}")
