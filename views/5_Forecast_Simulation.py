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
    st.warning("📋 Operations Notice: The master part catalog database is empty or disconnected.")
    st.stop()

st.title("🔮 Job-Work Forecast & Shift Performance Simulator")
st.markdown("---")

st.subheader("📊 Parameter / Input Block")
col_p1, col_p2, col_p3 = st.columns(3)

with col_p1:
    catalog_df["display_name"] = catalog_df["part_number"].astype(str) + " - " + catalog_df["description"].astype(str).str.upper()
    display_options = catalog_df["display_name"].unique()
    selected_display = st.selectbox("Select Component (Part Number & Description)", display_options)
    
    # 🚀 THE CRITICAL CORRECTION: Append .iloc[0] to treat the output securely as a single dictionary data row!
    part_meta = catalog_df[catalog_df["display_name"] == selected_display].iloc[0]
    weight_kg = float(part_meta["weight_kg"])
    billing_rate_per_ton = float(part_meta["billing_rate_per_ton"])
    
    st.info(f"**Part Number:** {str(part_meta['part_number']).upper()}\n\n"
            f"**Casting Weight:** {weight_kg:.2f} Kg\n\n"
            f"**Weight Class:** {part_meta['part_class']}\n\n"
            f"**Hoist Requirement:** {str(part_meta['handling_requirement']).upper()}")

with col_p2:
    active_jhulas = st.number_input("Number of Active Jhula Machines", min_value=1, max_value=10, value=2)
    active_hours = st.number_input("Active Production Hours Per Shift", min_value=1, max_value=24, value=10)
    fixed_labor_payroll = st.number_input("Fixed Labor Shift Payroll (₹)", min_value=0.0, value=6400.0)
    variable_labor_per_ton = st.number_input("Per-Ton Variable Labor Payout (₹)", min_value=0.0, value=0.0)

with col_p3:
    monthly_factory_bills = st.number_input("Total Monthly Factory Bills (₹) [Leave 0 if using Slab]", min_value=0.0, value=0.0)
    slab_pct_input = st.number_input("Factory Maintenance Fund Allocation (%) [Leave 0 if using Bills]", min_value=0.0, max_value=100.0, value=35.0)
    st.success(f"**Billing Rate Assigned:** ₹{billing_rate_per_ton:,.2f} / Ton")

st.markdown("---")

# ============================================================================
# 3. OPTIONAL DYNAMIC MACHINE PRODUCTION COUNTER INPUT GRID
# ============================================================================
st.subheader("🔢 Machine Output Entry Block (Optional)")
st.markdown("*Leave these counts at 0 to view pure Break-Even Forecasting values.*")

j_cols = st.columns(min(active_jhulas, 5))
actual_counts = []

for idx in range(active_jhulas):
    col_selector = j_cols[idx % 5]
    with col_selector:
        pcs = st.number_input(f"Jhula {idx + 1} Production (Pcs)", min_value=0, value=0, key=f"jhula_{idx}")
        actual_counts.append(pcs)

total_shift_pieces = sum(actual_counts)
total_shift_tonnage = (total_shift_pieces * weight_kg) / 1000.0
gross_shift_revenue = total_shift_tonnage * billing_rate_per_ton
slab_factor = slab_pct_input / 100.0

is_simulation_mode = total_shift_pieces > 0

# ============================================================================
# 4. HIERARCHY EVALUATION LOGIC
# ============================================================================
has_slab = slab_pct_input > 0
has_bills = monthly_factory_bills > 0

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
# 5. LIVE SHIFT FINANCIAL RUN SIMULATION
# ============================================================================
if is_simulation_mode:
    st.subheader("💵 Live Shift Financial Performance Summary")
    st.markdown(f"<div style='background-color: {model_color}; padding: 10px; border-radius: 5px; border-left: 4px solid {border_color}; font-weight: bold;'>{active_model_desc}</div>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    
    total_variable_labor_cost = total_shift_tonnage * variable_labor_per_ton
    
    if has_slab:
        maint_allocation = gross_shift_revenue * slab_factor
    elif has_bills:
        maint_allocation = monthly_factory_bills / 30.0
    else:
        maint_allocation = 0.0
        
    net_profit = gross_shift_revenue - (maint_allocation + fixed_labor_payroll + total_variable_labor_cost)
    
    f_col1, f_col2, f_col3 = st.columns(3)
    f_col1.metric("Total Pieces Processed", f"{total_shift_pieces} Pcs", f"{total_shift_tonnage:.3f} Tons")
    f_col2.metric("Gross Revenue Realized", f"₹{gross_shift_revenue:,.2f}")
    f_col3.metric("Net Take-Home Shift Profit", f"₹{net_profit:,.2f}", delta="- Deficit" if net_profit < 0 else None, delta_color="inverse" if net_profit < 0 else "normal")
    st.markdown("---")

# ============================================================================
# 6. AUTOMATED TARGET FORECASTING ENGINE LAYOUT
# ============================================================================
st.subheader("🔮 Break-Even Target Forecasting Engine")
st.markdown(f"Running calculation layout following hierarchy logic: **{active_model_desc}**")
st.markdown("<br>", unsafe_allow_html=True)

if has_slab:
    net_margin_ton = (billing_rate_per_ton * (1.0 - slab_factor)) - variable_labor_per_ton
    min_tonnage = fixed_labor_payroll / net_margin_ton if net_margin_ton > 0 else 0.0
    maint_disp = f"₹{min_tonnage * billing_rate_per_ton * slab_factor:,.2f} (Computed Dynamic Slab Cost)"
else:
    net_margin_ton = billing_rate_per_ton - variable_labor_per_ton
    flat_daily_overhead = (monthly_factory_bills / 30.0) if has_bills else 0.0
    min_tonnage = (flat_daily_overhead + fixed_labor_payroll) / net_margin_ton if net_margin_ton > 0 else 0.0
    maint_disp = f"₹{flat_daily_overhead:,.2f} (Flat Fixed Daily Overhead)"

min_pieces = (min_tonnage * 1000.0) / weight_kg if weight_kg > 0 else 0.0
total_shift_runtime_units = active_jhulas * active_hours
min_rate_hr = min_pieces / total_shift_runtime_units if total_shift_runtime_units > 0 else 0.0

st.markdown(f"<div style='background-color: {model_color}; padding: 20px; border-radius: 8px; border-left: 6px solid {border_color};'>", unsafe_allow_html=True)

fc1, fc2 = st.columns(2)
with fc1:
    st.write(f"**Net Margin Retained / Ton:** ₹{net_margin_ton:,.2f}")
    st.write(f"**Factory Maintenance Cost Applied:** {maint_disp}")
    st.write(f"**Fixed Labor Cost Applied:** ₹{fixed_labor_payroll:,.2f}")
with fc2:
    st.metric("🎯 Break-Even Target (Volume)", f"{min_tonnage:.3f} Tons")
    st.metric("🎯 Total Casting Pieces Needed", f"{int(min_pieces)} Pcs")
    st.success(f"**🚀 Required Floor Pace:** {min_rate_hr:.2f} Pcs / Hour / Machine")

st.markdown("</div>", unsafe_allow_html=True)
st.markdown("---")

# ============================================================================
# 7. MATHEMATICAL FORMULAS EXPANDER VIEW BLOCK
# ============================================================================
with st.expander("📝 View Active Costing Hierarchy Equations"):
    if has_slab:
        st.markdown("### ⚡ Active Formula Profile: Dynamic Variable Slab Model")
        st.latex(r"\text{Net Margin Ton} = [\text{Billing Rate} \times (1 - \text{Slab \%})] - \text{Variable Labor Per Ton}")
        st.latex(r"\text{Break Even Tonnage} = \frac{\text{Fixed Labor Shift Payroll}}{\text{Net Margin Retained Per Ton}}")
    else:
        st.markdown("### 📊 Active Formula Profile: Standard Flat Model")
        st.latex(r"\text{Flat Daily Overhead} = \frac{\text{Total Monthly Bills}}{30}")
        st.latex(r"\text{Net Margin Ton} = \text{Billing Rate} - \text{Variable Labor Per Ton}")
        st.latex(r"\text{Break Even Tonnage} = \frac{\text{Flat Daily Overhead} + \text{Fixed Labor Shift Payroll}}{\text{Net Margin Retained Per Ton}}")
        
    st.latex(r"\text{Casting Pieces Needed} = \frac{\text{Break Even Tonnage} \times 1000}{\text{Weight (Kg)}}")
    st.latex(r"\text{Target Floor Pace} = \frac{\text{Casting Pieces Needed}}{\text{Active Jhulas} \times \text{Active Hours}}")
