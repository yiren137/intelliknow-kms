"""KB Management — upload form + documents table with inline actions."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import httpx
from config.settings import get_settings

settings = get_settings()
BASE = settings.api_base_url

st.set_page_config(page_title="KB Management | IntelliKnow", page_icon="📚", layout="wide")
st.title("📚 Knowledge Base Management")

# ── Column proportions for the document table ─────────────────────────────
_COLS = [3.2, 1.4, 0.7, 0.8, 0.7, 0.9, 0.55, 0.65, 0.55]
_HEADERS = ["Document", "Space", "Type", "Size", "Chunks", "Status", "View", "Update", "Delete"]

# ── Session state ─────────────────────────────────────────────────────────
if "action_message" not in st.session_state:
    st.session_state.action_message = None   # (level, text) shown after a rerun


# ── Helpers ───────────────────────────────────────────────────────────────

def get_intent_spaces():
    try:
        r = httpx.get(f"{BASE}/api/v1/intent-spaces", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


def get_documents(intent_space=None, search=None):
    try:
        params = {}
        if intent_space:
            params["intent_space"] = intent_space
        if search:
            params["search"] = search
        r = httpx.get(f"{BASE}/api/v1/documents", params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Error loading documents: {e}")
        return []


def fmt_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / 1024 ** 2:.1f} MB"


def status_badge(status: str) -> str:
    colours = {"indexed": "🟢", "processing": "🟡", "error": "🔴", "pending": "⚪"}
    return f"{colours.get(status, '⚪')} {status}"


# ── Dialogs ───────────────────────────────────────────────────────────────
# Dialogs are called directly inside button handlers — this ensures they are
# tied to a button click (which resets each rerun) rather than persistent
# session state, preventing them from re-opening after tab navigation.

@st.dialog("📄 Document Chunks", width="large")
def view_chunks_dialog(doc: dict):
    st.markdown(f"**{doc['original_name']}** · `{doc['intent_space_name']}` · {fmt_size(doc['file_size_bytes'])}")
    st.divider()
    try:
        r = httpx.get(f"{BASE}/api/v1/documents/{doc['id']}/chunks", timeout=15)
        r.raise_for_status()
        chunks = r.json()
        st.caption(f"{len(chunks)} chunks indexed")
        for c in chunks:
            pg = f" — page {c['page_number']}" if c.get("page_number") is not None else ""
            with st.expander(f"Chunk {c['chunk_index']}{pg}", expanded=False):
                st.text(c["chunk_text"])
    except Exception as e:
        st.error(f"Failed to load chunks: {e}")
    if st.button("Close", use_container_width=True):
        st.rerun()


@st.dialog("⚠️ Confirm Delete")
def delete_confirm_dialog(doc: dict):
    st.warning(
        f"Are you sure you want to permanently delete **{doc['original_name']}**?\n\n"
        f"This will remove the document and all **{doc['chunk_count']} indexed chunks** "
        f"from the `{doc['intent_space_name']}` knowledge base."
    )
    col_cancel, col_confirm = st.columns(2)
    with col_cancel:
        if st.button("Cancel", use_container_width=True):
            st.rerun()
    with col_confirm:
        if st.button("Yes, Delete", type="primary", use_container_width=True):
            try:
                r = httpx.delete(f"{BASE}/api/v1/documents/{doc['id']}", timeout=30)
                r.raise_for_status()
                st.session_state.action_message = ("success", f"✅ '{doc['original_name']}' deleted successfully.")
            except Exception as e:
                st.error(f"Delete failed: {e}")
                return
            st.rerun()


@st.dialog("🔄 Replace Document")
def update_document_dialog(doc: dict):
    st.markdown(
        f"**Current file:** {doc['original_name']}  \n"
        f"Space: `{doc['intent_space_name']}` · {fmt_size(doc['file_size_bytes'])} · "
        f"{doc['chunk_count']} chunks"
    )
    st.divider()
    st.caption(
        "Upload a new file to replace the existing document. "
        "The old file and all its chunks will be removed and re-indexed with the new file."
    )
    new_file = st.file_uploader(
        "Choose a replacement PDF or DOCX file",
        type=["pdf", "docx", "doc"],
        key="replace_file_uploader",
    )
    col_cancel, col_confirm = st.columns(2)
    with col_cancel:
        if st.button("Cancel", use_container_width=True):
            st.rerun()
    with col_confirm:
        if st.button("Replace & Re-index", type="primary", disabled=new_file is None, use_container_width=True):
            with st.spinner("Replacing and re-indexing…"):
                try:
                    files = {"file": (new_file.name, new_file.getvalue(), new_file.type)}
                    r = httpx.post(
                        f"{BASE}/api/v1/documents/{doc['id']}/replace",
                        files=files,
                        timeout=120,
                    )
                    r.raise_for_status()
                    result = r.json()
                    st.session_state.action_message = (
                        "success",
                        f"✅ '{result['original_name']}' replaced — {result['chunk_count']} chunks re-indexed.",
                    )
                except httpx.HTTPStatusError as e:
                    st.error(f"Replace failed: {e.response.text}")
                    return
                except Exception as e:
                    st.error(f"Replace failed: {e}")
                    return
            st.rerun()


# ── Post-action message ───────────────────────────────────────────────────
if st.session_state.action_message:
    level, text = st.session_state.action_message
    st.session_state.action_message = None
    if level == "success":
        st.success(text)
    else:
        st.error(text)

# ── Upload form ───────────────────────────────────────────────────────────
spaces = get_intent_spaces()
space_names = [s["name"] for s in spaces if s.get("is_active")]

st.subheader("Upload Document")
with st.form("upload_form"):
    col1, col2 = st.columns([2, 1])
    with col1:
        uploaded_file = st.file_uploader("Choose a PDF or DOCX file", type=["pdf", "docx", "doc"])
    with col2:
        selected_space = st.selectbox("Intent Space", space_names if space_names else ["general"])
    submit_upload = st.form_submit_button("Upload & Index")

if submit_upload and uploaded_file:
    with st.spinner("Uploading and indexing…"):
        try:
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
            r = httpx.post(
                f"{BASE}/api/v1/documents/upload",
                files=files,
                data={"intent_space": selected_space},
                timeout=120,
            )
            r.raise_for_status()
            result = r.json()
            st.success(
                f"✅ Uploaded '{result['original_name']}' → {result['chunk_count']} chunks indexed "
                f"in '{result['intent_space']}'"
            )
        except httpx.HTTPStatusError as e:
            st.error(f"Upload failed: {e.response.text}")
        except Exception as e:
            st.error(f"Upload failed: {e}")

st.markdown("---")

# ── Search & Filter ───────────────────────────────────────────────────────
st.subheader("Indexed Documents")

col1, col2 = st.columns([2, 1])
with col1:
    search_query = st.text_input("🔍 Search by document name", placeholder="e.g. handbook", key="search")
with col2:
    filter_space = st.selectbox("Filter by intent space", ["All"] + space_names, key="filter")

docs = get_documents(
    intent_space=None if filter_space == "All" else filter_space,
    search=search_query.strip() or None,
)

if not docs:
    st.info("No documents found. Use the form above to upload PDF or DOCX files.")
else:
    # ── Table header ──────────────────────────────────────────────────
    header_cols = st.columns(_COLS)
    for col, label in zip(header_cols, _HEADERS):
        col.markdown(f"**{label}**")
    st.divider()

    # ── Document rows ─────────────────────────────────────────────────
    for doc in docs:
        doc_id = doc["id"]
        row = st.columns(_COLS)

        row[0].markdown(f"**{doc['original_name']}**", help=doc["original_name"])
        row[1].markdown(f"`{doc['intent_space_name']}`")
        row[2].markdown(doc.get("file_type", "—").upper())
        row[3].markdown(fmt_size(doc.get("file_size_bytes", 0)))
        row[4].markdown(str(doc.get("chunk_count", 0)))
        row[5].markdown(status_badge(doc.get("status", "unknown")))

        # Buttons call dialogs directly — no session state needed for dialog
        # triggering, so closing via the X button leaves no stale state.
        with row[6]:
            if st.button("👁", key=f"view_{doc_id}", help="View chunks", use_container_width=True):
                view_chunks_dialog(doc)

        with row[7]:
            if st.button("↑", key=f"update_{doc_id}", help="Replace document", use_container_width=True):
                update_document_dialog(doc)

        with row[8]:
            if st.button("🗑", key=f"delete_{doc_id}", help="Delete document", use_container_width=True):
                delete_confirm_dialog(doc)

        st.divider()
