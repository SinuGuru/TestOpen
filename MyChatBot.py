
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

tab_chat, tab_edit = st.tabs(["Chatbot", "Edit file"])

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
    st.subheader("Upload a text file or zip archive to edit")
    uploaded = st.file_uploader(
        "Supported types: txt, md, py, json, csv, yaml, yml, zip",
        type=["txt", "md", "py", "json", "csv", "yaml", "yml", "zip"],
        accept_multiple_files=False,
    )

    if "file_content" not in st.session_state:
        st.session_state.file_content = ""
    if "file_name" not in st.session_state:
        st.session_state.file_name = "edited.txt"
    if "is_zip" not in st.session_state:
        st.session_state.is_zip = False
    if "zip_file_list" not in st.session_state:
        st.session_state.zip_file_list = []
    if "zip_preview" not in st.session_state:
        st.session_state.zip_preview = {}

    if uploaded is not None:
        st.session_state.is_zip = uploaded.name.lower().endswith(".zip")
        if st.session_state.is_zip:
            try:
                uploaded.seek(0)
                zip_bytes = uploaded.read()
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
                st.session_state.file_content = ""
                st.session_state.file_name = uploaded.name
                st.success(f"Loaded ZIP: {uploaded.name} ({len(file_list)} files)")
            except Exception as e:
                st.error(f"Failed to read zip file: {e}")
                st.session_state.zip_file_list = []
                st.session_state.zip_preview = {}
        else:
            try:
                raw = uploaded.read()
                text = raw.decode("utf-8", errors="replace")
                st.session_state.file_content = text
                st.session_state.file_name = uploaded.name
                st.success(f"Loaded {uploaded.name} ({len(text):,} chars)")
            except Exception as e:
                st.error(f"Failed to read file: {e}")

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
        st.markdown("**Chatbot: Ask about your file or instructions**")
        if "edit_chat_history" not in st.session_state:
            st.session_state.edit_chat_history = [
                {"role": "system", "content": "You are a helpful chatbot for file editing and code tasks."}
            ]
        for msg in st.session_state.edit_chat_history:
            if msg["role"] == "system":
                continue
            with st.chat_message(msg["role"], avatar="💬"):
                st.write(msg["content"])
        edit_user_msg = st.chat_input("Ask chatbot about your file or instructions", key="edit_chat_input")
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
                    else:
                        context = st.session_state.file_content[:1000]
                    chat_messages = st.session_state.edit_chat_history.copy()
                    chat_messages.insert(1, {"role": "user", "content": f"Current file preview:\n{context}\n\nCurrent instructions:\n{instructions}"})
                    reply = ai_chat(chat_messages)
                    st.write(reply)
            if reply:
                st.session_state.edit_chat_history.append({"role": "assistant", "content": reply})
        if st.button("Reset chatbot (edit)", key="reset_edit_chat"):
            st.session_state.edit_chat_history = [
                {"role": "system", "content": "You are a helpful chatbot for file editing and code tasks."}
            ]
            st.rerun()

    if st.session_state.is_zip and st.session_state.zip_file_list:
        st.markdown("**ZIP file preview (first 10 files):**")
        for fname, preview in st.session_state.zip_preview.items():
            st.markdown(f"**{fname}**")
            st.code(preview, language="")
    else:
        st.text_area(
            "Original file content (read-only preview)",
            value=st.session_state.file_content,
            height=240,
            disabled=True,
        )

    if st.session_state.is_zip and st.session_state.zip_file_list:
        run_edit_disabled = False if st.session_state.zip_file_list else True
    else:
        run_edit_disabled = not bool(st.session_state.file_content.strip())

    if st.button("Run edit", type="primary", disabled=run_edit_disabled):
        if st.session_state.is_zip and st.session_state.zip_file_list:
            with st.spinner("Editing all files in ZIP with OpenAI..."):
                uploaded.seek(0)
                zip_bytes = uploaded.read()
                edited_files = edit_zip_with_instructions(zip_bytes, instructions)
                if edited_files:
                    st.session_state.edited_zip = edited_files
                    st.session_state.edited_content = ""
                    st.success(f"Edited {len(edited_files)} files in ZIP.")
                else:
                    st.session_state.edited_zip = {}
                    st.session_state.edited_content = ""
        else:
            with st.spinner("Editing with OpenAI..."):
                edited = edit_file_with_instructions(st.session_state.file_content, instructions)
                if edited:
                    st.session_state.edited_content = edited
                    st.session_state.edited_zip = {}
                    st.success("Edit complete.")

    edited_text = st.session_state.get("edited_content", "")
    edited_zip = st.session_state.get("edited_zip", {})

    if st.session_state.is_zip and edited_zip:
        st.markdown("**Edited files in ZIP:**")
        for fname, content in list(edited_zip.items())[:5]:
            st.markdown(f"**{fname}**")
            st.code(content[:500], language="")
        mem_zip = make_zip_from_dict(edited_zip)
        st.download_button(
            "Download edited ZIP",
            data=mem_zip,
            file_name=f"edited_{st.session_state.file_name}",
            mime="application/zip",
        )
    else:
        st.text_area(
            "Edited file content",
            value=edited_text,
            height=300,
        )
        if edited_text:
            st.download_button(
                "Download edited file",
                data=edited_text.encode("utf-8"),
                file_name=f"edited_{st.session_state.file_name}",
                mime="text/plain",
            )
