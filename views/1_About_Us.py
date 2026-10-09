# ============================================================================
# VIEWS/1_ABOUT_US.PY - PART 1
# CONFIGURATIONS, CAPTURE UTILITIES & IMAGE RESIZING ENGINE
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

# Core configuration setup variables
GALLERY_DIR = "assets/gallery"
os.makedirs(GALLERY_DIR, exist_ok=True)

def process_to_square_size(uploaded_file, target_size=200):
    """
    Read an uploaded image, crop it to a perfect square, 
    and resize it down to the pre-defined target dimensions.
    """
    try:
        img = Image.open(uploaded_file)
        # Convert to RGB if image is in RGBA/CMYK format
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            
        width, height = img.size
        min_dim = min(width, height)
        
        # Center crop bounding logic calculations
        left = (width - min_dim) / 2
        top = (height - min_dim) / 2
        right = (width + min_dim) / 2
        bottom = (height + min_dim) / 2
        
        img_cropped = img.crop((left, top, right, bottom))
        img_resized = img_cropped.resize((target_size, target_size), Image.Resampling.LANCZOS)
        return img_resized
    except Exception as e:
        st.error(f"Error processing image asset profiles: {str(e)}")
        return None
# ============================================================================
# VIEWS/1_ABOUT_US.PY - PART 2
# HTML MAPPING CSS STYLES & FACILITY HERO PRESENTATION
# ============================================================================

# Inject custom round avatar CSS styling maps without horizontal text wrapping
st.markdown("""
<style>
    .circular-gallery {
        display: flex;
        flex-wrap: wrap;
        gap: 25px;
        justify-content: flex-start;
        margin-top: 15px;
        margin-bottom: 20px;
    }
    .avatar-card {
        text-align: center;
        width: 130px;
    }
    .avatar-circle {
        width: 120px;
        height: 120px;
        border-radius: 50%;
        object-fit: cover;
        border: 3px solid #2B6CB0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin: 0 auto;
    }
    .avatar-label {
        margin-top: 8px;
        font-size: 13px;
        font-weight: 600;
        color: #2D3748;
        word-wrap: break-word;
    }
</style>
""", unsafe_allow_html=True)

st.title("🏢 Classic Industries")
st.subheader("Foundry Friends & Finishers Division")
st.markdown("---")

hero_path = "assets/main_hero.jpg"
if os.path.exists(hero_path):
    st.image(
        hero_path, 
        caption="Classic Industries — Foundry Processing Hub Floor Matrix",
        use_container_width=True
    )
else:
    st.warning(f"📷 Please ensure your image is uploaded to assets exactly as: `{hero_path}`")

st.markdown("---")
tab_about, tab_services, tab_team = st.tabs(["📋 About Us", "🛠️ Our Services", "👥 My Team"])
# ============================================================================
# VIEWS/1_ABOUT_US.PY - PART 3
# ABOUT US CONTENT MATRIX AND PLANT NETWORK MODULES
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
        
        st.write("### ⏱️ Corporate Facility Reference Matrix")
        st.markdown("""
        *   **Company Name:** Classic Industries
        *   **Division Core:** Foundry Friends & Finishers (Casting Processing Hub)
        *   **Plant Operations:** 🔄 **24x7 Continuous Production Shifts**
        *   **Helpdesk & IT Support:** 📞 **08:00 AM – 05:00 PM** (Monday – Saturday)
        """)
    with col2:
        st.info("🗺️ **Classic Industries Plant Network**")
        st.markdown("""
        Our specialized manufacturing facilities are optimized for high-volume casting processing, 
        featuring automated inbound document capture infrastructure.
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
        st.markdown("#### ⚙️ Precision Fitting Operations")
        
    with col_grind:
        grind_path = "assets/thumb_grinding.jpg"
        if os.path.exists(grind_path):
            st.image(grind_path, use_container_width=True)
        else:
            st.info("Grinding Thumbnail Pending.")
        st.markdown("#### 🪚 Industrial Grinding & Linishing")
# ============================================================================
# VIEWS/1_ABOUT_US.PY - PART 4
# TEAM TAB INTEGRATION WITH DYNAMIC CIRCULAR IMAGE GALLERY WIDGETS
# ============================================================================

with tab_team:
    st.markdown("### 👥 Dynamic Team Profile Gallery")
    
    # 1. File Upload Processing Handling Hook
    uploaded_img = st.file_uploader(
        "Upload New Team Profile Member Photo:",
        type=["jpg", "jpeg", "png"],
        key="gallery_uploader_input"
    )
    
    if uploaded_img is not None:
        target_filename = uploaded_img.name.strip().replace(" ", "_")
        destination_filepath = os.path.join(GALLERY_DIR, target_filename)
        
        # 2. Check if file is not already present to prevent execution overrides
        if not os.path.exists(destination_filepath):
            with st.spinner("Processing image to pre-defined square profile size..."):
                processed_bitmap = process_to_square_size(uploaded_img, target_size=250)
                if processed_bitmap is not None:
                    processed_bitmap.save(destination_filepath, format="JPEG")
                    st.success(f"✓ Added `{target_filename}` in uniform pre-defined size layout properties!")
                    st.rerun()
        else:
            st.info(f"ℹ️ An asset profile matching the name `{target_filename}` already exists in the gallery database system.")

    st.markdown("---")
    st.write("#### 👥 Active Line Team Members Roster")
    
    # 3. Dynamic Scan Loops over the local assets directory
    gallery_files = [f for f in os.listdir(GALLERY_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    
    if gallery_files:
        html_gallery_content = '<div class="circular-gallery">'
        
        for index, filename in enumerate(sorted(gallery_files)):
            file_src_path = os.path.join(GALLERY_DIR, filename)
            # Extends base title labels out of asset tracking string name components
            display_label = os.path.splitext(filename)[0].replace("_", " ").title()
            
            # Formulate layout string components without any raw backspace controls
            html_gallery_content += f"""
            <div class="avatar-card">
                <img src="data:image/jpeg;base64,{st.image(file_src_path, channels="RGB").getvalue() if False else ''}" 
                     class="avatar-circle" 
                     src_local="{file_src_path}" 
                     alt="{display_label}"/>
                <div class="avatar-label">{display_label}</div>
            </div>
            """
        
        html_gallery_content += '</div>'
        
        # Alternately render clean Streamlit elements in columns for absolute stability across servers
        cols = st.columns(5)
        for idx, filename in enumerate(sorted(gallery_files)):
            file_src_path = os.path.join(GALLERY_DIR, filename)
            display_label = os.path.splitext(filename)[0].replace("_", " ").title()
            
            with cols[idx % 5]:
                # Streamlit alternative to safe HTML circular masking rendering
                st.image(file_src_path, use_container_width=True)
                st.markdown(f"<p style='text-align:center; font-weight:bold;'>{display_label}</p>", unsafe_allow_html=True)
    else:
        st.info("📋 The dynamic profile directory is currently empty. Upload images above to populate badges.")
