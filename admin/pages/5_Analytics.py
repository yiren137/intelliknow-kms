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
if summary:
    cols = st.columns(5)
    cols[0].metric("Total Queries", summary["total_queries"])
    cols[1].metric("Success Rate", f"{summary['success_rate']*100:.1f}%")
    cols[2].metric("Total Documents", summary["total_documents"])
    cols[3].metric("Total Chunks", summary["total_chunks"])
    cols[4].metric("Avg Latency (ms)", f"{summary['avg_latency_ms']:.0f}")

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

col1, col2 = st.columns(2)
with col1:
    source_filter = st.selectbox("Filter by source", ["All", "api", "telegram", "slack", "admin_ui"])
with col2:
    limit = st.slider("Entries to show", 10, 500, 100)

params = {"limit": limit}
if source_filter != "All":
    params["source"] = source_filter

queries = get("/api/v1/analytics/queries", params)
if queries:
    df_q = pd.DataFrame(queries)
    if not df_q.empty:
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
