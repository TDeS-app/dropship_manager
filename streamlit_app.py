import streamlit as st
import pandas as pd
import re
from io import BytesIO
from datetime import datetime
from rapidfuzz import fuzz

st.set_page_config(layout="wide")

st.title("🛒 Dropship Product & Inventory Manager")

# Session state for selections
if 'selected_handles' not in st.session_state:
    st.session_state.selected_handles = set()

if 'product_df' not in st.session_state:
    st.session_state.product_df = None

if 'last_output_df' not in st.session_state:
    st.session_state.last_output_df = None

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

def fuzzy_match_inventory(product_df, inventory_df):
    product_df['sku_num'] = product_df['Variant SKU'].apply(extract_sku_number)
    inventory_df['sku_num'] = inventory_df['Variant SKU'].apply(extract_sku_number)

    merged_rows = []

    for _, prod_row in product_df.iterrows():
        best_match = None
        best_score = 0

        for _, inv_row in inventory_df.iterrows():
            if prod_row['sku_num'] and prod_row['sku_num'] == inv_row['sku_num']:
                title_score = fuzz.token_sort_ratio(str(prod_row['Title']), str(inv_row['Title']))
                if title_score > 90:
                    best_match = inv_row
                    break
                elif title_score > best_score:
                    best_match = inv_row
                    best_score = title_score

        if best_match is not None:
            merged_row = pd.concat([prod_row, best_match.drop(labels=product_df.columns.intersection(inventory_df.columns))])
        else:
            merged_row = prod_row
        merged_rows.append(merged_row)

    merged_df = pd.DataFrame(merged_rows)
    return merged_df

def display_product_tiles(merged_df):
    grouped = merged_df.groupby("Handle")

    for handle, group in grouped:
        with st.container():
            col1, col2 = st.columns([1, 3])

            with col1:
                main_row = group[group['Variant SKU'].notna()].iloc[0] if not group[group['Variant SKU'].notna()].empty else group.iloc[0]
                main_image = main_row['Image Src']
                st.image(main_image, width=150, caption="Main Image")
                checked = st.checkbox(f"Select: {main_row['Title']}", value=handle in st.session_state.selected_handles, key=handle)
                if checked:
                    st.session_state.selected_handles.add(handle)
                else:
                    st.session_state.selected_handles.discard(handle)

            with col2:
                st.markdown(f"**Product Title:** {main_row['Title']}")

                # Inventory info
                qty_col = 'Available Quantity'
                if qty_col not in group.columns:
                    alt_qty = [c for c in group.columns if 'Available' in c]
                    qty_col = alt_qty[0] if alt_qty else None
                if qty_col:
                    total_qty = group[qty_col].fillna(0).sum()
                    st.markdown(f"**Available:** {int(total_qty)}")
                else:
                    st.markdown("❓ *No inventory data found*")

def output_selected_files(merged_df):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    selected_df = merged_df[merged_df['Handle'].isin(st.session_state.selected_handles)]

    # Split product and inventory back into two files
    product_columns = [col for col in selected_df.columns if col in st.session_state.original_product_columns]
    inventory_columns = [col for col in selected_df.columns if col in st.session_state.original_inventory_columns]

    product_output = selected_df[product_columns]
    inventory_output = selected_df[inventory_columns]

    # Save to session for future incremental updates
    st.session_state.last_output_df = selected_df.copy()
    st.session_state.product_df = selected_df.copy()

    # Download buttons
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

if product_files and inventory_file:
    product_dfs = [read_csv_with_fallback(file) for file in product_files]
    product_dfs = [df for df in product_dfs if df is not None]
    inventory_df = read_csv_with_fallback(inventory_file)

    if product_dfs and inventory_df is not None:
        product_df = pd.concat(product_dfs, ignore_index=True)
        st.session_state.original_product_columns = product_df.columns.tolist()
        st.session_state.original_inventory_columns = inventory_df.columns.tolist()

        merged_df = fuzzy_match_inventory(product_df, inventory_df)

        st.markdown("---")
        st.subheader("🖼️ Browse Products")
        display_product_tiles(merged_df)

        st.markdown("---")
        if st.button("✅ Confirm Choices"):
            st.success("📝 Confirmed! Generating download files...")
            output_selected_files(merged_df)

elif inventory_file and st.session_state.product_df is not None:
    inventory_df = read_csv_with_fallback(inventory_file)
    if inventory_df is not None:
        merged_df = fuzzy_match_inventory(st.session_state.product_df, inventory_df)
        st.subheader("🆕 Inventory Updated")
        output_selected_files(merged_df)

else:
    st.info("👆 Please upload your product and inventory files to begin.")
