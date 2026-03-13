"""Analytics — charts, query log, document access stats, CSV export."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import io
import streamlit as st
import httpx
import pandas as pd
from config.settings import get_settings

settings = get_settings()
BASE = settings.api_base_url

st.set_page_config(page_title="Analytics | IntelliKnow", page_icon="📈", layout="wide")
st.title("📈 Analytics")


def get(path: str, params: dict = None):
    try:
        r = httpx.get(f"{BASE}{path}", params=params or {}, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API error ({path}): {e}")
        return None


# Summary row
summary = get("/api/v1/analytics/summary")
feedback = get("/api/v1/analytics/feedback-summary")
if summary:
    cols = st.columns(6)
    cols[0].metric("Total Queries", summary["total_queries"])
    cols[1].metric("API Success Rate", f"{summary['success_rate']*100:.1f}%")
    cols[2].metric("Total Documents", summary["total_documents"])
    cols[3].metric("Total Chunks", summary["total_chunks"])
    cols[4].metric("Avg Latency (ms)", f"{summary['avg_latency_ms']:.0f}")
    if feedback and feedback.get("positive_rate") is not None:
        cols[5].metric(
            "User Satisfaction",
            f"{feedback['positive_rate']*100:.1f}%",
            help=f"👍 {feedback['thumbs_up']} / 👎 {feedback['thumbs_down']} ({feedback['total_with_feedback']} rated)",
        )
    else:
        cols[5].metric("User Satisfaction", "No feedback yet")

st.markdown("---")

# Cache hit stats
cache_stats = get("/api/v1/analytics/cache-stats", {"days": 30})
if cache_stats:
    total = cache_stats["total_queries"]
    hits = cache_stats["cache_hits"]
    rate = cache_stats["cache_hit_rate"]

    st.subheader("Cache Performance (last 30 days)")
    c1, c2, c3 = st.columns(3)
    c1.metric("Cache Hit Rate", f"{rate * 100:.1f}%")
    c2.metric("Cache Hits", hits)
    c3.metric("Cache Misses", cache_stats["cache_misses"])

    daily_cache = cache_stats.get("daily", [])
    if daily_cache:
        df_cache = pd.DataFrame(daily_cache)
        df_cache["date"] = pd.to_datetime(df_cache["date"])
        df_cache = df_cache.set_index("date")
        st.area_chart(
            df_cache[["hits", "total"]].rename(columns={"hits": "Cache Hits", "total": "Total Queries"}),
        )
    else:
        st.info("No query data in the last 30 days.")

st.markdown("---")

# Daily query volume chart
st.subheader("Daily Query Volume (last 30 days)")
daily = get("/api/v1/analytics/daily", {"days": 30})
if daily:
    df_daily = pd.DataFrame(daily)
    if not df_daily.empty:
        df_daily["date"] = pd.to_datetime(df_daily["date"])
        st.line_chart(df_daily.set_index("date")["query_count"])
    else:
        st.info("No queries in the last 30 days.")

st.markdown("---")

# Document access stats
st.subheader("Document Access Statistics")
doc_stats = get("/api/v1/analytics/documents")
if doc_stats:
    df_docs = pd.DataFrame(doc_stats)
    if not df_docs.empty:
        st.dataframe(df_docs, use_container_width=True)
        if st.button("Export Document Stats CSV"):
            csv = df_docs.to_csv(index=False)
            st.download_button(
                "Download CSV",
                data=csv.encode(),
                file_name="document_access_stats.csv",
                mime="text/csv",
            )
    else:
        st.info("No document access data yet.")

st.markdown("---")

# Query log
st.subheader("Query Log")

if "clear_log_confirmed" not in st.session_state:
    st.session_state.clear_log_confirmed = False


@st.dialog("⚠️ Clear Query Log")
def confirm_clear_log():
    st.warning(
        "This will permanently delete **all query log entries**. "
        "This action cannot be undone."
    )
    col_cancel, col_confirm = st.columns(2)
    with col_cancel:
        if st.button("Cancel", use_container_width=True):
            st.rerun()
    with col_confirm:
        if st.button("Yes, Clear All", type="primary", use_container_width=True):
            try:
                r = httpx.delete(f"{BASE}/api/v1/analytics/queries", timeout=15)
                r.raise_for_status()
                deleted = r.json().get("deleted", 0)
                st.session_state.clear_log_confirmed = True
                st.session_state._clear_log_msg = f"✅ Cleared {deleted} query log entries."
            except Exception as e:
                st.error(f"Failed to clear log: {e}")
                return
            st.rerun()


if st.session_state.get("_clear_log_msg"):
    st.success(st.session_state.pop("_clear_log_msg"))

col1, col2, col3 = st.columns([2, 2, 1])
with col1:
    source_filter = st.selectbox("Filter by source", ["All", "api", "telegram", "slack", "admin_ui"])
with col2:
    limit = st.slider("Entries to show", 10, 500, 100)
with col3:
    st.markdown("&nbsp;", unsafe_allow_html=True)  # vertical alignment spacer
    if st.button("🗑 Clear Log", type="secondary", use_container_width=True):
        confirm_clear_log()

params = {"limit": limit}
if source_filter != "All":
    params["source"] = source_filter

queries = get("/api/v1/analytics/queries", params)
if queries:
    df_q = pd.DataFrame(queries)
    if not df_q.empty:
        if "cache_hit" in df_q.columns:
            df_q["cache_hit"] = df_q["cache_hit"].map({True: "✅ Hit", False: "—", 1: "✅ Hit", 0: "—"})
        st.dataframe(df_q, use_container_width=True)

        if st.button("Export Query Log CSV"):
            csv = df_q.to_csv(index=False)
            st.download_button(
                "Download CSV",
                data=csv.encode(),
                file_name="query_log.csv",
                mime="text/csv",
            )
    else:
        st.info("No queries logged yet.")
