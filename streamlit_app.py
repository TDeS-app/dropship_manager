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

st.title("🎢 Dropship Product & Inventory Manager")

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
if 'last_search_query' not in st.session_state:
    st.session_state.last_search_query = ""

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

def paginate_list(grouped, page):
    if not page:
        page = 1
    start = (page - 1) * PRODUCTS_PER_PAGE
    end = start + PRODUCTS_PER_PAGE
    return grouped[start:end]

def display_pagination_controls(total, current_page, key_prefix):
    total_pages = (total + PRODUCTS_PER_PAGE - 1) // PRODUCTS_PER_PAGE
    col1, col2, col3 = st.columns([1, 2, 1])

    if current_page > 1 and col1.button("⬅️ Prev", key=f"{key_prefix}_prev"):
        st.session_state[f"{key_prefix}_page"] = current_page - 1

    with col2:
        new_page = st.selectbox(
            f"Page ({key_prefix})",
            options=list(range(1, total_pages + 1)),
            index=current_page - 1,
            key=f"{key_prefix}_page_selector"
        )
        if new_page != current_page:
            st.session_state[f"{key_prefix}_page"] = new_page

    if current_page < total_pages and col3.button("➡️ Next", key=f"{key_prefix}_next"):
        st.session_state[f"{key_prefix}_page"] = current_page + 1

def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme in ("http", "https"), result.netloc])
    except Exception:
        return False

def display_product_tiles(merged_df, page_key, search_query=""):
    if f"{page_key}_page" not in st.session_state:
        st.session_state[f"{page_key}_page"] = 1

    max_inventory = int(merged_df[[col for col in merged_df.columns if 'Available' in col][0]].fillna(0).max()) if not merged_df.empty else 500
    inventory_filter = st.sidebar.slider("📦 Filter by Inventory Quantity", 0, max_inventory, (0, max_inventory), key=f"{page_key}_inventory_filter_slider")

    grouped = list(merged_df.groupby("Handle"))

    if search_query != st.session_state.last_search_query:
        st.session_state[f"{page_key}_page"] = 1
        st.session_state.last_search_query = search_query

    if search_query:
        grouped = [
            (handle, group) for handle, group in grouped
            if search_query.lower() in str(group['Title'].iloc[0]).lower()
            or search_query.lower() in handle.lower()
            or any(search_query.lower() in str(sku).lower() for sku in group.get('Variant SKU', group.get('SKU', [])))
        ]

    filtered_grouped = []
    for handle, group in grouped:
        qty_col = 'Available Quantity'
        if qty_col not in group.columns:
            alt_qty = [c for c in group.columns if 'Available' in c]
            qty_col = alt_qty[0] if alt_qty else None
        if qty_col:
            total_qty = group[qty_col].fillna(0).sum()
            if inventory_filter[0] <= total_qty <= inventory_filter[1]:
                filtered_grouped.append((handle, group))
    grouped = filtered_grouped

    total = len(grouped)
    current_page = st.session_state[f"{page_key}_page"]
    paginated_grouped = paginate_list(grouped, current_page)

    for handle, group in paginated_grouped:
        handle_str = str(handle)
        sku_col = 'Variant SKU' if 'Variant SKU' in group.columns else 'SKU' if 'SKU' in group.columns else None
        if sku_col:
            non_na_rows = group[group[sku_col].notna()]
            main_row = non_na_rows.iloc[0] if not non_na_rows.empty else group.iloc[0]
        else:
            main_row = group.iloc[0]

        checked = st.checkbox(f" {group['Title'].iloc[0]} ({handle})", value=handle_str in st.session_state.selected_handles, key=f"chk_{page_key}_{handle_str}")
        if checked:
            st.session_state.selected_handles.add(handle_str)
        else:
            st.session_state.selected_handles.discard(handle_str)

        with st.expander("View Details"):
            image_columns = [col for col in group.columns if 'Image' in col and group[col].notna().any()]
            image_urls = []
            for col in image_columns:
                image_urls.extend(group[col].dropna().astype(str).unique().tolist())
            valid_image_urls = [url for url in image_urls if isinstance(url, str) and is_valid_url(url)]
            if valid_image_urls:
                image_cols = st.columns(min(len(valid_image_urls), 4))
                for i, url in enumerate(valid_image_urls[:4]):
                    with image_cols[i % 4]:
                        st.image(url, width=120)
            st.dataframe(group.reset_index(drop=True))

    save_selected_handles()
    display_pagination_controls(total, current_page, page_key)

def output_selected_files(df):
    selected = df[df['Handle'].isin(st.session_state.selected_handles)]
    if not selected.empty:
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_df = (
            selected
            .drop_duplicates()
            .sort_values("Handle")
        )
        csv = final_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "⬇️ Download Selected Products",
            data=csv,
            file_name=f"selected_products_{now}.csv",
            mime="text/csv"
        )

# --- MAIN APP FLOW ---
product_files = st.file_uploader("📄 Upload Product CSVs", type="csv", accept_multiple_files=True)
inventory_file = st.file_uploader("📦 Upload Inventory CSV", type="csv")

if product_files:
    dfs = []
    for uploaded_file in product_files:
        df = read_csv_with_fallback(uploaded_file)
        if df is not None:
            dfs.append(df)
    if dfs:
        combined_df = pd.concat(dfs, ignore_index=True)
        st.session_state.full_product_df = combined_df.copy()
        st.session_state.product_df = combined_df.copy()
        st.success("✅ Product files loaded and combined.")

if inventory_file and st.session_state.full_product_df is not None:
    if st.button("📦 Update Inventory Only"):
        inventory_df = read_csv_with_fallback(inventory_file)
        if inventory_df is not None:
            merged_df = fuzzy_match_inventory(st.session_state.full_product_df, inventory_df)
            st.session_state.merged_df_cache = merged_df.copy()
            st.session_state.original_inventory_columns = inventory_df.columns.tolist()
            st.success("✅ Inventory updated using latest file!")

# Always allow preview of product tiles if data exists
if st.session_state.merged_df_cache is not None:
    st.markdown("---")
    st.subheader("🖼️ Browse Products (Updated)")
    search_query = st.text_input("🔍 Search Products (After Inventory Update)")
    display_product_tiles(st.session_state.merged_df_cache, page_key="product", search_query=search_query)

    st.markdown("---")
    st.subheader("🔎 Selected Products Preview")
    selected_handles = st.session_state.selected_handles
    if selected_handles:
        selected_preview = st.session_state.merged_df_cache[st.session_state.merged_df_cache['Handle'].isin(selected_handles)]
        display_product_tiles(selected_preview, page_key="selected")
        if st.button("✅ Confirm Choices"):
            output_selected_files(st.session_state.merged_df_cache)
    else:
        st.info("ℹ️ No products selected yet.")

elif st.session_state.full_product_df is not None:
    st.markdown("---")
    st.subheader("🖼️ Browse Products")
    search_query = st.text_input("🔍 Search Products")
    display_product_tiles(st.session_state.full_product_df, page_key="product", search_query=search_query)

    st.markdown("---")
    st.subheader("🔎 Selected Products Preview")
    selected_handles = st.session_state.selected_handles
    if selected_handles:
        selected_preview = st.session_state.full_product_df[st.session_state.full_product_df['Handle'].isin(selected_handles)]
        display_product_tiles(selected_preview, page_key="selected")
        if st.button("✅ Confirm Choices"):
            output_selected_files(st.session_state.full_product_df)
    else:
        st.info("ℹ️ No products selected yet.")
