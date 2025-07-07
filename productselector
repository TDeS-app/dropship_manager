# streamlit_app.py
import streamlit as st
import pandas as pd
import os
from datetime import datetime
from io import BytesIO

st.set_page_config(layout="wide")
st.title("Dropshipping Product & Inventory Manager")

# Initialize session state
if 'selected_handles' not in st.session_state:
    st.session_state.selected_handles = set()
if 'product_df' not in st.session_state:
    st.session_state.product_df = pd.DataFrame()
if 'inventory_df' not in st.session_state:
    st.session_state.inventory_df = pd.DataFrame()

st.sidebar.header("Step 1: Upload Files")
product_files = st.sidebar.file_uploader("Upload Product CSVs", type='csv', accept_multiple_files=True)
inventory_file = st.sidebar.file_uploader("Upload Inventory CSV", type='csv')

# Step 2: Load Data
if product_files:
    product_dfs = [pd.read_csv(file) for file in product_files]
    product_df = pd.concat(product_dfs, ignore_index=True)
    st.session_state.product_df = product_df

if inventory_file:
    inventory_df = pd.read_csv(inventory_file)
    st.session_state.inventory_df = inventory_df

product_df = st.session_state.product_df
inventory_df = st.session_state.inventory_df

# Step 3: Match Inventory
if not product_df.empty and not inventory_df.empty:
    merged_df = product_df.merge(inventory_df, on='Variant SKU', how='left')
    grouped = merged_df.groupby('Handle')

    st.header("Step 2: Select Products")
    for handle, group in grouped:
        cols = st.columns([1, 3])

        # Main image from first row
        main_image = group.iloc[0]['Image Src']
        title = group.iloc[0]['Title']

        with cols[0]:
            st.image(main_image, width=150)

        with cols[1]:
            st.markdown(f"### {title}")
            st.markdown(f"**Handle**: {handle}")
            st.markdown(f"**Inventory**:")
            inv_details = group[['Variant SKU', 'Variant Inventory Qty']].dropna()
            for _, row in inv_details.iterrows():
                st.markdown(f"- SKU: {row['Variant SKU']} — Stock: {int(row['Variant Inventory Qty'])}")

            checked = handle in st.session_state.selected_handles
            if st.checkbox("Select this product", key=handle, value=checked):
                st.session_state.selected_handles.add(handle)
            else:
                st.session_state.selected_handles.discard(handle)

    st.header("Step 3: Export Selected Files")
    if st.button("Confirm Choices"):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        selected_products = product_df[product_df['Handle'].isin(st.session_state.selected_handles)]
        selected_inventory = inventory_df[inventory_df['Variant SKU'].isin(selected_products['Variant SKU'])]

        prod_buffer = BytesIO()
        inv_buffer = BytesIO()

        selected_products.to_csv(prod_buffer, index=False)
        selected_inventory.to_csv(inv_buffer, index=False)

        st.download_button(
            label="Download Selected Product File",
            data=prod_buffer.getvalue(),
            file_name=f"selected_products_{timestamp}.csv",
            mime="text/csv"
        )

        st.download_button(
            label="Download Selected Inventory File",
            data=inv_buffer.getvalue(),
            file_name=f"selected_inventory_{timestamp}.csv",
            mime="text/csv"
        )
