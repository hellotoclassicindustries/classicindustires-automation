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
    st.warning("📋 Operations Notice: The master part catalog database is empty or disconnected. Please sync parts from your Google Sheet master catalog.")
    st.stop()

st.title("🔮 Job-Work Forecast & Shift Performance Simulator")
st.markdown("---")

# Layout Form Grid matching Excel Format
st.subheader("📊 Parameter / Input Block")
col_p1, col_p2, col_p3 = st.columns(3)

with col_p1:
    part_options = catalog_df["part_number"].unique()
    selected_part = st.selectbox("Select Part Name", part_options)
    part_meta = catalog_df[catalog_df["part_number"] == selected_part].iloc[0]
    
    st.info(f"**Description:** {part_meta['description'].upper()}\n\n"
            f"**Weight:** {float(part_meta['weight_kg']):.2f} Kg\n\n"
            f"**Class:** {part_meta['part_class']}")

with col_p2:
    active_jhulas = st.number_input("Number of Active Jhula Machines", min_value=1, max_value=10, value=2)
    active_hours = st.number_input("Active Production Hours Per Shift", min_value=1, max_value=24, value=10)
    fixed_labor_payroll = st.number_input("Fixed Labor Shift Payroll (₹)", min_value=0.0, value=6400.0)

with col_p3:
    monthly_factory_bills = st.number_input("Total Monthly Factory Bills (₹)", min_value=0.0, value=245000.0)
    slab_pct_input = st.number_input("Factory Maintenance Fund Allocation (%)", min_value=0.0, max_value=100.0, value=35.0)
    billing_rate_per_ton = float(part_meta["billing_rate_per_ton"])
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
weight_kg = float(part_meta["weight_kg"])
total_shift_tonnage = (total_shift_pieces * weight_kg) / 1000.0
gross_shift_revenue = total_shift_tonnage * billing_rate_per_ton
slab_factor = slab_pct_input / 100.0

# Determine mode: Simulation if pieces are typed, otherwise Pure Forecasting
is_simulation_mode = total_shift_pieces > 0

# ============================================================================
# 4. IF PIECES ENTERED ➔ DISPLAY FINANCIAL RUN SIMULATION
# ============================================================================
if is_simulation_mode:
    st.subheader("💵 Live Shift Financial Performance Summary")
    
    maint_allocation_b = monthly_factory_bills / 30.0
    net_profit_b = gross_shift_revenue - (maint_allocation_b + fixed_labor_payroll)
    
    maint_allocation_d = gross_shift_revenue * slab_factor
    net_profit_d = gross_shift_revenue - (maint_allocation_d + fixed_labor_payroll)
    
    f_col1, f_col2, f_col3 = st.columns(3)
    f_col1.metric("Total Pieces Processed", f"{total_shift_pieces} Pcs", f"{total_shift_tonnage:.3f} Tons")
    f_col2.metric("Gross Revenue Realized", f"₹{gross_shift_revenue:,.2f}")
    f_col3.metric("Net Take-Home Profit (Slab Model)", f"₹{net_profit_d:,.2f}")
    
    st.markdown("<br>", unsafe_allow_html=True)

# ============================================================================
# 5. AUTOMATED TARGET FORECASTING ENGINE LAYOUT (SIDE-BY-SIDE)
# ============================================================================
st.subheader("🔮 Break-Even Target Forecasting Engine")
left_column, right_column = st.columns(2)

maint_allocation_b = monthly_factory_bills / 30.0
net_margin_ton_b = billing_rate_per_ton
net_margin_ton_d = billing_rate_per_ton * (1.0 - slab_factor)

min_ton_b = (maint_allocation_b + fixed_labor_payroll) / net_margin_ton_b if net_margin_ton_b > 0 else 0.0
min_ton_d = fixed_labor_payroll / net_margin_ton_d if net_margin_ton_d > 0 else 0.0

min_pieces_b = (min_ton_b * 1000.0) / weight_kg if weight_kg > 0 else 0.0
min_pieces_d = (min_ton_d * 1000.0) / weight_kg if weight_kg > 0 else 0.0

total_shift_runtime_units = active_jhulas * active_hours
min_rate_hr_b = min_pieces_b / total_shift_runtime_units if total_shift_runtime_units > 0 else 0.0
min_rate_hr_d = min_pieces_d / total_shift_runtime_units if total_shift_runtime_units > 0 else 0.0

with left_column:
    st.markdown("<div style='background-color: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 5px solid #595959;'><h4 style='margin-top:0;'>📊 Standard Flat Model (Column B)</h4></div>", unsafe_allow_html=True)
    st.write(f"**Net Margin Retained / Ton:** ₹{net_margin_ton_b:,.2f}")
    st.metric("Break-Even Target (Volume)", f"{min_ton_b:.3f} Tons")
    st.metric("Total Casting Pieces Needed", f"{int(min_pieces_b)} Pcs")
    st.success(f"**Target Floor Pace:** {min_rate_hr_b:.2f} Pcs / Hr / Machine")

with right_column:
    st.markdown("<div style='background-color: #e2efda; padding: 15px; border-radius: 8px; border-left: 5px solid #006100;'><h4 style='margin-top:0; color: #006100;'>⚡ Dynamic Slab Model (Column D)</h4></div>", unsafe_allow_html=True)
    st.write(f"**Net Margin Retained / Ton:** ₹{net_margin_ton_d:,.2f}")
    st.metric("Break-Even Target (Volume)", f"{min_ton_d:.3f} Tons")
    st.metric("Total Casting Pieces Needed", f"{int(min_pieces_d)} Pcs")
    st.success(f"**Target Floor Pace:** {min_rate_hr_d:.2f} Pcs / Hr / Machine")

st.markdown("---")

# ============================================================================
# 6. MATHEMATICAL FORMULAS EXPANDER VIEW BLOCK
# ============================================================================
with st.expander("📝 View Underlying Dashboard Equations & Formulas"):
    st.markdown("### 🏦 1. Total Shifting Performance Realization")
    st.latex(r"\text{Total Pieces} = \sum (\text{Actual Pieces Entered Per Jhula})")
    st.latex(r"\text{Total Tonnage} = \frac{\text{Total Pieces} \times \text{Weight (Kg)}}{1000}")
    st.latex(r"\text{Gross Revenue (₹)} = \text{Total Tonnage} \times \text{Billing Rate Per Ton}")
    
    st.markdown("### 📊 2. Standard Flat Model Costing (Column B)")
    st.latex(r"\text{Factory Maintenance Cost} = \frac{\text{Total Monthly Bills}}{30}")
    st.latex(r"\text{Break Even Tonnage} = \frac{\text{Factory Maintenance Cost} + \text{Fixed Labor Shift Payroll}}{\text{Billing Rate Per Ton}}")
    
    st.markdown("### ⚡ 3. Dynamic Variable Slab Costing (Column D)")
    st.latex(r"\text{Factory Maintenance Cost} = \text{Gross Revenue} \times \text{Allocation \%}")
    st.latex(r"\text{Net Margin Retained Per Ton} = \text{Billing Rate Per Ton} \times (1 - \text{Allocation \%})")
    st.latex(r"\text{Break Even Tonnage} = \frac{\text{Fixed Labor Shift Payroll}}{\text{Net Margin Retained Per Ton}}")
    
    st.markdown("### 🎯 4. Production Pace Metrics")
    st.latex(r"\text{Casting Pieces Needed} = \frac{\text{Break Even Tonnage} \times 1000}{\text{Weight (Kg)}}")
    st.latex(r"\text{Target Floor Pace} = \frac{\text{Casting Pieces Needed}}{\text{Active Jhulas} \times \text{Active Hours}}")
