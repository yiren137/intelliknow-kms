"""Telegram bot: receives messages and calls the FastAPI backend."""
import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from config.settings import get_settings

settings = get_settings()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{settings.api_base_url}/api/v1/query",
                json={"query": query, "source": "telegram", "user_id": user_id},
            )
            response.raise_for_status()
            data = response.json()

        answer = data["answer"]
        intent = data.get("intent_space_name", "General")
        sources = data.get("sources", [])

        reply = f"📂 {intent}\n\n{answer}"
        if sources:
            source_names = list({s["document_name"] for s in sources})[:3]
            reply += f"\n\n📄 Sources: {', '.join(source_names)}"

        await update.message.reply_text(reply)

    except httpx.HTTPStatusError as e:
        logger.error(f"API error: {e}")
        await update.message.reply_text(
            "⚠️ Sorry, I couldn't get an answer right now. Please try again."
        )
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await update.message.reply_text("⚠️ Something went wrong. Please try again later.")


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

    loop = asyncio.get_event_loop()
    loop.create_task(heartbeat_task())

    logger.info("Starting Telegram bot (polling)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
