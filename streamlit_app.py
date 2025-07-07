import streamlit as st
import pandas as pd
import re
from io import BytesIO
from datetime import datetime
from rapidfuzz import fuzz

st.set_page_config(layout="wide")

st.title("🛒 Dropship Product & Inventory Manager")

# Session state for selections and pagination
if 'selected_handles' not in st.session_state:
    st.session_state.selected_handles = set()
if 'product_df' not in st.session_state:
    st.session_state.product_df = None
if 'last_output_df' not in st.session_state:
    st.session_state.last_output_df = None
if 'merged_df_cache' not in st.session_state:
    st.session_state.merged_df_cache = None
if 'full_product_df' not in st.session_state:
    st.session_state.full_product_df = None

# --- FUNCTIONS ---

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
    df['sku_num'] = df['Variant SKU'].apply(extract_sku_number)
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

def display_product_tiles(merged_df):
    grouped = list(merged_df.groupby("Handle"))

    search_query = st.text_input("🔍 Search Products (Title, Handle, or SKU):")
    if search_query:
        grouped = [
            (handle, group) for handle, group in grouped
            if search_query.lower() in str(group['Title'].iloc[0]).lower()
            or search_query.lower() in handle.lower()
            or any(search_query.lower() in str(sku).lower() for sku in group['Variant SKU'])
        ]

    progress_bar = st.progress(0)
    total = len(grouped)

    for i, (handle, group) in enumerate(grouped):
        with st.expander(f"{group['Title'].iloc[0]}"):
            col1, col2 = st.columns([1, 3])
            with col1:
                main_row = group[group['Variant SKU'].notna()].iloc[0] if not group[group['Variant SKU'].notna()].empty else group.iloc[0]
                main_image = main_row['Image Src']
                st.image(main_image, width=150, caption="Main Image")
                checked = st.checkbox("Select", value=handle in st.session_state.selected_handles, key=handle)
                if checked:
                    st.session_state.selected_handles.add(handle)
                else:
                    st.session_state.selected_handles.discard(handle)
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
        progress_bar.progress((i + 1) / total)

def output_selected_files(merged_df):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    selected_handles = st.session_state.selected_handles
    selected_df = merged_df[merged_df['Handle'].isin(selected_handles)]

    # Add extra rows from the full original product data
    if st.session_state.full_product_df is not None:
        extra_rows = st.session_state.full_product_df[
            st.session_state.full_product_df['Handle'].isin(selected_handles)
        ]
        full_selected_df = fuzzy_match_inventory(extra_rows, pd.DataFrame([{}]))
        selected_df = pd.concat([selected_df, full_selected_df]).drop_duplicates()

    product_columns = [col for col in selected_df.columns if col in st.session_state.original_product_columns]
    inventory_columns = [col for col in selected_df.columns if col in st.session_state.original_inventory_columns]

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
inventory_file = st.file_uploader("Upload latest inventory CSV", type=["csv"])

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
            display_product_tiles(merged_df)

            st.markdown("---")
            st.subheader("🔎 Selected Products Preview")
            selected_preview = merged_df[merged_df['Handle'].isin(st.session_state.selected_handles)]
            for handle, group in selected_preview.groupby("Handle"):
                with st.expander(group['Title'].iloc[0]):
                    col1, col2 = st.columns([1, 3])
                    with col1:
                        main_row = group[group['Variant SKU'].notna()].iloc[0] if not group[group['Variant SKU'].notna()].empty else group.iloc[0]
                        st.image(main_row['Image Src'], width=150)
                        if st.button("❌ Remove", key=f"remove_{handle}"):
                            st.session_state.selected_handles.discard(handle)
                            st.experimental_rerun()
                    with col2:
                        qty_col = 'Available Quantity'
                        if qty_col in group.columns:
                            total_qty = group[qty_col].fillna(0).sum()
                            st.markdown(f"**Available:** {int(total_qty)}")

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
    display_product_tiles(st.session_state.merged_df_cache)

    st.markdown("---")
    st.subheader("🔎 Selected Products Preview")
    selected_preview = st.session_state.merged_df_cache[st.session_state.merged_df_cache['Handle'].isin(st.session_state.selected_handles)]
    for handle, group in selected_preview.groupby("Handle"):
        with st.expander(group['Title'].iloc[0]):
            col1, col2 = st.columns([1, 3])
            with col1:
                main_row = group[group['Variant SKU'].notna()].iloc[0] if not group[group['Variant SKU'].notna()].empty else group.iloc[0]
                st.image(main_row['Image Src'], width=150)
                if st.button("❌ Remove", key=f"remove_{handle}"):
                    st.session_state.selected_handles.discard(handle)
                    st.experimental_rerun()
            with col2:
                qty_col = 'Available Quantity'
                if qty_col in group.columns:
                    total_qty = group[qty_col].fillna(0).sum()
                    st.markdown(f"**Available:** {int(total_qty)}")

    if st.button("✅ Confirm Choices"):
        output_selected_files(st.session_state.merged_df_cache)
else:
    st.info("👆 Please upload your product and inventory files, then press 'Process Files' to begin.")
