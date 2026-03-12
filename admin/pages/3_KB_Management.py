"""KB Management — upload form + documents table with inline actions."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import httpx
import pandas as pd
from config.settings import get_settings

settings = get_settings()
BASE = settings.api_base_url

st.set_page_config(page_title="KB Management | IntelliKnow", page_icon="📚", layout="wide")
st.title("📚 Knowledge Base Management")


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
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / 1024 ** 2:.1f} MB"


spaces = get_intent_spaces()
space_names = [s["name"] for s in spaces if s.get("is_active")]

# ── Upload ────────────────────────────────────────────────────────────────
st.subheader("Upload Document")
with st.form("upload_form"):
    col1, col2 = st.columns([2, 1])
    with col1:
        uploaded_file = st.file_uploader("Choose a PDF or DOCX file", type=["pdf", "docx", "doc"])
    with col2:
        selected_space = st.selectbox("Intent Space", space_names if space_names else ["general"])
    submit_upload = st.form_submit_button("Upload & Index")

if submit_upload and uploaded_file:
    with st.spinner("Uploading and indexing..."):
        try:
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
            data = {"intent_space": selected_space}
            r = httpx.post(f"{BASE}/api/v1/documents/upload", files=files, data=data, timeout=120)
            r.raise_for_status()
            result = r.json()
            st.success(
                f"✅ Uploaded '{result['original_name']}' → {result['chunk_count']} chunks indexed in '{result['intent_space']}'"
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

space_filter = None if filter_space == "All" else filter_space
search_filter = search_query.strip() if search_query.strip() else None

docs = get_documents(space_filter, search_filter)

if not docs:
    st.info("No documents found. Use the form above to upload PDF or DOCX files.")
else:
    # Summary table (read-only)
    df = pd.DataFrame(docs)
    df["size"] = df["file_size_bytes"].apply(fmt_size)
    display_cols = ["id", "original_name", "intent_space_name", "file_type", "size", "chunk_count", "status", "uploaded_at"]
    display_cols = [c for c in display_cols if c in df.columns or c == "size"]
    st.dataframe(df[display_cols], use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── Inline actions per document ───────────────────────────────────────
    for doc in docs:
        doc_id = doc["id"]
        label = f"**{doc['original_name']}**  `{doc['intent_space_name']}` · {fmt_size(doc['file_size_bytes'])} · {doc['chunk_count']} chunks · _{doc['status']}_"

        with st.expander(label):
            col_view, col_reparse, col_delete = st.columns(3)

            with col_view:
                if st.button("🔍 View Chunks", key=f"view_{doc_id}", use_container_width=True):
                    try:
                        r = httpx.get(f"{BASE}/api/v1/documents/{doc_id}/chunks", timeout=15)
                        r.raise_for_status()
                        chunks = r.json()
                        st.markdown(f"**{len(chunks)} chunks indexed**")
                        for c in chunks:
                            pg = f" — page {c['page_number']}" if c.get("page_number") is not None else ""
                            st.markdown(f"*Chunk {c['chunk_index']}{pg}*")
                            st.text(c["chunk_text"][:500] + ("..." if len(c["chunk_text"]) > 500 else ""))
                            st.divider()
                    except Exception as e:
                        st.error(f"Failed to load chunks: {e}")

            with col_reparse:
                if st.button("🔄 Re-parse", key=f"reparse_{doc_id}", use_container_width=True):
                    with st.spinner("Re-parsing..."):
                        try:
                            r = httpx.post(f"{BASE}/api/v1/documents/{doc_id}/reparse", timeout=120)
                            r.raise_for_status()
                            result = r.json()
                            st.success(f"✅ {result['chunk_count']} chunks re-indexed")
                            st.rerun()
                        except httpx.HTTPStatusError as e:
                            st.error(f"Re-parse failed: {e.response.text}")
                        except Exception as e:
                            st.error(f"Re-parse failed: {e}")

            with col_delete:
                if st.button("🗑 Delete", key=f"delete_{doc_id}", type="secondary", use_container_width=True):
                    try:
                        r = httpx.delete(f"{BASE}/api/v1/documents/{doc_id}", timeout=30)
                        r.raise_for_status()
                        st.success(r.json()["message"])
                        st.rerun()
                    except Exception as e:
                        st.error(f"Delete failed: {e}")
