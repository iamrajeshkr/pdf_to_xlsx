# -*- coding: utf-8 -*-
import streamlit as st
import subprocess
import os
import base64
import platform
import tempfile
import json
import time
from datetime import datetime
from io import BytesIO
from contextlib import contextmanager

# Third-party imports
import camelot as cam
import pandas as pd
from PyPDF2 import PdfReader
from pdf2image import convert_from_bytes
import plotly.express as px

# --------------------------
# Core Configuration & Setup
# --------------------------
st.set_page_config(
    page_title="PDF Table Extractor", 
    page_icon="📋", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --------------------------
# Custom Styling
# --------------------------
def apply_custom_styling():
    st.markdown("""
    <style>
        /* App-wide styling */
        .main { padding: 1rem 2rem; }
        
        /* Headers */
        h1 { color: #2c3e50; margin-bottom: 1.5rem !important; }
        h2 { color: #34495e; margin-bottom: 1rem !important; }
        h3 { color: #7f8c8d; }
        
        /* Card-like containers */
        .card {
            border: 1px solid #e6e9ef;
            border-radius: 0.5rem;
            padding: 1.5rem;
            margin-bottom: 1rem;
            background-color: #ffffff;
            box-shadow: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24);
        }
        
        /* PDF Preview container */
        .pdf-preview {
            max-height: 600px;
            overflow-y: auto;
            border: 1px solid #e6e9ef;
            border-radius: 5px;
            padding: 10px;
            background-color: #f8f9fa;
        }
        
        /* Buttons */
        .stButton button {
            border-radius: 4px;
            height: 2.5rem;
            transition: all 0.2s ease;
        }
        .primary-button button {
            background-color: #4f8bf9;
            color: white;
            font-weight: 600;
        }
        
        /* Table thumbnails */
        .table-thumbnail {
            border: 1px solid #ddd;
            padding: 5px;
            cursor: pointer;
        }
        .table-thumbnail-selected {
            border: 2px solid #4f8bf9;
            box-shadow: 0 0 5px rgba(79, 139, 249, 0.5);
        }
        
        /* Toast notifications */
        .toast {
            position: fixed;
            top: 1rem;
            right: 1rem;
            background: #333;
            color: white;
            padding: 0.5rem 1rem;
            border-radius: 4px;
            z-index: 9999;
            animation: fadeInOut 3s ease;
        }
        @keyframes fadeInOut {
            0% { opacity: 0; }
            10% { opacity: 1; }
            90% { opacity: 1; }
            100% { opacity: 0; }
        }
    </style>
    """, unsafe_allow_html=True)

apply_custom_styling()

# --------------------------
# State Management
# --------------------------
def initialize_session_state():
    if 'page' not in st.session_state:
        st.session_state.page = 'upload'
    
    if 'tables' not in st.session_state:
        st.session_state.tables = None
    
    if 'selected_table' not in st.session_state:
        st.session_state.selected_table = 0
    
    if 'pdf_path' not in st.session_state:
        st.session_state.pdf_path = None
        
    if 'extraction_settings' not in st.session_state:
        st.session_state.extraction_settings = {
            'pages': '1',
            'flavor': 'lattice',
            'method': 'standard'
        }
    
    if 'dark_mode' not in st.session_state:
        st.session_state.dark_mode = False
    
    if 'extraction_history' not in st.session_state:
        st.session_state.extraction_history = []
    
    if 'pdf_info' not in st.session_state:
        st.session_state.pdf_info = None
    
    if 'total_pages' not in st.session_state:
        st.session_state.total_pages = 0

initialize_session_state()

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
    if not check_ghostscript():
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.warning("⚠️ Ghostscript is required for PDF processing")
        
        if platform.system() != "Windows":
            if st.button("Install Ghostscript automatically?", key="install_gs"):
                try:
                    with st.spinner("Installing Ghostscript..."):
                        subprocess.run(["sudo", "apt-get", "install", "-y", "ghostscript"],
                                    check=True, stdout=subprocess.DEVNULL)
                    st.success("Ghostscript installed successfully!")
                    time.sleep(2)
                    st.rerun()
                except subprocess.CalledProcessError as e:
                    st.error(f"Installation failed: {str(e)}")
                    st.info("Please try installing Ghostscript manually: `sudo apt-get install ghostscript`")
        else:
            st.info("Please download and install Ghostscript:")
            st.markdown("""
            1. [Download Ghostscript for Windows](https://www.ghostscript.com/download/gsdnld.html)
            2. Run the installer and follow instructions
            3. Restart this application after installation
            """)
        st.markdown('</div>', unsafe_allow_html=True)
        st.stop()

# --------------------------
# File Handling Utilities
# --------------------------
@contextmanager
def temp_pdf_file(uploaded_file):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.getbuffer())
            yield tmp.name
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)

def get_pdf_info(pdf_path):
    with open(pdf_path, "rb") as f:
        reader = PdfReader(f)
        total_pages = len(reader.pages)
        info = reader.metadata
        
        # Extract basic info from the first page
        first_page = reader.pages[0]
        width, height = first_page.mediabox.width, first_page.mediabox.height
        
        return {
            "total_pages": total_pages,
            "title": info.title if info and info.title else "Untitled",
            "author": info.author if info and info.author else "Unknown",
            "creation_date": info.creation_date if info and info.creation_date else None,
            "dimensions": f"{width:.1f} x {height:.1f} points",
            "file_size": os.path.getsize(pdf_path) / (1024 * 1024), # in MB
        }

def save_upload_for_session(uploaded_file):
    with temp_pdf_file(uploaded_file) as tmp_path:
        # Get a more persistent temporary file
        persistent_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        persistent_tmp.close()
        
        # Copy to persistent temp file
        with open(tmp_path, 'rb') as src, open(persistent_tmp.name, 'wb') as dst:
            dst.write(src.read())
        
        # Store in session state
        st.session_state.pdf_path = persistent_tmp.name
        st.session_state.pdf_info = get_pdf_info(persistent_tmp.name)
        st.session_state.total_pages = st.session_state.pdf_info["total_pages"]
        
        # Reset other states
        st.session_state.tables = None
        st.session_state.selected_table = 0
        
        return persistent_tmp.name

# --------------------------
# UI Components
# --------------------------
def show_pdf_preview(pdf_path, highlight_areas=None):
    try:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        
        with st.spinner("Generating PDF preview..."):
            # Convert all pages to images
            images = convert_from_bytes(pdf_bytes, thread_count=4)
            
            if not images:
                st.error("Could not generate preview")
                return

            # Create a container with fixed height and scroll
            st.markdown('<div class="pdf-preview">', unsafe_allow_html=True)
            
            # Add zoom controls
            zoom_level = st.slider("Zoom", min_value=50, max_value=150, value=100, step=10, key="pdf_zoom")
            zoom_factor = zoom_level / 100.0
            
            # Display images with spacing
            for i, image in enumerate(images):
                # Resize based on zoom
                width, height = image.size
                new_width, new_height = int(width * zoom_factor), int(height * zoom_factor)
                image = image.resize((new_width, new_height))
                
                img_bytes = BytesIO()
                image.save(img_bytes, format='JPEG', quality=85)
                img_bytes.seek(0)
                
                # If we have highlight areas for this page, draw them
                if highlight_areas and i+1 in highlight_areas:
                    st.markdown(f"<h3>Page {i+1} - Tables detected</h3>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<h3>Page {i+1}</h3>", unsafe_allow_html=True)
                
                st.image(
                    img_bytes,
                    use_container_width=True,
                    output_format="JPEG"
                )
                st.write("")  # Add spacing between pages

            st.markdown('</div>', unsafe_allow_html=True)
                
    except Exception as e:
        st.error(f"Preview generation failed: {str(e)}")

def create_table_thumbnail(df, max_rows=5, max_cols=5):
    preview_df = df.iloc[:max_rows, :max_cols].copy()
    
    # If dataframe is too large, add indication
    more_rows = df.shape[0] > max_rows
    more_cols = df.shape[1] > max_cols
    
    # Generate HTML table with custom styling
    html = f"""
    <div style="overflow-x: auto; font-size: 0.7em;">
        <table style="border-collapse: collapse; width: 100%;">
            <thead>
                <tr>
                    {' '.join(f'<th style="border: 1px solid #ddd; padding: 4px; text-align: left;">{col}</th>' for col in preview_df.columns)}
                    {f'<th style="border: 1px solid #ddd; padding: 4px; text-align: center;">...</th>' if more_cols else ''}
                </tr>
            </thead>
            <tbody>
    """
    
    # Add rows
    for _, row in preview_df.iterrows():
        html += '<tr>'
        for val in row:
            html += f'<td style="border: 1px solid #ddd; padding: 4px;">{val}</td>'
        if more_cols:
            html += '<td style="border: 1px solid #ddd; padding: 4px; text-align: center;">...</td>'
        html += '</tr>'
    
    # Add indicator for more rows
    if more_rows:
        html += f"""
        <tr>
            <td style="border: 1px solid #ddd; padding: 4px; text-align: center;" colspan="{preview_df.shape[1] + (1 if more_cols else 0)}">...</td>
        </tr>
        """
    
    html += """
            </tbody>
        </table>
    </div>
    <div style="text-align: center; margin-top: 3px; font-size: 0.8em;">
        <span>{0} rows × {1} columns</span>
    </div>
    """.format(df.shape[0], df.shape[1])
    
    return html

def show_toast(message, type="info"):
    color = {
        "info": "#4f8bf9",
        "success": "#4CAF50",
        "warning": "#FFC107",
        "error": "#f44336"
    }.get(type, "#4f8bf9")
    
    toast_html = f"""
    <div class="toast" style="background-color: {color};">
        {message}
    </div>
    <script>
        setTimeout(function() {{
            document.querySelector('.toast').style.display = 'none';
        }}, 3000);
    </script>
    """
    st.markdown(toast_html, unsafe_allow_html=True)

def render_page_navigation():
    st.markdown('<div class="page-navigation">', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 4, 1])
    
    with col1:
        if st.session_state.page != 'upload':
            if st.button("← Back", key="nav_back"):
                if st.session_state.page == 'extract':
                    st.session_state.page = 'upload'
                elif st.session_state.page == 'results':
                    st.session_state.page = 'extract'
                st.rerun()
    
    with col3:
        if st.session_state.page != 'results' and st.session_state.page != 'upload':
            if st.button("Next →", key="nav_next"):
                if st.session_state.page == 'upload' and st.session_state.pdf_path:
                    st.session_state.page = 'extract'
                elif st.session_state.page == 'extract' and st.session_state.tables is not None:
                    st.session_state.page = 'results'
                st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)

def render_sidebar():
    with st.sidebar:
        st.image("https://i.imgur.com/X6yx00q.png", width=80)  # Placeholder logo
        st.title("PDF Table Extractor")
        
        st.markdown("---")
        
        # Navigation
        st.subheader("Navigation")
        
        nav_options = {
            "upload": "📄 Upload PDF",
            "extract": "🔍 Extract Tables",
            "results": "📊 View & Export Results"
        }
        
        for page_id, page_name in nav_options.items():
            button_style = "primary-button" if st.session_state.page == page_id else ""
            
            # Disable buttons that shouldn't be accessible yet
            disabled = False
            if page_id == 'extract' and not st.session_state.pdf_path:
                disabled = True
            if page_id == 'results' and st.session_state.tables is None:
                disabled = True
            
            if st.button(page_name, key=f"nav_{page_id}", disabled=disabled, help=f"Go to {page_name} page"):
                st.session_state.page = page_id
                st.rerun()
        
        st.markdown("---")
        
        # App info and settings
        st.subheader("Settings")
        
        # Dark mode toggle
        dark_mode = st.toggle("Dark Mode (Beta)", value=st.session_state.dark_mode)
        if dark_mode != st.session_state.dark_mode:
            st.session_state.dark_mode = dark_mode
            # Apply dark mode styling if needed
            if dark_mode:
                st.markdown("""
                <style>
                    body {
                        background-color: #1e1e1e;
                        color: #f0f0f0;
                    }
                    .card {
                        background-color: #2d2d2d;
                        border-color: #444;
                    }
                    h1, h2, h3 {
                        color: #f0f0f0;
                    }
                    .stDataFrame {
                        background-color: #2d2d2d;
                    }
                </style>
                """, unsafe_allow_html=True)
            st.rerun()
        
        # Session information
        if st.session_state.pdf_info:
            st.markdown("---")
            st.subheader("Current PDF")
            st.markdown(f"""
            **File:** {os.path.basename(st.session_state.pdf_path)}  
            **Pages:** {st.session_state.pdf_info['total_pages']}  
            **Size:** {st.session_state.pdf_info['file_size']:.2f} MB
            """)
        
        # Footer
        st.markdown("---")
        st.markdown("""
        <div class="footer">
            PDF Table Extractor v2.0<br>
            Powered by Camelot, PyPDF2, and Streamlit<br>
            © 2025
        </div>
        """, unsafe_allow_html=True)

# --------------------------
# Page Renderers
# --------------------------
def render_upload_page():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.title("📄 Upload Your PDF Document")
    
    st.markdown("""
    Start by uploading a PDF file containing tables that you want to extract. 
    The app will help you identify and extract data from tables in your document.
    """)
    
    col1, col2 = st.columns([3, 2])
    
    with col1:
        uploaded_file = st.file_uploader(
            "Choose a PDF file",
            type=["pdf"],
            help="Maximum file size: 200MB",
            key="pdf_uploader"
        )
        
        if uploaded_file:
            # Save file and get info
            pdf_path = save_upload_for_session(uploaded_file)
            
            # Show success with file details
            st.success(f"✅ Successfully loaded PDF with {st.session_state.total_pages} pages")
            
            # Auto-navigate to extract page
            st.session_state.page = 'extract'
            st.rerun()
    
    with col2:
        st.markdown("""
        ### Accepted File Types
        - PDF documents (*.pdf)
        
        ### Limitations
        - Maximum file size: 200MB
        - Protected/encrypted PDFs not supported
        
        ### Tips
        - Make sure your PDF contains clearly defined tables
        - For best results, use PDFs with good quality text
        """)
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Add sample PDFs section
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Or try with a sample PDF")
    
    sample_pdfs = {
        "Simple Table": "https://example.com/sample1.pdf",
        "Complex Tables": "https://example.com/sample2.pdf",
        "Financial Statement": "https://example.com/sample3.pdf"
    }
    
    col1, col2, col3 = st.columns(3)
    
    for i, (name, url) in enumerate(sample_pdfs.items()):
        col = [col1, col2, col3][i]
        with col:
            st.markdown(f"**{name}**")
            if st.button(f"Use this sample", key=f"sample_{i}"):
                st.info(f"Loading {name} sample...")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Feature showcase
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Features")
    
    features = [
        ("🔍 Smart Table Detection", "Automatically detects tables on PDF pages"),
        ("📊 Multiple Export Formats", "Export to Excel, CSV, HTML or JSON"),
        ("⚡ Batch Processing", "Extract all tables at once"),
        ("✏️ Table Editing", "Clean up data before export")
    ]
    
    feature_cols = st.columns(len(features))
    
    for i, ((icon, title), description) in enumerate(features):
        with feature_cols[i]:
            st.markdown(f"### {icon} {title}")
            st.markdown(description)
    
    st.markdown('</div>', unsafe_allow_html=True)

def render_extract_page():
    if not st.session_state.pdf_path:
        st.warning("Please upload a PDF first")
        st.session_state.page = 'upload'
        st.rerun()
    
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.title("🔍 Extract Tables from PDF")
    
    # Create tabs for extraction options and PDF preview
    tab1, tab2 = st.tabs(["Extraction Options", "PDF Preview"])
    
    with tab1:
        st.subheader("Configure Extraction Settings")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Page selection
            pages = st.text_input(
                "Pages to analyze",
                value=st.session_state.extraction_settings['pages'],
                help="Enter page numbers or ranges (e.g., 1,3-5,7)",
                key="pages_input"
            )
            st.session_state.extraction_settings['pages'] = pages
            
            # Table detection method
            flavor_options = {
                "lattice": "Lattice (tables with borders/lines)",
                "stream": "Stream (tables without clear borders)"
            }
            flavor = st.selectbox(
                "Table detection method",
                options=list(flavor_options.keys()),
                format_func=lambda x: flavor_options[x],
                index=list(flavor_options.keys()).index(st.session_state.extraction_settings['flavor']),
                help="Choose the method based on your table structure"
            )
            st.session_state.extraction_settings['flavor'] = flavor
        
        with col2:
            # Advanced options
            method_options = {
                "standard": "Standard (balanced)",
                "accurate": "Accurate (slower but more precise)",
                "fast": "Fast (quicker but may miss details)"
            }
            method = st.selectbox(
                "Extraction method",
                options=list(method_options.keys()),
                format_func=lambda x: method_options[x],
                index=list(method_options.keys()).index(st.session_state.extraction_settings['method']),
                help="Choose extraction quality vs. speed"
            )
            st.session_state.extraction_settings['method'] = method
            
            # Table filtering options
            min_size = st.slider(
                "Minimum table size (rows)",
                min_value=1,
                max_value=10,
                value=2,
                help="Ignore tables with fewer rows than this"
            )
        
        # Preview of what will be processed
        st.markdown("### Processing Summary")
        
        summary_items = [
            f"**PDF:** {os.path.basename(st.session_state.pdf_path)}",
            f"**Pages to process:** {pages}",
            f"**Detection method:** {flavor_options[flavor]}",
            f"**Extraction quality:** {method_options[method]}"
        ]
        
        for item in summary_items:
            st.markdown(item)
        
        # Extract button
        extract_col1, extract_col2 = st.columns([1, 4])
        with extract_col1:
            extract_clicked = st.button(
                "🚀 Extract Tables",
                key="extract_button",
                help="Start table extraction with current settings"
            )
        
        if extract_clicked:
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                # Update status
                status_text.text("Analyzing PDF structure...")
                progress_bar.progress(10)
                
                # Get total pages to process for progress calculation
                page_nums = []
                for page_ref in pages.split(','):
                    if '-' in page_ref:
                        start, end = map(int, page_ref.split('-'))
                        page_nums.extend(range(start, end + 1))
                    else:
                        page_nums.append(int(page_ref))
                total_to_process = len(page_nums)
                
                # Process in smaller batches for better feedback
                all_tables = []
                for i, page in enumerate(page_nums):
                    status_text.text(f"Processing page {page}...")
                    progress_value = 10 + int(85 * (i / total_to_process))
                    progress_bar.progress(progress_value)
                    
                    # Process the individual page
                    page_tables = cam.read_pdf(
                        st.session_state.pdf_path,
                        pages=str(page),
                        flavor=flavor,
                        suppress_stdout=False
                    )
                    
                    # Filter tables if needed
                    filtered_tables = [table for table in page_tables if len(table.df) >= min_size]
                    all_tables.extend(filtered_tables)
                    
                    # Small delay to show progress
                    time.sleep(0.2)
                
                # Final processing
                status_text.text("Finalizing results...")
                progress_bar.progress(95)
                
                # Store in session state
                st.session_state.tables = all_tables
                st.session_state.selected_table = 0
                
                # Add to extraction history
                extraction_record = {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "pages": pages,
                    "method": f"{flavor}/{method}",
                    "table_count": len(all_tables)
                }
                st.session_state.extraction_history.append(extraction_record)
                
                # Complete progress
                progress_bar.progress(100)
                status_text.text(f"Extraction complete! Found {len(all_tables)} tables.")
                
                # Show success message
                st.success(f"🎉 Successfully extracted {len(all_tables)} tables!")
                
                # Auto-navigate to results page if tables were found
                if len(all_tables) > 0:
                    time.sleep(1)  # Give user time to see success message
                    st.session_state.page = 'results'
                    st.rerun()
                else:
                    st.warning("No tables were found with the current settings. Try changing the detection method or page selection.")
            
            except Exception as e:
                st.error(f"❌ Extraction failed: {str(e)}")
                st.info("Tips: Check if pages exist in the document and that tables are properly formatted.")
                
                # Log error for debugging
                st.session_state.last_error = str(e)
    
    with tab2:
        # PDF preview with page controls
        st.subheader("PDF Document Preview")
        
        # Add page navigation
        total_pages = st.session_state.total_pages
        
        # Create a page selector
        preview_page = st.slider(
            "Navigate to page", 
            min_value=1, 
            max_value=total_pages,
            value=1,
            key="preview_page_slider"
        )
        
        # Generate preview for selected page only
        try:
            with open(st.session_state.pdf_path, "rb") as f:
                pdf_bytes = f.read()
            
            with st.spinner(f"Loading page {preview_page}..."):
                images = convert_from_bytes(pdf_bytes, first_page=preview_page, last_page=preview_page)
                
                if images:
                    st.image(
                        images[0],
                        caption=f"Page {preview_page} of {total_pages}",
                        use_container_width=True
                    )
                else:
                    st.error("Could not generate preview for this page")
        except Exception as e:
            st.error(f"Preview generation failed: {str(e)}")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Show extraction history if available
    if st.session_state.extraction_history:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("Extraction History")
        
        history_df = pd.DataFrame(st.session_state.extraction_history)
        st.dataframe(history_df, use_container_width=True)
        
        st.markdown('</div>', unsafe_allow_html=True)

def render_results_page():
    if st.session_state.tables is None or len(st.session_state.tables) == 0:
        st.warning("No extracted tables to display. Please extract tables first.")
        st.session_state.page = 'extract'
        st.rerun()
    
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.title("📊 View and Export Tables")
    
    # Create tabs for table viewing and export
    tab1, tab2, tab3 = st.tabs(["Table Viewer", "Export Options", "Data Visualization"])
    
    with tab1:
        st.subheader("Extracted Tables")
        
        # Table selection via thumbnails
        st.markdown("### Select a table to view:")
        
        # Split into rows of 3 thumbnails
        thumbnails_per_row = 3
        num_tables = len(st.session_state.tables)
        
        for i in range(0, num_tables, thumbnails_per_row):
            cols = st.columns(thumbnails_per_row)
            
            for j in range(thumbnails_per_row):
                table_idx = i + j
                if table_idx < num_tables:
                    with cols[j]:
                        table = st.session_state.tables[table_idx]
                        page_num = table.page
                        
                        # Create a thumbnail of the table
                        thumbnail_html = create_table_thumbnail(table.df)
                        
                        # Create a container with a border
                        border_class = "table-thumbnail-selected" if table_idx == st.session_state.selected_table else "table-thumbnail"
                        st.markdown(f'<div class="{border_class}">', unsafe_allow_html=True)
                        
                        st.markdown(f"**Table {table_idx+1}** (Page {page_num})")
                        st.markdown(thumbnail_html, unsafe_allow_html=True)
                        
                        if st.button(f"Select", key=f"select_table_{table_idx}"):
                            st.session_state.selected_table = table_idx
                            st.rerun()
                        
                        st.markdown('</div>', unsafe_allow_html=True)
        
        # Display the selected table
        st.markdown("### Table Details:")
        
        selected_idx = st.session_state.selected_table
        selected_table = st.session_state.tables[selected_idx]
    
