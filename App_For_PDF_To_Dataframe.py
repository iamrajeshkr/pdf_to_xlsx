# -*- coding: utf-8 -*-
import streamlit as st
import subprocess
import os
import base64
import camelot as cam
import platform
import tempfile
import pandas as pd
from PyPDF2 import PdfReader
from contextlib import contextmanager
from io import BytesIO
import streamlit as st
import subprocess
import os
import base64
import camelot as cam
import platform
import tempfile
import pandas as pd
from PyPDF2 import PdfReader
from contextlib import contextmanager
from io import BytesIO
from pdf2image import convert_from_bytes
# --------------------------
# Core Configuration & Setup
# --------------------------
st.set_page_config(page_title="PDF Table Genius", page_icon="📋", layout="wide")

# --------------------------
# Ghostscript Handling
# --------------------------
@st.cache_resource
def check_ghostscript():
    """Check Ghostscript installation without Streamlit elements"""
    if platform.system() == "Windows":
        gs_paths = ["C:\\Program Files\\gs", "C:\\Program Files (x86)\\gs"]
        return any(os.path.exists(p) for p in gs_paths)
    else:
        try:
            subprocess.run(["gs", "--version"], check=True, 
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

def handle_ghostscript_dependencies():
    """Main dependency handling with proper UI separation"""
    if not check_ghostscript():
        if platform.system() != "Windows":
            if st.button("Install Ghostscript automatically?"):
                try:
                    with st.spinner("Installing Ghostscript..."):
                        subprocess.run(["sudo", "apt-get", "install", "-y", "ghostscript"],
                                     check=True, stdout=subprocess.DEVNULL)
                    st.success("Ghostscript installed successfully!")
                    st.rerun()
                except subprocess.CalledProcessError as e:
                    st.error(f"Installation failed: {str(e)}")
        else:
            st.error("Ghostscript required! [Download here](https://www.ghostscript.com/)")
        st.stop()

# --------------------------
# File Handling Utilities
# --------------------------
@contextmanager
def temp_pdf_file(uploaded_file):
    """Context manager for temporary PDF files"""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.getbuffer())
            yield tmp.name
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)

def get_total_pages(pdf_path):
    """Get total number of pages in PDF"""
    with open(pdf_path, "rb") as f:
        return len(PdfReader(f).pages)

# --------------------------
# UI Components
# --------------------------
def show_pdf_preview(uploaded_file):
    # Convert the first page of the PDF to an image
    try:
        pdf_bytes = uploaded_file.read()
        images = convert_from_bytes(pdf_bytes, first_page=1, last_page=total_pages)
        if images:
            img_bytes = BytesIO()
            images[0].save(img_bytes, format='PNG')
            img_bytes.seek(0)
            st.image(img_bytes, caption='First Page Preview', use_column_width=True)
        else:
            st.error("Could not generate preview")
    except Exception as e:
        st.error(f"Preview generation failed: {str(e)}")
    finally:
        uploaded_file.seek(0)

# --------------------------
# Main Application
# --------------------------
handle_ghostscript_dependencies()

st.title("📋 PDF Table Genius")
st.subheader("Smart Table Extraction with Multi-Page & Excel Export")

with st.expander("ℹ️ How to use"):
    st.markdown("""
    1. Upload a PDF file containing tables
    2. Select pages to analyze (e.g. 1,3-5)
    3. Choose table detection method
    4. Select and export tables
    """)

input_pdf = st.file_uploader("Upload PDF", type=["pdf"], help="Maximum file size: 200MB")

if input_pdf:
    with temp_pdf_file(input_pdf) as tmp_path:
        try:
            total_pages = get_total_pages(tmp_path)
            st.success(f"📄 Loaded PDF with {total_pages} pages")
            
            # Page selection
            col1, col2 = st.columns(2)
            with col1:
                pages = st.text_input(
                    "Pages to analyze (e.g.: 1,3-5)", 
                    value="1",
                    help="Comma-separated page numbers or ranges"
                )
            with col2:
                flavor = st.selectbox(
                    "Table detection method",
                    ["lattice (structured tables)", "stream (less structured)"],
                    index=0
                ).split(" ")[0]

            # PDF preview
            with st.expander("🔍 PDF Preview", expanded=True):
                show_pdf_preview(input_pdf)

            if st.button("🚀 Extract Tables"):
                with st.spinner("🔍 Analyzing PDF structure..."):
                    try:
                        st.session_state.tables = cam.read_pdf(
                            tmp_path,
                            pages=pages,
                            flavor=flavor,
                            suppress_stdout=False
                        )
                        st.session_state.selected_table = 0
                        st.success(f"🎉 Found {len(st.session_state.tables)} tables!")
                    except Exception as e:
                        st.error(f"❌ Extraction failed: {str(e)}")
                        st.stop()

            # Show tables if they exist in session state
            if 'tables' in st.session_state and len(st.session_state.tables) > 0:
                # Table selection
                selected_table = st.selectbox(
                    "Select table to view",
                    options=[f"Table {i+1}" for i in range(len(st.session_state.tables))],
                    index=st.session_state.get('selected_table', 0),
                    key='table_selector'
                )
                table_idx = int(selected_table.split(" ")[1]) - 1
                st.session_state.selected_table = table_idx
                
                # Display table
                st.dataframe(
                    st.session_state.tables[table_idx].df,
                    height=400,
                    use_container_width=True
                )

                # Export options
                col1, col2, col3 = st.columns(3)
                with col1:
                    csv = st.session_state.tables[table_idx].df.to_csv(index=False)
                    st.download_button(
                        "💾 Download Current CSV",
                        data=csv,
                        file_name=f"table_{table_idx+1}.csv",
                        mime="text/csv"
                    )

                with col2:
                    # Excel export logic
                    excel_name = os.path.splitext(input_pdf.name)[0] + ".xlsx"
                    buffer = BytesIO()
                    
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        page_counter = {}
                        
                        for idx, table in enumerate(st.session_state.tables):
                            page = table.page
                            if page not in page_counter:
                                page_counter[page] = 1
                            else:
                                page_counter[page] += 1
                            
                            sheet_name = f"table_{page}.{page_counter[page]}"
                            table.df.to_excel(
                                writer,
                                sheet_name=sheet_name[:31],  # Excel sheet name limit
                                index=False
                            )
                    
                    buffer.seek(0)
                    st.download_button(
                        "📊 Download All Tables (Excel)",
                        data=buffer,
                        file_name=excel_name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        help="All tables in single Excel file with multiple sheets"
                    )

                with col3:
                    if st.button("🔄 Process New PDF"):
                        st.session_state.clear()
                        st.rerun()

        except Exception as e:
            st.error(f"❌ PDF processing error: {str(e)}")
            st.stop()
else:
    st.info("👆 Upload a PDF file to get started")

# --------------------------
# Footer & Cleanup
# --------------------------
st.markdown("---")
st.markdown("*Powered by Camelot, PyPDF2, and Streamlit*")
