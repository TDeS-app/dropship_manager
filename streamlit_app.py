import streamlit as st
import pandas as pd
import re
import os
import json
from io import BytesIO
from datetime import datetime
from rapidfuzz import fuzz

st.set_page_config(layout="wide")

st.title("🛒 Dropship Product & Inventory Manager")

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
    start = (page - 1) * PRODUCTS_PER_PAGE
    end = start + PRODUCTS_PER_PAGE
    return grouped[start:end]

def display_pagination_controls(total, current_page, key_prefix):
    total_pages = (total + PRODUCTS_PER_PAGE - 1) // PRODUCTS_PER_PAGE
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if current_page > 1:
            if st.button("⬅️ Prev", key=f"{key_prefix}_prev"):
                st.session_state[f"{key_prefix}_page"] -= 1
    with col2:
        st.selectbox(
            f"Page ({key_prefix})",
            options=list(range(1, total_pages + 1)),
            index=current_page - 1,
            key=f"{key_prefix}_page_selector",
            on_change=lambda: st.session_state.update({f"{key_prefix}_page": st.session_state[f"{key_prefix}_page_selector"]})
        )
    with col3:
        if current_page < total_pages:
            if st.button("➡️ Next", key=f"{key_prefix}_next"):
                st.session_state[f"{key_prefix}_page"] += 1

def display_product_tiles(merged_df, page_key, search_query=""):
    grouped = list(merged_df.groupby("Handle"))

    if search_query:
        grouped = [
            (handle, group) for handle, group in grouped
            if search_query.lower() in str(group['Title'].iloc[0]).lower()
            or search_query.lower() in handle.lower()
            or any(search_query.lower() in str(sku).lower() for sku in group.get('Variant SKU', group.get('SKU', [])))
        ]

    total = len(grouped)
    current_page = st.session_state[f"{page_key}_page"]
    paginated_grouped = paginate_list(grouped, current_page)

    for handle, group in paginated_grouped:
        handle_str = str(handle)
        sku_col = 'Variant SKU' if 'Variant SKU' in group.columns else 'SKU' if 'SKU' in group.columns else None
        main_row = group[group[sku_col].notna()].iloc[0] if sku_col and not group[sku_col].notna().empty else group.iloc[0]

        cols = st.columns([0.05, 0.95])
        with cols[0]:
            checked = st.checkbox("", value=handle_str in st.session_state.selected_handles, key=f"chk_{page_key}_{handle_str}")
        with cols[1]:
            with st.expander(f"{group['Title'].iloc[0]}"):
                col1, col2 = st.columns([1, 3])
                with col1:
                    st.image(main_row['Image Src'], width=150, caption="Main Image")
                with col2:
                    qty_col = 'Available Quantity'
                    if qty_col not in group.columns:
                        alt_qty = [c for c in group.columns if 'Available' in c]
                        qty_col = alt_qty[0] if alt_qty else None
                    if qty_col:
                        total_qty = group[qty_col].fillna(0).sum()
                        st.markdown(f"**Available:** {int(total_qty)}")
                    else:
                        st.markdown("❓ *No inventory data found*")

        if checked:
            st.session_state.selected_handles.add(handle_str)
        else:
            st.session_state.selected_handles.discard(handle_str)
        save_selected_handles()

    display_pagination_controls(total, current_page, page_key)

def output_selected_files(merged_df):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    selected_handles = st.session_state.selected_handles
    selected_df = merged_df[merged_df['Handle'].isin(selected_handles)]

    if st.session_state.full_product_df is not None:
        extra_rows = st.session_state.full_product_df[
            st.session_state.full_product_df['Handle'].isin(selected_handles)
        ]
        selected_df = pd.concat([selected_df, extra_rows]).drop_duplicates()

    product_columns = [col for col in selected_df.columns if 'original_product_columns' in st.session_state and col in st.session_state.original_product_columns]
    inventory_columns = [col for col in selected_df.columns if 'original_inventory_columns' in st.session_state and col in st.session_state.original_inventory_columns]

    if not product_columns:
        product_columns = [col for col in selected_df.columns if 'SKU' in col or 'Title' in col or 'Handle' in col or 'Image Src' in col]
    if not inventory_columns:
        inventory_columns = [col for col in selected_df.columns if 'Available' in col or 'SKU' in col]

    product_output = selected_df[product_columns]
    inventory_output = selected_df[inventory_columns]

    st.session_state.last_output_df = selected_df.copy()
    st.session_state.product_df = selected_df.copy()

    st.success("✅ Files ready for download!")

    st.download_button(
        label="📁 Download Product CSV",
        data=product_output.to_csv(index=False).encode('utf-8'),
        file_name=f"products_selected_{timestamp}.csv",
        mime="text/csv"
    )
    st.download_button(
        label="📦 Download Inventory CSV",
        data=inventory_output.to_csv(index=False).encode('utf-8'),
        file_name=f"inventory_selected_{timestamp}.csv",
        mime="text/csv"
    )

# --- MAIN APP FLOW ---

st.subheader("📤 Upload Product CSV(s)")
product_files = st.file_uploader("Upload one or more product CSVs", accept_multiple_files=True, type=["csv"])

st.subheader("📥 Upload Inventory CSV")
inventory_file = st.file_uploader("Upload latest inventory CSV. Change 'Variant SKU' to SKU'", type=["csv"])

if st.button("🔄 Process Files"):
    if product_files and inventory_file:
        product_dfs = [read_csv_with_fallback(file) for file in product_files]
        product_dfs = [df for df in product_dfs if df is not None]
        inventory_df = read_csv_with_fallback(inventory_file)

        if product_dfs and inventory_df is not None:
            product_df = pd.concat(product_dfs, ignore_index=True)
            st.session_state.full_product_df = product_df.copy()
            st.session_state.original_product_columns = product_df.columns.tolist()
            st.session_state.original_inventory_columns = inventory_df.columns.tolist()

            merged_df = fuzzy_match_inventory(product_df, inventory_df)
            st.session_state.merged_df_cache = merged_df.copy()

            st.markdown("---")
            st.subheader("🖼️ Browse Products")
            search_query = st.text_input("🔍 Search Products")
            display_product_tiles(merged_df, page_key="product", search_query=search_query)

            st.markdown("---")
            st.subheader("🔎 Selected Products Preview")
            selected_preview = merged_df[merged_df['Handle'].isin(st.session_state.selected_handles)]
            display_product_tiles(selected_preview, page_key="selected")

            if st.button("✅ Confirm Choices"):
                output_selected_files(merged_df)

elif inventory_file and st.session_state.product_df is not None:
    if st.button("📦 Update Inventory Only"):
        inventory_df = read_csv_with_fallback(inventory_file)
        if inventory_df is not None:
            merged_df = fuzzy_match_inventory(st.session_state.product_df, inventory_df)
            st.session_state.merged_df_cache = merged_df.copy()
            st.subheader("🆕 Inventory Updated")
            output_selected_files(merged_df)

elif st.session_state.merged_df_cache is not None:
    st.markdown("---")
    st.subheader("🖼️ Browse Products (Cached)")
    search_query = st.text_input("🔍 Search Products")
    display_product_tiles(st.session_state.merged_df_cache, page_key="product", search_query=search_query)

    st.markdown("---")
    st.subheader("🔎 Selected Products Preview")
    selected_preview = st.session_state.merged_df_cache[st.session_state.merged_df_cache['Handle'].isin(st.session_state.selected_handles)]
    display_product_tiles(selected_preview, page_key="selected")

    if st.button("✅ Confirm Choices"):
        output_selected_files(st.session_state.merged_df_cache)
else:
    st.info("👆 Please upload your product and inventory files, then press 'Process Files' to begin.")
