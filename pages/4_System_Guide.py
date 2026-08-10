import streamlit as st

st.title("📘 System Operational & Maintenance Guide")
st.subheader("Standard Operating Procedures for the Classic Industries Pipeline")

st.markdown("---")

# Section 1: End-to-End Core Workflow Steps
st.write("### 🔄 1. End-to-End Data Pipeline Steps")
st.markdown("""
Follow these steps to process new incoming casting documents and sync records:
1. **Upload Document Scan:** Drop the raw delivery challan PDF or image file straight into the tracked Google Drive folder (`Inward_Challans`).
2. **AI Automated Extraction:** The background Google Apps Script runs automatically, calling the Gemini AI engine to extract dates, challan IDs, part numbers, and quantities.
3. **Verify the Google Sheet Row:** Open your `Daily_Log` spreadsheet tab to check the extracted text lines for any typos.
4. **Trigger the Cloud Sync:** Check the **`Is Validated`** checkbox row to mark it `TRUE`. The script will push the payload directly to Supabase and mark the status as **`Synced`**.
5. **Dashboard Monitoring:** Open this Streamlit app. The row register and stock health charts recalculate instantly.
""")

st.markdown("---")

# Section 2: Instructions to Update Dashboard Code or Layout
st.write("### ⚙️ 2. How to Update This Website Code")
st.markdown("""
If you need to change text headers, alter tables, or adjust dashboard layouts:
* **Modify Code on GitHub:** Open your private repository `classicindustires-automation` directly in your browser.
* **Edit Target Sub-Page:** Navigate into the `pages/` directory and use the pencil icon to modify the specific screen file.
* **Commit to Main Branch:** Click **Commit changes** to save your text strings on the `main` branch. 
* **Instant Hot Reload:** Streamlit Cloud listens to your GitHub commits and updates your live URL link automatically within 5 seconds.
""")

st.markdown("---")

# Section 3: Credentials Management
st.write("### 🔒 3. Database Secrets Management")
st.markdown("""
If your database anon keys or table names change, do not type them into your Python scripts:
1. Log into your **Streamlit Community Cloud Workspace**.
2. Go to your active app container settings and open **Advanced Settings -> Secrets**.
3. Overwrite your `SUPABASE_URL`, `SUPABASE_KEY`, or `TABLE_NAME` tokens inside the TOML text block and click **Save**.
""")
