
import os
import streamlit as st
from openai import OpenAI
import zipfile
import io

# ---------- Config ----------
st.set_page_config(page_title="OpenAI ChatBot & File Editor", page_icon="💬", layout="wide")

# ---- Configuration ----
DEFAULT_MODEL = "gpt-4.1"
MODEL_OPTIONS = [
    "gpt-4.1-mini",
    "gpt-4.1",
    "gpt-4o",
    "gpt-4o-mini",
    "o4-mini",
]

# Sidebar: API key + model selection
st.sidebar.header("OpenAI settings")
api_key = st.sidebar.text_input("OPENAI_API_KEY", type="password", placeholder="sk-...", help="Stored only in this session")
model = st.sidebar.selectbox("Model", MODEL_OPTIONS, index=MODEL_OPTIONS.index(DEFAULT_MODEL))
custom_model = st.sidebar.text_input("Custom model (optional)", placeholder="Override model name")
if custom_model.strip():
    model = custom_model.strip()

st.sidebar.caption("Note: There is no public model named gpt-5 at this time. Pick one above and later replace with the new model name when available.")

# Initialize OpenAI client lazily when key is present
client = None
if api_key:
    os.environ["OPENAI_API_KEY"] = api_key
    client = OpenAI()

# ---------- Helpers ----------
def need_key():
    st.warning("Enter your OPENAI_API_KEY in the sidebar to use the app.")
    return

def ai_chat(messages):
    # messages: list of {"role": "system"|"user"|"assistant", "content": str}
    if not client:
        need_key()
        return ""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        st.error(f"OpenAI error: {e}")
        return ""

def edit_file_with_instructions(file_text, instructions):
    if not client:
        need_key()
        return ""

    if not file_text:
        st.error("No file content to edit.")
        return ""
    max_chars = 120000  # adjust if your model/context allows more
    if len(file_text) > max_chars:
        st.error(f"File is too large ({len(file_text):,} chars). Please upload a smaller file or split it.")
        return ""

    system_prompt = (
        "You are an expert editor. Given file content and user instructions, produce ONLY the fully edited file. "
        "Preserve the file's format and structure. Do not add explanations or extra text."
    )
    user_prompt = (
        f"{instructions.strip()}\n\n"
        "File content between <FILE> and </FILE>:\n"
        "<FILE>\n"
        f"{file_text}\n"
        "</FILE>\n"
        "Return only the edited file content."
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        st.error(f"OpenAI error: {e}")
        return ""

def edit_zip_with_instructions(zip_bytes, instructions):
    # Returns: dict of {filename: edited_content}
    edited_files = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            if zf.getinfo(name).is_dir():
                continue
            try:
                raw = zf.read(name)
                try:
                    text = raw.decode("utf-8", errors="replace")
                except Exception:
                    continue
                edited = edit_file_with_instructions(text, instructions)
                if edited:
                    edited_files[name] = edited
            except Exception as e:
                st.warning(f"Could not process {name}: {e}")
    return edited_files

def make_zip_from_dict(file_dict):
    # file_dict: {filename: content(str)}
    mem_zip = io.BytesIO()
    with zipfile.ZipFile(mem_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, content in file_dict.items():
            zf.writestr(fname, content)
    mem_zip.seek(0)
    return mem_zip

# ---------- UI ----------
st.title("OpenAI ChatBot + File Editor")

tab_chat, tab_edit = st.tabs(["Chatbot", "Edit file(s)"])

# ----- Chatbot tab -----
with tab_chat:
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {"role": "system", "content": "You are a helpful chatbot assistant."}
        ]
    # render history (skip system message)
    for msg in st.session_state.chat_history:
        if msg["role"] == "system":
            continue
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    user_msg = st.chat_input("Type your message")
    if user_msg:
        st.session_state.chat_history.append({"role": "user", "content": user_msg})
        with st.chat_message("user"):
            st.write(user_msg)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                reply = ai_chat(st.session_state.chat_history)
                st.write(reply)
        if reply:
            st.session_state.chat_history.append({"role": "assistant", "content": reply})

    col1, _ = st.columns(2)
    with col1:
        if st.button("Reset chatbot"):
            st.session_state.chat_history = [{"role": "system", "content": "You are a helpful chatbot assistant."}]
            st.rerun()

# ----- Edit file tab -----
with tab_edit:
    st.subheader("Upload one or more text files, or a zip archive, to edit")
    uploaded_files = st.file_uploader(
        "Supported types: txt, md, py, json, csv, yaml, yml, zip",
        type=["txt", "md", "py", "json", "csv", "yaml", "yml", "zip"],
        accept_multiple_files=True,
        key="multi_file_upload",
    )

    # Session state for multi-file support
    if "file_contents" not in st.session_state:
        st.session_state.file_contents = {}  # {filename: content}
    if "file_names" not in st.session_state:
        st.session_state.file_names = []
    if "is_zip" not in st.session_state:
        st.session_state.is_zip = False
    if "zip_file_list" not in st.session_state:
        st.session_state.zip_file_list = []
    if "zip_preview" not in st.session_state:
        st.session_state.zip_preview = {}
    if "selected_file" not in st.session_state:
        st.session_state.selected_file = None
    if "edited_files" not in st.session_state:
        st.session_state.edited_files = {}  # {filename: edited_content}
    if "edited_zip" not in st.session_state:
        st.session_state.edited_zip = {}
    if "edited_content" not in st.session_state:
        st.session_state.edited_content = ""
    if "zip_bytes" not in st.session_state:
        st.session_state.zip_bytes = None

    # Handle uploads
    if uploaded_files:
        st.session_state.file_contents = {}
        st.session_state.file_names = []
        st.session_state.is_zip = False
        st.session_state.zip_file_list = []
        st.session_state.zip_preview = {}
        st.session_state.selected_file = None
        st.session_state.edited_files = {}
        st.session_state.edited_zip = {}
        st.session_state.edited_content = ""
        st.session_state.zip_bytes = None

        # If only one file and it's a zip, treat as zip
        if len(uploaded_files) == 1 and uploaded_files[0].name.lower().endswith(".zip"):
            uploaded = uploaded_files[0]
            st.session_state.is_zip = True
            try:
                uploaded.seek(0)
                zip_bytes = uploaded.read()
                st.session_state.zip_bytes = zip_bytes
                with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                    file_list = [name for name in zf.namelist() if not zf.getinfo(name).is_dir()]
                    st.session_state.zip_file_list = file_list
                    preview = {}
                    for name in file_list[:10]:  # preview up to 10 files
                        try:
                            raw = zf.read(name)
                            text = raw.decode("utf-8", errors="replace")
                            preview[name] = text[:500]
                        except Exception:
                            preview[name] = "[Could not decode]"
                    st.session_state.zip_preview = preview
                st.session_state.file_names = file_list
                st.success(f"Loaded ZIP: {uploaded.name} ({len(file_list)} files)")
            except Exception as e:
                st.error(f"Failed to read zip file: {e}")
                st.session_state.zip_file_list = []
                st.session_state.zip_preview = {}
                st.session_state.file_names = []
        else:
            # Multiple files (or single non-zip)
            for uploaded in uploaded_files:
                try:
                    raw = uploaded.read()
                    text = raw.decode("utf-8", errors="replace")
                    st.session_state.file_contents[uploaded.name] = text
                    st.session_state.file_names.append(uploaded.name)
                except Exception as e:
                    st.error(f"Failed to read file {uploaded.name}: {e}")
            if st.session_state.file_names:
                st.success(f"Loaded {len(st.session_state.file_names)} file(s): {', '.join(st.session_state.file_names)}")
            st.session_state.is_zip = False
            st.session_state.selected_file = st.session_state.file_names[0] if st.session_state.file_names else None

    # Move instructions and chat input to the top of the tab
    col_edit, col_chat = st.columns([2, 1])
    with col_edit:
        instructions = st.text_area(
            "Editing instructions",
            value="Improve clarity and fix grammar. Keep original meaning. Preserve formatting and code blocks.",
            height=120,
            key="edit_instructions",
        )
    with col_chat:
        st.markdown("**Chatbot: Ask about your file(s) or instructions**")
        if "edit_chat_history" not in st.session_state:
            st.session_state.edit_chat_history = [
                {"role": "system", "content": "You are a helpful chatbot for file editing and code tasks."}
            ]
        for msg in st.session_state.edit_chat_history:
            if msg["role"] == "system":
                continue
            with st.chat_message(msg["role"], avatar="💬"):
                st.write(msg["content"])
        edit_user_msg = st.chat_input("Ask chatbot about your file(s) or instructions", key="edit_chat_input")
        if edit_user_msg:
            st.session_state.edit_chat_history.append({"role": "user", "content": edit_user_msg})
            with st.chat_message("user", avatar="💬"):
                st.write(edit_user_msg)
            with st.chat_message("assistant", avatar="💬"):
                with st.spinner("Thinking..."):
                    # Add file content and instructions to the context for the AI
                    context = ""
                    if st.session_state.is_zip and st.session_state.zip_file_list:
                        context = f"ZIP file with files: {', '.join(st.session_state.zip_file_list[:10])}..."
                    elif st.session_state.file_names:
                        context = f"Project files: {', '.join(st.session_state.file_names[:10])}..."
                        if st.session_state.selected_file:
                            context += f"\nPreview of {st.session_state.selected_file}:\n{st.session_state.file_contents.get(st.session_state.selected_file, '')[:500]}"
                    chat_messages = st.session_state.edit_chat_history.copy()
                    chat_messages.insert(1, {"role": "user", "content": f"Current file(s) preview:\n{context}\n\nCurrent instructions:\n{instructions}"})
                    reply = ai_chat(chat_messages)
                    st.write(reply)
            if reply:
                st.session_state.edit_chat_history.append({"role": "assistant", "content": reply})
        if st.button("Reset chatbot (edit)", key="reset_edit_chat"):
            st.session_state.edit_chat_history = [
                {"role": "system", "content": "You are a helpful chatbot for file editing and code tasks."}
            ]
            st.rerun()

    # File/project browser and preview
    if st.session_state.is_zip and st.session_state.zip_file_list:
        st.markdown("**ZIP file preview (first 10 files):**")
        for fname, preview in st.session_state.zip_preview.items():
            st.markdown(f"**{fname}**")
            st.code(preview, language="")
    elif st.session_state.file_names:
        st.markdown("**Project files:**")
        selected = st.selectbox(
            "Select a file to preview and edit",
            st.session_state.file_names,
            index=st.session_state.file_names.index(st.session_state.selected_file) if st.session_state.selected_file in st.session_state.file_names else 0,
            key="file_select_box",
        )
        st.session_state.selected_file = selected
        st.text_area(
            "Original file content (read-only preview)",
            value=st.session_state.file_contents.get(selected, ""),
            height=240,
            disabled=True,
            key="original_file_preview",
        )
    else:
        st.info("Upload files to get started.")

    # Enable/disable edit button
    if st.session_state.is_zip and st.session_state.zip_file_list:
        run_edit_disabled = False if st.session_state.zip_file_list else True
    elif st.session_state.file_names:
        run_edit_disabled = False
    else:
        run_edit_disabled = True

    # Edit button and logic
    if st.button("Run edit", type="primary", disabled=run_edit_disabled):
        if st.session_state.is_zip and st.session_state.zip_file_list:
            with st.spinner("Editing all files in ZIP with OpenAI..."):
                zip_bytes = st.session_state.zip_bytes
                edited_files = edit_zip_with_instructions(zip_bytes, instructions)
                if edited_files:
                    st.session_state.edited_zip = edited_files
                    st.session_state.edited_files = {}
                    st.session_state.edited_content = ""
                    st.success(f"Edited {len(edited_files)} files in ZIP.")
                else:
                    st.session_state.edited_zip = {}
                    st.session_state.edited_files = {}
                    st.session_state.edited_content = ""
        elif st.session_state.file_names:
            st.session_state.edited_files = {}
            with st.spinner("Editing all files with OpenAI..."):
                for fname in st.session_state.file_names:
                    content = st.session_state.file_contents.get(fname, "")
                    if content.strip():
                        edited = edit_file_with_instructions(content, instructions)
                        if edited:
                            st.session_state.edited_files[fname] = edited
                if st.session_state.edited_files:
                    st.session_state.edited_content = ""
                    st.session_state.edited_zip = {}
                    st.success(f"Edited {len(st.session_state.edited_files)} file(s).")
                else:
                    st.session_state.edited_content = ""
                    st.session_state.edited_zip = {}
        else:
            st.warning("No file(s) to edit.")

    edited_files = st.session_state.get("edited_files", {})
    edited_zip = st.session_state.get("edited_zip", {})
    edited_content = st.session_state.get("edited_content", "")

    # Download and preview for edited files
    if st.session_state.is_zip and edited_zip:
        st.markdown("**Edited files in ZIP:**")
        for fname, content in list(edited_zip.items())[:5]:
            st.markdown(f"**{fname}**")
            st.code(content[:500], language="")
        mem_zip = make_zip_from_dict(edited_zip)
        st.download_button(
            "Download edited ZIP",
            data=mem_zip,
            file_name=f"edited_project.zip",
            mime="application/zip",
        )
    elif edited_files:
        st.markdown("**Edited project files:**")
        selected_edited = st.selectbox(
            "Select an edited file to preview and download",
            list(edited_files.keys()),
            key="edited_file_select_box",
        )
        st.text_area(
            "Edited file content",
            value=edited_files[selected_edited],
            height=300,
            key="edited_file_preview",
        )
        st.download_button(
            "Download edited file",
            data=edited_files[selected_edited].encode("utf-8"),
            file_name=f"edited_{selected_edited}",
            mime="text/plain",
            key="download_single_edited_file",
        )
        mem_zip = make_zip_from_dict(edited_files)
        st.download_button(
            "Download all edited files as ZIP",
            data=mem_zip,
            file_name="edited_project.zip",
            mime="application/zip",
            key="download_all_edited_files_zip",
        )
    elif edited_content:
        st.text_area(
            "Edited file content",
            value=edited_content,
            height=300,
        )
        if edited_content:
            st.download_button(
                "Download edited file",
                data=edited_content.encode("utf-8"),
                file_name="edited_file.txt",
                mime="text/plain",
            )
