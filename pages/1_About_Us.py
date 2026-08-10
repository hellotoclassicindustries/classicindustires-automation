import streamlit as st
import os

# FIXED: Re-structured the company name hierarchy to put Classic Industries first
st.title("🏢 Classic Industries")
st.subheader("Foundry Friends & Finishers Division")

# 1. Main Hero Image Header Configuration
hero_path = "assets/main_hero.jpg"
if os.path.exists(hero_path):
    st.image(
        hero_path, 
        caption="Classic Industries — Foundry Friends & Finishers Advanced Metal Shop Floor",
        use_container_width=True
    )
else:
    st.warning(f"📷 [System Notice] Please ensure your image is uploaded to the root assets folder exactly as: `{hero_path}`")

st.markdown("---")

# 2. Main Tabbed Layout Menu Options
tab_about, tab_services, tab_team = st.tabs(["📋 About Us", "🛠️ Our Services", "👥 My Team"])

with tab_about:
    col1, col2 = st.columns([1.3, 1])
    with col1:
        st.write("### 🤝 Who We Are")
        st.markdown("""
        Welcome to the **Foundry Friends & Finishers** division of **Classic Industries**. 
        We operate as a premium, high-volume multi-process jobwork hub optimized to handle raw, rough casting outputs 
        straight out of foundry sand molds. 
        
        Our specialized lines take rough metal castings and perform precision bench fitting, edge grinding, 
        seam linishing, and dimensional alignment loops to transform rough metal parts into production-ready components.
        
        This application interfaces directly with our high-speed cloud database layers to convert document data 
        points into live, actionable shop floor asset values.
        """)
        
        st.write("### ⏱️ Corporate Facility Reference Matrix")
        st.markdown("""
        *   **Company Name:** Classic Industries
        *   **Division Core:** Foundry Friends & Finishers (Casting Processing Hub)
        *   **Operational Hours:** 08:00 AM – 08:00 PM (Monday – Saturday)
        *   **System Classification:** Internal ERP Dashboard Deployment Suite
        *   **Automation Core:** Powered by deep extraction AI models converting delivery challans seamlessly.
        """)
    with col2:
        st.info("🗺️ **Classic Industries Plant Network**")
        st.markdown("""
        Our specialized manufacturing facilities are optimized for high-volume casting processing, 
        featuring automated inbound document capture infrastructure.
        
        *Use the sidebar menu tabs to toggle between real-time **Stock Summaries** and the **Daily Transaction Register**.*
        """)

with tab_services:
    st.write("### 🛠️ Our Core Industrial Workflows")
    
    col_fit, col_grind = st.columns(2)
    
    with col_fit:
        fit_path = "assets/thumb_fitting.jpg"
        if os.path.exists(fit_path):
            st.image(fit_path, use_container_width=True)
        else:
            st.caption("ℹ️ *Fitting image placeholder*")
        st.markdown("""
        #### ⚙️ Precision Fitting Operations
        High-tolerance mechanical alignment, bench fitting, and final component structural assemblies tailored to client blueprint layouts.
        """)
        
    with col_grind:
        grind_path = "assets/thumb_grinding.jpg"
        if os.path.exists(grind_path):
            st.image(grind_path, use_container_width=True)
        else:
            st.info("📷 **Grinding Thumbnail Pending** — This slot will display automatically once `thumb_grinding.jpg` is uploaded to your assets folder.")
        st.markdown("""
        #### 🪚 Industrial Grinding & Linishing
        Shaving off parting lines, smoothing mold seams, deburring, defect elimination, and achieving exact dimensional smoothness profiles on rough castings.
        """)
        
    st.markdown("---")
    st.write("### 🚀 Upcoming Finishing Infrastructure Expansion")
    
    col_soon1, col_soon2 = st.columns(2)
    with col_soon1:
        st.warning("#### ⏳ Shotblasting (Coming Soon)")
        st.caption("High-pressure abrasive shot lines to strip heavy foundry scale, rust, and surface contaminants back down to raw clean metal.")
    with col_soon2:
        st.warning("#### ⏳ Protective Painting (Coming Soon)")
        st.caption("Specialized anti-corrosion priming, industrial liquid spray coats, and durable environmental seal finishes to protect completed jobs.")

with tab_team:
    st.info("### 👥 My Team (Coming Soon)")
    st.markdown("""
    This section is currently being organized. Once active, it will present:
    *   **Shift Supervisor Directories** (Contact details for active line management).
    *   **Operator Rosters** (Assigned stations for fitting, grinding, and inspection loops).
    *   **Quality Inspector Badges** (Authorized personnel confirming casting dispatch codes).
    """)
