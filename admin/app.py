"""IntelliKnow KMS — Streamlit Admin Entry Point."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

st.set_page_config(
    page_title="IntelliKnow KMS",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🧠 IntelliKnow KMS")
st.subheader("Gen AI-Powered Knowledge Management System")

st.markdown("""
Welcome to the **IntelliKnow KMS Admin Console**.

Use the sidebar to navigate between sections:

| Page | Description |
|------|-------------|
| 📊 Dashboard | System overview, recent queries |
| 🤖 Frontend Integration | Telegram & Slack bot status |
| 📚 KB Management | Upload and manage documents |
| 🗂 Intent Configuration | Manage intent spaces |
| 📈 Analytics | Query logs, charts, export |
""")

st.info("Navigate using the sidebar on the left. All pages connect to the FastAPI backend at http://localhost:8000")
