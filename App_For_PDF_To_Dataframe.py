import streamlit as st
import subprocess
import os
import platform
import tempfile
import logging
import pandas as pd
import camelot as cam
from PyPDF2 import PdfReader
from contextlib import contextmanager
from io import BytesIO
from pdf2image import convert_from_bytes

# --------------------------
# Logging Configuration
# --------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)
logger = logging.getLogger(__name__)

# --------------------------
# Streamlit Page Config
# --------------------------
st.set_page_config(page_title="PDF Table Extractor", page_icon="📋", layout="wide")

# --------------------------
# Ghostscript Handling
# --------------------------
@st.cache_resource
def check_ghostscript():
    if platform.system() == "Windows":
        gs_paths = ["C:\\Program Files\\gs", "C:\\Program Files (x86)\\gs"]
        return any(os.path.exists(p) for p in gs_paths)
    try:
        subprocess.run(["gs", "--version"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def handle_ghostscript_dependencies():
    if not check_ghostscript():
        if platform.system() != "Windows":
            if st.button("Install Ghostscript automatically?"):
                with st.spinner("Installing Ghostscript..."):
                    try:
                        subprocess.run(["sudo", "apt-get", "install", "-y", "ghostscript"],
                                       check=True, stdout=subprocess.DEVNULL)
                        st.success("Ghostscript installed successfully. Please rerun.")
                        st.stop()
                    except subprocess.CalledProcessError as e:
                        st.error(f"Installation failed: {e}")
                        st.stop()
        else:
            st.error("Ghostscript required! Please install from https://www.ghostscript.com/")
        st.stop()

# --------------------------
# PDF Utilities
# --------------------------
@st.cache_data
def get_total_pages(pdf_bytes: bytes) -> int:
    reader = PdfReader(BytesIO(pdf_bytes))
    return len(reader.pages)

@st.cache_data
def convert_page_to_image(pdf_bytes: bytes, page_num: int, dpi: int = 100):
    images = convert_from_bytes(
        pdf_bytes, dpi=dpi, first_page=page_num, last_page=page_num
    )
    return images[0] if images else None

@contextmanager
def temp_pdf_file(uploaded_file):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.getbuffer())
        yield tmp.name
    try:
        os.unlink(tmp.name)
    except FileNotFoundError:
        pass

# --------------------------
# Table Cleaning
# --------------------------
def clean_table(df: pd.DataFrame) -> pd.DataFrame:
    # Trim whitespace and normalize types
    return df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

# --------------------------
# App UI
# --------------------------
handle_ghostscript_dependencies()
st.title("📋 PDF Table Extraction")
st.subheader("Smart Table Extraction with Multi-Page Preview & Export")

with st.expander("ℹ️ How to use"):
    st.markdown(
        """
        1. Upload a PDF containing tables
        2. Select pages to preview & analyze
        3. Choose detection method
        4. View & clean tables
        5. Export as CSV/Excel
        """
    )

# Upload PDF
input_pdf = st.file_uploader("Upload PDF", type=["pdf"], help="Max size: 200MB")
if not input_pdf:
    st.info("👆 Upload a PDF to get started.")
    st.stop()

# Read bytes once
pdf_bytes = input_pdf.read()

# Total pages
try:
    total_pages = get_total_pages(pdf_bytes)
    st.success(f"Loaded PDF with {total_pages} pages.")
except Exception as e:
    logger.error(f"Failed to read PDF: {e}")
    st.error("Could not read PDF file.")
    st.stop()

# Interactive page picker
page_options = [str(i) for i in range(1, total_pages + 1)]
selected_pages = st.multiselect(
    "Select pages to preview & extract", options=page_options, default=["1"],
    help="Choose one or more pages for preview and table detection"
)
if not selected_pages:
    st.warning("Please select at least one page.")
    st.stop()
selected_pages_int = [int(p) for p in selected_pages]

# Preview selected pages
with st.expander("🔍 PDF Preview", expanded=False):
    progress = st.progress(0)
    for idx, pg in enumerate(selected_pages_int):
        img = convert_page_to_image(pdf_bytes, pg)
        if img:
            st.image(img, caption=f"Page {pg}", use_container_width=True)
        else:
            st.error(f"Could not render page {pg}.")
        progress.progress((idx + 1) / len(selected_pages_int))

# Detection method
flavor = st.selectbox(
    "Table detection method", ["lattice", "stream"], index=0,
    help="Lattice: structured tables, Stream: less structured"
)

# Extract tables
if st.button("🚀 Extract Tables"):
    progress = st.progress(0)
    with st.spinner("Detecting tables..."):
        try:
            tables = cam.read_pdf(
                BytesIO(pdf_bytes), pages=','.join(selected_pages), flavor=flavor
            )
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            st.error("Extraction failed. Try a different method or page selection.")
            st.stop()
    if not tables:
        st.warning("No tables found. You may try OCR fallback or switch detection mode.")
        # OCR fallback button placeholder
    else:
        st.success(f"Found {len(tables)} tables.")
        # Clean tables
        for t in tables:
            t.df = clean_table(t.df)
        st.session_state.tables = tables
        st.experimental_rerun()

# Display & export
if 'tables' in st.session_state and st.session_state.tables:
    tables = st.session_state.tables
    # Select one to view
    options = [f"Table {i+1} (Pg {t.page})" for i, t in enumerate(tables)]
    sel = st.selectbox("Select table to view", options)
    idx = options.index(sel)
    df = tables[idx].df
    st.dataframe(df, height=300)

    # Download CSV of viewed table
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        "💾 Download Table as CSV", data=csv,
        file_name=f"table_{idx+1}.csv", mime="text/csv"
    )

    # Multi-export: select multiple tables
    multi = st.multiselect(
        "Select tables to download (Excel)", options, default=[options[idx]]
    )
    sel_idxs = [options.index(m) for m in multi]
    if multi:
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            for i in sel_idxs:
                sheet = f"table_{tables[i].page}.{i+1}"[:31]
                tables[i].df.to_excel(writer, sheet_name=sheet, index=False)
        buffer.seek(0)
        st.download_button(
            "📊 Download Selected Tables (Excel)", data=buffer,
            file_name=os.path.splitext(input_pdf.name)[0] + ".xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    # Reset
    if st.button("🔄 New PDF"):  # clear state
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.experimental_rerun()

# Footer
st.markdown("---")
st.markdown("*Powered by Camelot, PyPDF2 & Streamlit*")
