import streamlit as st
import pandas as pd

st.title("🗂️ Part Configuration Registry")
st.subheader("Authorized Item Master Reference List")

supabase = st.session_state.supabase

try:
    # Pull master reference list
    response = supabase.table("item_master").select("*").execute()
    items = response.data

    if items:
        df_items = pd.DataFrame(items)
        
        # Search utility
        search_query = st.text_input("🔍 Search Registry by Part Number Component:", "").strip().upper()
        if search_query:
            df_items = df_items[df_items['part_number'].astype(str).str.upper().str.contains(search_query)]

        st.write(f"Showing {len(df_items)} Registered Product Specifications")
        st.dataframe(df_items, use_container_width=True)
    else:
        st.warning("Connected to database, but table node 'item_master' returned an empty catalogue layout.")
except Exception as e:
    st.error(f"Failed to query Item Master node: {str(e)}")
