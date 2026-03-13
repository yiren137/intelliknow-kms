"""Telegram bot: receives messages and calls the FastAPI backend."""
import asyncio
import logging
import sys
import os
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

from config.settings import get_settings

settings = get_settings()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_MAX_LENGTH = 4096

# Per-user conversation history: {user_id: deque([(query, answer), ...])}
_conversation_history: dict[str, deque] = {}


def _get_history(user_id: str) -> list[tuple[str, str]]:
    return list(_conversation_history.get(user_id, []))


def _update_history(user_id: str, query: str, answer: str):
    if user_id not in _conversation_history:
        _conversation_history[user_id] = deque(maxlen=settings.max_conversation_history)
    _conversation_history[user_id].append((query, answer))


def _split_message(text: str) -> list[str]:
    """Split text into chunks of at most TELEGRAM_MAX_LENGTH characters."""
    if len(text) <= TELEGRAM_MAX_LENGTH:
        return [text]
    parts = []
    while text:
        parts.append(text[:TELEGRAM_MAX_LENGTH])
        text = text[TELEGRAM_MAX_LENGTH:]
    return parts


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to IntelliKnow!\n\n"
        "Ask me anything about your company's knowledge base.\n"
        "I'll search through HR, Legal, Finance, and General documents to find the answer."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 How to use:\n\n"
        "• Just type your question and I'll search the knowledge base\n"
        "• Example: 'What is the vacation policy?'\n"
        "• Example: 'How do I submit an expense report?'"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    user_id = str(update.effective_user.id)

    await update.message.reply_text("🔍 Searching knowledge base...")

    try:
        history = _get_history(user_id)
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{settings.api_base_url}/api/v1/query",
                json={
                    "query": query,
                    "source": "telegram",
                    "user_id": user_id,
                    "conversation_history": history,
                },
            )
            response.raise_for_status()
            data = response.json()

        answer = data["answer"]
        intent = data.get("intent_space_name", "General")
        sources = data.get("sources", [])
        query_log_id = data.get("query_log_id")

        reply = f"📂 {intent}\n\n{answer}"
        if sources:
            source_names = list({s["document_name"] for s in sources})[:3]
            reply += f"\n\n📄 Sources: {', '.join(source_names)}"

        _update_history(user_id, query, answer)

        # Send reply in chunks if too long
        parts = _split_message(reply)
        for part in parts[:-1]:
            await update.message.reply_text(part)

        # Add feedback buttons to the last message
        if query_log_id:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("👍", callback_data=f"fb:{query_log_id}:1"),
                InlineKeyboardButton("👎", callback_data=f"fb:{query_log_id}:-1"),
            ]])
            await update.message.reply_text(parts[-1], reply_markup=keyboard)
        else:
            await update.message.reply_text(parts[-1])

    except httpx.HTTPStatusError as e:
        logger.error(f"API error: {e}")
        await update.message.reply_text(
            "⚠️ Sorry, I couldn't get an answer right now. Please try again."
        )
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await update.message.reply_text("⚠️ Something went wrong. Please try again later.")


async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 👍/👎 button presses."""
    query = update.callback_query
    await query.answer()

    try:
        _, query_log_id, feedback = query.data.split(":")
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{settings.api_base_url}/api/v1/feedback/{query_log_id}",
                json={"feedback": int(feedback)},
            )
        label = "👍 Thanks for the feedback!" if int(feedback) == 1 else "👎 Thanks, we'll improve!"
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(label)
    except Exception as e:
        logger.error(f"Feedback error: {e}")


async def heartbeat_task():
    """Periodically ping the API to mark Telegram bot as alive."""
    while True:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.put(
                    f"{settings.api_base_url}/api/v1/bots/telegram",
                    json={"is_active": True},
                )
        except Exception:
            pass
        await asyncio.sleep(60)


def main():
    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set in .env")
        sys.exit(1)

    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_feedback, pattern=r"^fb:"))

    loop = asyncio.get_event_loop()
    loop.create_task(heartbeat_task())

    logger.info("Starting Telegram bot (polling)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
