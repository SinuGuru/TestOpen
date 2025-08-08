import os
import io
import zipfile
import streamlit as st
from datetime import datetime
from streamlit_ace import st_ace

# --- Helper Functions ---
def list_files(directory):
    """List files in a directory (non-recursive)."""
    return [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]

def get_file_info(filepath):
    size = os.path.getsize(filepath)
    mtime = os.path.getmtime(filepath)
    return size, datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

def save_file(filepath, content):
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

def read_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()

def zip_directory(directory):
    mem_zip = io.BytesIO()
    with zipfile.ZipFile(mem_zip, "w") as zf:
        for filename in list_files(directory):
            zf.write(os.path.join(directory, filename), arcname=filename)
    mem_zip.seek(0)
    return mem_zip

# --- Streamlit App ---
st.set_page_config(page_title="Edit Files", layout="wide")
st.title("📝 Edit Files")
st.write("Browse, edit, and manage your files. Use the AI assistant by entering instructions to modify your code.")

# --- Sidebar: File Browser ---
st.sidebar.header("Files")
WORKSPACE = "workspace"
os.makedirs(WORKSPACE, exist_ok=True)

# Upload
uploaded = st.sidebar.file_uploader("Upload New File", type=None, accept_multiple_files=True)
if uploaded:
    for up in uploaded:
        with open(os.path.join(WORKSPACE, up.name), "wb") as f:
            f.write(up.read())
    st.sidebar.success("File(s) uploaded.")

# Download all
if st.sidebar.button("Download All as Zip"):
    mem_zip = zip_directory(WORKSPACE)
    st.sidebar.download_button("Download workspace.zip", mem_zip, "workspace.zip")

# File list
files = list_files(WORKSPACE)
if not files:
    st.sidebar.info("No files uploaded yet.")

# --- Main Area: Two Columns ---
col1, col2 = st.columns([1, 2])

# --- Left: File List & Actions ---
with col1:
    st.subheader("Files")
    selected_file = st.radio("Select a file to edit:", files, key="file_select") if files else None

    if selected_file:
        # Actions: Download, Rename, Delete
        file_path = os.path.join(WORKSPACE, selected_file)
        with st.expander("File Actions"):
            col_dl, col_rename, col_delete = st.columns(3)
            with col_dl:
                with open(file_path, "rb") as f:
                    st.download_button("Download", f, file_name=selected_file)
            with col_rename:
                new_name = st.text_input("Rename file", value=selected_file, key="rename_input")
                if st.button("Rename", key="rename_btn") and new_name and new_name != selected_file:
                    os.rename(file_path, os.path.join(WORKSPACE, new_name))
                    st.experimental_rerun()
            with col_delete:
                if st.button("Delete", key="delete_btn"):
                    os.remove(file_path)
                    st.experimental_rerun()

# --- Right: Editor, Instructions, Info ---
with col2:
    if selected_file:
        file_path = os.path.join(WORKSPACE, selected_file)
        file_content = read_file(file_path)
        st.subheader(f"Editing: {selected_file}")

        # Editable file name
        editable_name = st.text_input("File Name", value=selected_file, key="edit_name")
        if editable_name != selected_file:
            if st.button("Rename File", key="edit_rename_btn"):
                os.rename(file_path, os.path.join(WORKSPACE, editable_name))
                st.success("File renamed.")
                st.experimental_rerun()

        # Code editor with syntax highlighting
        code = st_ace(value=file_content, language="python", theme="monokai", key="ace_editor", height=400)

        # AI instruction input
        st.markdown("**AI Editing Instruction**")
        instruction = st.text_area("Describe how you want the AI to edit this file (e.g., 'Add docstrings', 'Refactor for clarity').", key="ai_instruction")

        # Apply instruction (AI integration placeholder)
        if st.button("Apply Instruction"):
            if not instruction.strip():
                st.warning("Please enter an instruction for the AI.")
            else:
                # --- PLACEHOLDER: Integrate your AI backend here ---
                # For now, just echo the instruction
                st.info(f"AI would process: '{instruction}' (integration needed)")
                # After AI returns new code, update `code` variable

        # Save/Cancel
        col_save, col_cancel = st.columns(2)
        with col_save:
            if st.button("Save Changes"):
                save_file(file_path, code)
                st.success("File saved.")
        with col_cancel:
            if st.button("Cancel Changes"):
                st.experimental_rerun()

        # File info
        size, mtime = get_file_info(file_path)
        st.caption(f"**Size:** {size} bytes | **Last Modified:** {mtime}")

# --- Footer/Status Bar ---
st.markdown("---")
st.info("💡 Tip: Use the instruction box to tell the AI how to edit your code. Remember to save your changes!")
