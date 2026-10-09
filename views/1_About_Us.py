# ============================================================================
# VIEWS/1_ABOUT_US.PY - PART 1 (ROOT PATH REFIXED)
# CONFIGURATIONS, TRUE REPO ROOT ROUTING UTILITIES & ENGINES
# ============================================================================

import calendar
import datetime
import io
import os
import re
from PIL import Image
import pandas as pd
import requests
import streamlit as st
from dateutil.relativedelta import relativedelta

# Steps back up out of the views folder to find the root directory level
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR) 

# Sets absolute routing mappings targeting the true repository root levels
GALLERY_DIR = os.path.join(REPO_ROOT, "assets", "gallery")
os.makedirs(GALLERY_DIR, exist_ok=True)

try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except Exception:
    st.error(
        "❌ Missing infrastructure secrets configuration. "
        "Please configure SUPABASE_URL and SUPABASE_KEY."
    )
    st.stop()

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

SOURCE_IDENTIFIER = "STREAMLIT_LIVE_UI"
APP_USER = (
    st.session_state.get("user_name")
    or st.session_state.get("username")
    or "Streamlit User"
)

# ============================================================================
# VIEWS/1_ABOUT_US.PY - PART 2
# GRAPHICAL BITMAP TRANSLATION ENGINE & INTERFACING LAYOUT STYLES
# ============================================================================

def process_to_square_size(uploaded_file, target_size=250):
    """
    Read an uploaded image, crop it to a perfect square from the center,
    and scale it down to match our uniform target bounding box parameters.
    """
    try:
        img = Image.open(uploaded_file)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            
        width, height = img.size
        min_dim = min(width, height)
        
        # Center cropping box coordinate geometry boundary loops
        left = (width - min_dim) / 2
        top = (height - min_dim) / 2
        right = (width + min_dim) / 2
        bottom = (height + min_dim) / 2
        
        img_cropped = img.crop((left, top, right, bottom))
        img_resized = img_cropped.resize(
            (target_size, target_size), 
            Image.Resampling.LANCZOS
        )
        return img_resized
    except Exception as e:
        st.error(f"Image scaling execution failure: {str(e)}")
        return None

# Custom styling injection to cleanly handle structural element tags
st.markdown("""
<style>
    .avatar-label {
        margin-top: 8px;
        font-size: 13px;
        font-weight: 600;
        color: #2D3748;
        word-wrap: break-word;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)
# ============================================================================
# VIEWS/1_ABOUT_US.PY - PART 3 (ROOT PATH REFIXED)
# BRAND PRESENTATION HEADER & ROOT HERO ASSET MATRIX TARGETS
# ============================================================================

st.title("🏢 Classic Industries")
st.subheader("Foundry Friends & Finishers Division")
st.markdown("---")

# Corrected path mapping pointing directly to the root assets folder
hero_path = os.path.join(REPO_ROOT, "assets", "main_hero.jpg")
if os.path.exists(hero_path):
    st.image(
        hero_path, 
        caption="Classic Industries — Advanced Shop Floor Layout Floor Matrix",
        use_container_width=True
    )
else:
    st.warning(f"📷 [System Notice] Hero asset missing at target: `{hero_path}`")

st.markdown("---")
tab_about, tab_services, tab_team = st.tabs(
    ["📋 About Us", "🛠️ Our Services", "👥 My Team"]
)

# ============================================================================
# VIEWS/1_ABOUT_US.PY - PART 4 (ROOT PATH REFIXED)
# CORE BUSINESS DATA PANELS AND REFIXED ACCESSIBLE SUB-TAB ASSETS
# ============================================================================

with tab_about:
    col1, col2 = st.columns([1.3, 1])
    with col1:
        st.write("### 🤝 Who We Are")
        st.markdown("""
        Welcome to the **Foundry Friends & Finishers** division of **Classic Industries**. 
        We operate as a premium, high-volume multi-process jobwork hub optimized to handle raw, rough casting outputs 
        straight out of foundry sand molds. 
        """)
        st.write("### ⏱️ Facility Operational Matrix")
        st.markdown("""
        *   **Company Name:** Classic Industries
        *   **Plant Operations:** 🔄 **24x7 Continuous Production Shifts**
        """)
    with col2:
        st.info("🗺️ **Classic Industries Plant Network**")
        st.markdown("Our manufacturing plants feature automated casting scale infrastructure lines.")

with tab_services:
    st.write("### 🛠️ Our Core Industrial Workflows")
    col_fit, col_grind = st.columns(2)
    
    with col_fit:
        # Corrected absolute routing paths pointing out to the true repo root
        fit_path = os.path.join(REPO_ROOT, "assets", "thumb_fitting.jpg")
        if os.path.exists(fit_path):
            st.image(fit_path, use_container_width=True)
        else:
            st.caption("ℹ️ *Fitting image placeholder asset*")
        st.markdown("#### ⚙️ Precision Fitting Operations")
        
    with col_grind:
        # Corrected absolute routing paths pointing out to the true repo root
        grind_path = os.path.join(REPO_ROOT, "assets", "thumb_grinding.jpg")
        if os.path.exists(grind_path):
            st.image(grind_path, use_container_width=True)
        else:
            st.info("📷 **Grinding Thumbnail Asset Pending**")
        st.markdown("#### 🪚 Industrial Grinding & Linishing")
# ============================================================================
# VIEWS/1_ABOUT_US.PY - PART 5 (ROOT PATH REFIXED)
# TEAM TAB INTEGRATION, ROOT DIRECTORY IMAGE UPLOADS AND CARD GRID
# ============================================================================

with tab_team:
    st.markdown("### 👥 Dynamic Team Profile Gallery Workspace")
    
    # 1. Cloud-accessible file upload selector interface
    uploaded_img = st.file_uploader(
        "Upload New Team Profile Member Photo:",
        type=["jpg", "jpeg", "png"],
        key="gallery_uploader_input"
    )
    
    if uploaded_img is not None:
        # Safe string cleaning converting filename text structures safely
        target_filename = uploaded_img.name.strip().replace(" ", "_")
        
        # Fixed destination filepath pointing out to the true global root gallery
        destination_filepath = os.path.join(GALLERY_DIR, target_filename)
        
        # 2. Check if file exists locally in the deployed root folder space
        if not os.path.exists(destination_filepath):
            with st.spinner("Processing image to predefined square layout sizes..."):
                processed_bitmap = process_to_square_size(uploaded_img, target_size=250)
                if processed_bitmap is not None:
                    # Persists file inside the absolute root gallery folder directory
                    processed_bitmap.save(destination_filepath, format="JPEG")
                    st.success(f"✓ Added `{target_filename}` successfully to root gallery asset database!")
                    st.rerun()
        else:
            st.info(f"ℹ️ Profile asset named `{target_filename}` matches an already tracked profile record file layout.")

    st.markdown("---")
    st.write("#### 👥 Active Line Team Members Roster")
    
    # 3. Read gallery files relative to the refixed absolute global root directory pathing
    gallery_files = [f for f in os.listdir(GALLERY_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    
    if gallery_files:
        # Render clean Streamlit responsive column blocks for absolute cloud server stability
        cols = st.columns(5)
        for idx, filename in enumerate(sorted(gallery_files)):
            file_src_path = os.path.join(GALLERY_DIR, filename)
            # Make label human-readable from file name configuration rules
            display_label = os.path.splitext(filename)[0].replace("_", " ").title()
            
            with cols[idx % 5]:
                st.image(file_src_path, use_container_width=True)
                st.markdown(f"<p class='avatar-label'>{display_label}</p>", unsafe_allow_html=True)
    else:
        st.info("📋 Profile gallery tracking directory is empty. Use the uploader tool panel above to configure data.")
