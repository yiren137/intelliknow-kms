"""Slack bot: Socket Mode — no public URL required."""
import logging
import os
import sys
import threading
import time
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from config.settings import get_settings

settings = get_settings()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = App(token=settings.slack_bot_token)

# Per-user conversation history: {user_id: deque([(query, answer), ...])}
_conversation_history: dict[str, deque] = {}


def _get_history(user_id: str) -> list[tuple[str, str]]:
    return list(_conversation_history.get(user_id, []))


def _update_history(user_id: str, query: str, answer: str):
    if user_id not in _conversation_history:
        _conversation_history[user_id] = deque(maxlen=settings.max_conversation_history)
    _conversation_history[user_id].append((query, answer))


def call_api(query: str, user_id: str) -> dict:
    history = _get_history(user_id)
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            f"{settings.api_base_url}/api/v1/query",
            json={
                "query": query,
                "source": "slack",
                "user_id": user_id,
                "conversation_history": history,
            },
        )
        resp.raise_for_status()
        return resp.json()


def submit_feedback(query_log_id: int, feedback: int):
    with httpx.Client(timeout=10.0) as client:
        client.post(
            f"{settings.api_base_url}/api/v1/feedback/{query_log_id}",
            json={"feedback": feedback},
        )


def format_response(data: dict) -> list[dict]:
    """Build Slack Block Kit blocks with answer and feedback buttons."""
    intent = data.get("intent_space_name", "General")
    answer = data.get("answer", "No answer available.")
    sources = data.get("sources", [])
    query_log_id = data.get("query_log_id")

    text = f"*{intent}*\n\n{answer}"
    if sources:
        source_names = list({s["document_name"] for s in sources})[:3]
        text += f"\n\n📄 Sources: {', '.join(source_names)}"

    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]

    if query_log_id:
        blocks.append({
            "type": "actions",
            "block_id": f"feedback_{query_log_id}",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "👍 Helpful"},
                    "value": f"{query_log_id}:1",
                    "action_id": "feedback_up",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "👎 Not helpful"},
                    "value": f"{query_log_id}:-1",
                    "action_id": "feedback_down",
                },
            ],
        })

    return blocks


@app.event("app_mention")
def handle_mention(event, say):
    text = event.get("text", "")
    user_id = event.get("user", "unknown")
    if "<@" in text:
        query = text.split(">", 1)[-1].strip()
    else:
        query = text.strip()

    if not query:
        say("Hi! Ask me a question about the company knowledge base.")
        return

    say("🔍 Searching...")

    try:
        data = call_api(query, user_id)
        _update_history(user_id, query, data.get("answer", ""))
        say(blocks=format_response(data), text=data.get("answer", ""))
    except httpx.HTTPStatusError as e:
        logger.error(f"API error: {e}")
        say("⚠️ Sorry, couldn't retrieve an answer right now.")
    except Exception as e:
        logger.error(f"Slack handler error: {e}")
        say("⚠️ Something went wrong. Please try again.")


@app.event("message")
def handle_dm(message, say):
    """Handle direct messages to the bot."""
    if message.get("channel_type") != "im":
        return
    query = message.get("text", "").strip()
    if not query:
        return

    user_id = message.get("user", "unknown")
    say("🔍 Searching...")

    try:
        data = call_api(query, user_id)
        _update_history(user_id, query, data.get("answer", ""))
        say(blocks=format_response(data), text=data.get("answer", ""))
    except Exception as e:
        logger.error(f"DM handler error: {e}")
        say("⚠️ Something went wrong. Please try again.")


@app.action("feedback_up")
def handle_feedback_up(ack, body, say):
    ack()
    try:
        value = body["actions"][0]["value"]
        query_log_id, feedback = value.split(":")
        submit_feedback(int(query_log_id), int(feedback))
        say("👍 Thanks for the feedback!")
    except Exception as e:
        logger.error(f"Feedback up error: {e}")


@app.action("feedback_down")
def handle_feedback_down(ack, body, say):
    ack()
    try:
        value = body["actions"][0]["value"]
        query_log_id, feedback = value.split(":")
        submit_feedback(int(query_log_id), int(feedback))
        say("👎 Thanks, we'll work on improving!")
    except Exception as e:
        logger.error(f"Feedback down error: {e}")


def heartbeat_thread():
    """Background thread to mark Slack bot alive in the API."""
    while True:
        try:
            with httpx.Client(timeout=10.0) as client:
                client.put(
                    f"{settings.api_base_url}/api/v1/bots/slack",
                    json={"is_active": True},
                )
        except Exception:
            pass
        time.sleep(60)


def main():
    if not settings.slack_bot_token:
        logger.error("SLACK_BOT_TOKEN not set in .env")
        sys.exit(1)
    if not settings.slack_app_token:
        logger.error("SLACK_APP_TOKEN not set in .env")
        sys.exit(1)

    t = threading.Thread(target=heartbeat_thread, daemon=True)
    t.start()

    logger.info("Starting Slack bot (Socket Mode)...")
    handler = SocketModeHandler(app, settings.slack_app_token)
    handler.start()


if __name__ == "__main__":
    main()
