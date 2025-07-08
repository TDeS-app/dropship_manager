import streamlit as st
import pandas as pd
import re
import os
import json
from io import BytesIO
from datetime import datetime
from urllib.parse import urlparse
from rapidfuzz import fuzz

st.set_page_config(layout="wide")

st.title("🎉 Dropship Product & Inventory Manager")

# Constants
PRODUCTS_PER_PAGE = 20
SELECTION_FILE = "selected_handles.json"

# Session state
if 'selected_handles' not in st.session_state:
    if os.path.exists(SELECTION_FILE):
        with open(SELECTION_FILE, "r") as f:
            st.session_state.selected_handles = set(json.load(f))
    else:
        st.session_state.selected_handles = set()
if 'product_df' not in st.session_state:
    st.session_state.product_df = None
if 'last_output_df' not in st.session_state:
    st.session_state.last_output_df = None
if 'merged_df_cache' not in st.session_state:
    st.session_state.merged_df_cache = None
if 'full_product_df' not in st.session_state:
    st.session_state.full_product_df = None
if 'product_page' not in st.session_state:
    st.session_state.product_page = 1
if 'selected_page' not in st.session_state:
    st.session_state.selected_page = 1
if 'search_query' not in st.session_state:
    st.session_state.search_query = ""

# --- Helper Functions ---
def save_selected_handles():
    with open(SELECTION_FILE, "w") as f:
        json.dump(list(st.session_state.selected_handles), f)

def read_csv_with_fallback(uploaded_file):
    content = uploaded_file.read()
    for enc in ['utf-8-sig', 'ISO-8859-1', 'windows-1252']:
        try:
            return pd.read_csv(BytesIO(content), encoding=enc)
        except Exception:
            continue
    st.warning(f"⚠️ Could not read {uploaded_file.name} with common encodings.")
    return None

def extract_sku_number(sku):
    match = re.search(r'\d+', str(sku))
    return match.group() if match else ''

def preprocess_sku(df):
    df = df.copy()
    sku_col = 'Variant SKU' if 'Variant SKU' in df.columns else 'SKU' if 'SKU' in df.columns else None
    if not sku_col:
        st.warning("⚠️ SKU column not found. Expected 'Variant SKU' or 'SKU'.")
        return pd.DataFrame()
    df['sku_num'] = df[sku_col].apply(extract_sku_number)
    return df[df['sku_num'].notna() & (df['sku_num'] != '')]

def fuzzy_match_inventory(product_df, inventory_df):
    product_df = preprocess_sku(product_df)
    inventory_df = preprocess_sku(inventory_df)

    # Filter inventory for available/on hand > 0
    qty_cols = [c for c in inventory_df.columns if 'Available' in c or 'On hand' in c]
    if qty_cols:
        inventory_df['total_available'] = inventory_df[qty_cols].fillna(0).sum(axis=1)
        inventory_df = inventory_df[inventory_df['total_available'] > 0]

    merged_rows = []
    for _, prod_row in product_df.iterrows():
        sku = prod_row['sku_num']
        match = inventory_df[inventory_df['sku_num'] == sku]
        if not match.empty:
            best_match = match.iloc[0]
            merged_row = pd.concat([prod_row, best_match.drop(labels=product_df.columns.intersection(inventory_df.columns))])
        else:
            merged_row = prod_row
        merged_rows.append(merged_row)

    return pd.DataFrame(merged_rows)

# Show file uploaders regardless of merged state
st.sidebar.header("Upload Files")
product_files = st.sidebar.file_uploader("Upload Product File(s)", type="csv", accept_multiple_files=True)
inventory_file = st.sidebar.file_uploader("Upload Inventory File", type="csv")

# Preprocess uploaded files and cache merged result
if product_files:
    dfs = [read_csv_with_fallback(f) for f in product_files]
    st.session_state.full_product_df = pd.concat(dfs, ignore_index=True)
if product_files and inventory_file:
    inventory_df = read_csv_with_fallback(inventory_file)
    merged_df = fuzzy_match_inventory(st.session_state.full_product_df, inventory_df)
    st.session_state.merged_df_cache = merged_df

# If merged_df_cache is ready, proceed to display UI
if st.session_state.merged_df_cache is not None:
    merged = st.session_state.merged_df_cache
    if not merged.empty:
        # This function would render the tiles/cards, pagination, selection, etc.
        from display import display_product_tiles
        display_product_tiles(merged, page_key="product")
    else:
        st.info("🔍 No matching products with inventory available.")
else:
    st.info("📤 Please upload product and inventory files to begin.")
