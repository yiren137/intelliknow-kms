"""Intent Configuration — CRUD for intent spaces with keywords and confidence threshold."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import httpx
from config.settings import get_settings

settings = get_settings()
BASE = settings.api_base_url

st.set_page_config(page_title="Intent Configuration | IntelliKnow", page_icon="🗂", layout="wide")
st.title("🗂 Intent Space Configuration")


def get_spaces():
    try:
        r = httpx.get(f"{BASE}/api/v1/intent-spaces", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Error: {e}")
        return []


spaces = get_spaces()

if spaces:
    st.subheader("Current Intent Spaces")
    for space in spaces:
        accuracy = space.get("accuracy_rate")
        accuracy_str = f"{accuracy * 100:.1f}%" if accuracy is not None else "N/A"
        with st.expander(
            f"{'✅' if space['is_active'] else '⚪'} {space['display_name']} (`{space['name']}`)"
            f" — {space.get('document_count', 0)} docs | accuracy: {accuracy_str}"
        ):
            with st.form(f"edit_{space['id']}"):
                new_display = st.text_input("Display Name", value=space["display_name"])
                new_desc = st.text_area("Description", value=space.get("description", ""))
                new_keywords = st.text_input(
                    "Classification Keywords",
                    value=space.get("keywords", ""),
                    help="Comma-separated keywords that help the AI classify queries into this space (e.g. 'leave, PTO, salary, onboarding')",
                )
                new_threshold = st.slider(
                    "Confidence Threshold",
                    min_value=0.0,
                    max_value=1.0,
                    value=float(space.get("confidence_threshold", 0.7)),
                    step=0.05,
                    help="Queries classified below this confidence will fall back to 'General'",
                )
                new_active = st.checkbox("Active", value=bool(space["is_active"]))

                col1, col2 = st.columns(2)
                with col1:
                    if st.form_submit_button("Save Changes"):
                        try:
                            r = httpx.put(
                                f"{BASE}/api/v1/intent-spaces/{space['id']}",
                                json={
                                    "display_name": new_display,
                                    "description": new_desc,
                                    "keywords": new_keywords,
                                    "confidence_threshold": new_threshold,
                                    "is_active": new_active,
                                },
                                timeout=10,
                            )
                            r.raise_for_status()
                            st.success("Updated!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Update failed: {e}")
                with col2:
                    if space["name"] != "general":
                        if st.form_submit_button("🗑 Delete", type="secondary"):
                            try:
                                r = httpx.delete(
                                    f"{BASE}/api/v1/intent-spaces/{space['id']}", timeout=10
                                )
                                r.raise_for_status()
                                st.success("Deleted!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Delete failed: {e}")

st.markdown("---")
st.subheader("Create New Intent Space")
with st.form("create_space"):
    name = st.text_input("Name (lowercase, underscores only)", placeholder="e.g. engineering")
    display_name = st.text_input("Display Name", placeholder="e.g. Engineering")
    description = st.text_area("Description", placeholder="Technical docs, architecture decisions...")
    keywords = st.text_input(
        "Classification Keywords",
        placeholder="e.g. architecture, deployment, code review, infrastructure",
        help="Comma-separated keywords to guide the AI classifier",
    )
    threshold = st.slider("Confidence Threshold", 0.0, 1.0, 0.7, 0.05)
    if st.form_submit_button("Create"):
        if not name or not display_name:
            st.warning("Name and Display Name are required.")
        else:
            try:
                r = httpx.post(
                    f"{BASE}/api/v1/intent-spaces",
                    json={
                        "name": name,
                        "display_name": display_name,
                        "description": description,
                        "keywords": keywords,
                        "confidence_threshold": threshold,
                    },
                    timeout=10,
                )
                r.raise_for_status()
                st.success(f"Created intent space '{name}'!")
                st.rerun()
            except httpx.HTTPStatusError as e:
                st.error(f"Failed: {e.response.text}")
            except Exception as e:
                st.error(f"Failed: {e}")
