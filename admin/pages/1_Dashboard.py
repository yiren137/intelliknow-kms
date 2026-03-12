"""Dashboard — summary cards + recent queries table."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import httpx
from config.settings import get_settings

settings = get_settings()
BASE = settings.api_base_url

st.set_page_config(page_title="Dashboard | IntelliKnow", page_icon="📊", layout="wide")
st.title("📊 Dashboard")


def get(path: str):
    try:
        r = httpx.get(f"{BASE}{path}", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API error: {e}")
        return None


# Summary cards
summary = get("/api/v1/analytics/summary")
if summary:
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Queries", summary["total_queries"])
    col2.metric("Success Rate", f"{summary['success_rate']*100:.1f}%")
    col3.metric("Documents", summary["total_documents"])
    col4.metric("Chunks Indexed", summary["total_chunks"])
    col5.metric("Avg Latency", f"{summary['avg_latency_ms']:.0f} ms")

    st.markdown("---")

    # Top intent spaces
    if summary["top_intent_spaces"]:
        st.subheader("Top Intent Spaces")
        import pandas as pd
        df = pd.DataFrame(summary["top_intent_spaces"])
        st.bar_chart(df.set_index("name")["count"])

# Recent queries
st.subheader("Recent Queries")
queries = get("/api/v1/analytics/queries?limit=20")
if queries:
    import pandas as pd
    df = pd.DataFrame(queries)
    if not df.empty:
        display_cols = ["created_at", "query_text", "intent_space_name", "source", "response_status", "latency_ms"]
        display_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(df[display_cols], use_container_width=True)
    else:
        st.info("No queries yet. Send a query via the API or a bot!")

# Health check
health = get("/health")
if health and health.get("status") == "ok":
    st.success("✅ API is healthy")
else:
    st.error("❌ API is not responding")
