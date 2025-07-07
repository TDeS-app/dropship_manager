import streamlit as st
import pandas as pd
from io import StringIO
from datetime import datetime

st.set_page_config(page_title="Dropship Manager", layout="wide")
st.title("🛒 Dropship Product & Inventory Manager")

# --- File Upload ---
st.sidebar.header("📁 Upload Files")

product_files = st.sidebar.file_uploader(
    "Upload Product CSV(s)", type="csv", accept_multiple_files=True
)
inventory_file = st.sidebar.file_uploader(
    "Upload Inventory CSV", type="csv", accept_multiple_files=False
)

if not product_files:
    st.warning("Please upload at least one Product CSV to continue.")
    st.stop()

if not inventory_file:
    st.warning("Please upload the Inventory CSV to continue.")
    st.stop()

# --- Read product files safely ---
product_dfs = []
for file in product_files:
    try:
        df = pd.read_csv(file, encoding='utf-8-sig')
        product_dfs.append(df)
    except Exception as e:
        st.warning(f"⚠️ Could not read {file.name}: {e}")

if not product_dfs:
    st.error("❌ No valid product files could be read.")
    st.stop()

product_df = pd.concat(product_dfs, ignore_index=True)

# --- Read inventory file safely ---
try:
    inventory_df = pd.read_csv(inventory_file, encoding='utf-8-sig')
except Exception as e:
    st.error(f"❌ Could not read inventory file: {e}")
    st.stop()

# --- Clean column names ---
product_df.columns = product_df.columns.str.strip()
inventory_df.columns = inventory_df.columns.str.strip()

# --- Check required column exists ---
if 'Variant SKU' not in product_df.columns:
    st.error("❌ 'Variant SKU' column not found in Product file.")
    st.stop()

if 'Variant SKU' not in inventory_df.columns:
    st.error("❌ 'Variant SKU' column not found in Inventory file.")
    st.stop()

# --- Merge inventory into product data ---
merged_df = product_df.merge(inventory_df, on='Variant SKU', how='left')

# --- Group by product handle ---
grouped = merged_df.groupby('Handle')

selected_handles = set()

st.subheader("🧾 Product Browser")

for handle, group in grouped:
    main_row = group[group['Variant SKU'] == handle]
    if main_row.empty:
        main_row = group.iloc[[0]]

    product_title = main_row['Title'].values[0]
    image_url = main_row['Image Src'].values[0] if 'Image Src' in main_row else ""

    with st.expander(f"📦 {product_title}"):
        cols = st.columns([1, 2])
        with cols[0]:
            if image_url:
                st.image(image_url, width=150)
            else:
                st.text("No image available")
        with cols[1]:
            st.write(group[['Variant SKU', 'Option1 Value', 'Available Quantity']])

        selected = st.checkbox("Select this product", key=handle)
        if selected:
            selected_handles.add(handle)

# --- Export button ---
if st.button("✅ Confirm Choices and Export Files"):
    if not selected_handles:
        st.warning("Please select at least one product before exporting.")
        st.stop()

    # Filter selected products
    selected_products = merged_df[merged_df['Handle'].isin(selected_handles)]
    selected_inventory = inventory_df[inventory_df['Variant SKU'].isin(selected_products['Variant SKU'])]

    # Output files
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    product_filename = f"selected_products_{timestamp}.csv"
    inventory_filename = f"selected_inventory_{timestamp}.csv"

    st.success("✅ Files generated successfully!")

    st.download_button("⬇️ Download Product File", selected_products.to_csv(index=False), product_filename)
    st.download_button("⬇️ Download Inventory File", selected_inventory.to_csv(index=False), inventory_filename)
