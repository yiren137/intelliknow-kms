"""Frontend Integration — Telegram & Slack bot status."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import httpx
from config.settings import get_settings

settings = get_settings()
BASE = settings.api_base_url

st.set_page_config(page_title="Frontend Integration | IntelliKnow", page_icon="🤖", layout="wide")
st.title("🤖 Frontend Integration")
st.caption("Status of messaging bot integrations")


def get_bots():
    try:
        r = httpx.get(f"{BASE}/api/v1/bots", timeout=10)
        r.raise_for_status()
        return {b["platform"].lower(): b for b in r.json()}
    except Exception as e:
        st.error(f"API error: {e}")
        return {}


def _masked(token: str, placeholder: str) -> str:
    if not token or token.startswith(placeholder):
        return "Not configured"
    return f"...{token[-4:]}"


def _run_test_query(query: str, source: str) -> dict | None:
    try:
        r = httpx.post(
            f"{BASE}/api/v1/query",
            json={"query": query, "source": source},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Query failed: {e}")
        return None


def _render_bot_tab(platform: str, bot: dict, token_display: str, instructions: str):
    icon = "✅" if bot["is_active"] else "⚪"
    status = "Active" if bot["is_active"] else "Inactive"
    last_seen = bot.get("last_seen_at") or "Never"

    col_info, col_test = st.columns([1, 1])

    with col_info:
        st.markdown(f"#### {icon} Status: **{status}**")
        st.markdown(f"**Last seen:** {last_seen}")
        st.markdown(f"**API Key:** `{token_display}`")
        st.markdown(instructions)

    with col_test:
        st.markdown("#### ▶ Test Query")
        test_q = st.text_input(
            "Enter a test question",
            placeholder="e.g. What is the vacation policy?",
            key=f"test_q_{platform}",
        )
        if st.button("Send", key=f"test_btn_{platform}", use_container_width=True):
            if test_q:
                with st.spinner("Querying..."):
                    data = _run_test_query(test_q, source=f"{platform}_test")
                if data:
                    st.success(
                        f"**Intent:** {data.get('intent_space_name')} "
                        f"(confidence: {data.get('confidence', 0):.2f})"
                    )
                    st.markdown(f"**Answer:** {data.get('answer', '')[:500]}")
                    if data.get("sources"):
                        names = list({s["document_name"] for s in data["sources"]})[:3]
                        st.caption(f"Sources: {', '.join(names)}")
            else:
                st.warning("Enter a query first.")


bots = get_bots()

tab_telegram, tab_slack = st.tabs(["📱 Telegram", "💬 Slack"])

with tab_telegram:
    bot = bots.get("telegram")
    if not bot:
        st.warning("Telegram bot not found in database.")
    else:
        _render_bot_tab(
            platform="telegram",
            bot=bot,
            token_display=_masked(settings.telegram_bot_token, "your_telegram"),
            instructions="""
**Setup:**
1. Create a bot via [@BotFather](https://t.me/BotFather)
2. Copy the token to `TELEGRAM_BOT_TOKEN` in `.env`
3. Run: `python bots/telegram_bot.py`
""",
        )

with tab_slack:
    bot = bots.get("slack")
    if not bot:
        st.warning("Slack bot not found in database.")
    else:
        _render_bot_tab(
            platform="slack",
            bot=bot,
            token_display=_masked(settings.slack_bot_token, "xoxb-your"),
            instructions="""
**Setup:**
1. Create a Slack app at [api.slack.com](https://api.slack.com)
2. Enable Socket Mode and Events API
3. Copy Bot Token (`xoxb-`) → `SLACK_BOT_TOKEN`
4. Copy App Token (`xapp-`) → `SLACK_APP_TOKEN`
5. Run: `python bots/slack_bot.py`
""",
        )
