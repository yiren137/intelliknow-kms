# IntelliKnow KMS

A **Gen AI-powered Knowledge Management System** built with FastAPI, Streamlit, FAISS, SQLite, and Anthropic Claude.

---

## Features

- **Smart Query Routing** — Claude classifies queries into intent spaces (HR, Legal, Finance, General)
- **Semantic Search** — Local `all-MiniLM-L6-v2` embeddings + FAISS vector search
- **Cited Answers** — Claude generates answers grounded in retrieved document chunks, with source citations
- **Document Management** — Upload PDF/DOCX, auto-chunk, index into FAISS; full delete support
- **Telegram Bot** — Polling-based; users ask questions via chat
- **Slack Bot** — Socket Mode (no public URL needed); responds to `@mentions` and DMs
- **Admin UI** — Streamlit dashboard for KB management, analytics, and bot status

---

## Quick Start

### Prerequisites

- Python 3.11+
- Anthropic API key ([console.anthropic.com](https://console.anthropic.com))
- (Optional) Telegram bot token and Slack app credentials

### Setup

```bash
cd /Users/yirren/IdeaProjects/intelliknow-kms

# Create virtual environment
python3 -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and fill in your ANTHROPIC_API_KEY (required)
# Add TELEGRAM_BOT_TOKEN and SLACK_BOT_TOKEN/SLACK_APP_TOKEN (optional)

# One-time setup: create directories + initialize DB
python scripts/init_db.py
```

### Run

Open **4 terminals** (or run only what you need):

```bash
# Terminal 1: FastAPI backend (required)
source .venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Streamlit admin (optional but recommended)
source .venv/bin/activate
streamlit run admin/app.py --server.port 8501

# Terminal 3: Telegram bot (optional)
source .venv/bin/activate
python bots/telegram_bot.py

# Terminal 4: Slack bot (optional)
source .venv/bin/activate
python bots/slack_bot.py
```

---

## Verification

```bash
# 1. Health check
curl http://localhost:8000/health
# → {"status": "ok"}

# 2. Upload a document
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -F "file=@/path/to/your/document.pdf" \
  -F "intent_space=hr"

# 3. Query the knowledge base
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the vacation policy?", "source": "api"}'

# 4. View analytics
curl http://localhost:8000/api/v1/analytics/summary

# 5. Open Streamlit admin
open http://localhost:8501

# 6. API docs (Swagger UI)
open http://localhost:8000/docs
```

---

## Project Structure

```
intelliknow-kms/
├── config/settings.py          # Pydantic BaseSettings
├── db/
│   ├── database.py             # SQLite context manager + init_db
│   └── models.py               # Dataclass type hints
├── core/
│   ├── embedder.py             # sentence-transformers singleton
│   ├── vector_store.py         # FAISS IndexFlatIP per intent space
│   ├── document_processor.py  # LangChain PDF/DOCX loader + splitter
│   ├── classifier.py           # Claude intent classification
│   ├── responder.py            # Claude cited answer generation
│   └── orchestrator.py        # Full query pipeline
├── api/
│   ├── main.py                 # FastAPI app
│   ├── schemas.py              # Pydantic models
│   └── routers/                # One file per resource
├── bots/
│   ├── telegram_bot.py         # python-telegram-bot v21 polling
│   └── slack_bot.py            # slack-bolt Socket Mode
├── admin/
│   ├── app.py                  # Streamlit entry point
│   └── pages/                  # 5 admin pages
├── scripts/init_db.py          # One-time setup script
└── data/                       # Runtime data (gitignored)
    ├── intelliknow.db
    ├── uploads/
    └── faiss_indices/
```

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check |
| POST | `/api/v1/query` | Main query endpoint |
| POST | `/api/v1/documents/upload` | Upload PDF/DOCX |
| GET | `/api/v1/documents` | List documents |
| DELETE | `/api/v1/documents/{id}` | Delete document |
| GET | `/api/v1/intent-spaces` | List intent spaces |
| POST | `/api/v1/intent-spaces` | Create intent space |
| PUT | `/api/v1/intent-spaces/{id}` | Update intent space |
| DELETE | `/api/v1/intent-spaces/{id}` | Delete intent space |
| GET | `/api/v1/analytics/summary` | Aggregated stats |
| GET | `/api/v1/analytics/queries` | Paginated query log |
| GET | `/api/v1/analytics/documents` | Per-doc access counts |
| GET | `/api/v1/analytics/daily` | Daily volume chart data |
| GET | `/api/v1/bots` | Bot status |
| PUT | `/api/v1/bots/{platform}` | Update bot status |

Full interactive docs: `http://localhost:8000/docs`

---

## Slack App Setup

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → Create New App → From Scratch
2. Under **OAuth & Permissions**, add Bot Token Scopes: `app_mentions:read`, `chat:write`, `im:history`, `im:read`
3. Under **Socket Mode**, enable it and generate an App-Level Token (`xapp-`) with `connections:write`
4. Under **Event Subscriptions**, enable and subscribe to: `app_mention`, `message.im`
5. Install app to workspace and copy Bot Token (`xoxb-`)
6. Set `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` in `.env`

## Telegram Bot Setup

1. Message [@BotFather](https://t.me/BotFather) → `/newbot`
2. Copy the token to `TELEGRAM_BOT_TOKEN` in `.env`

---

## AI Usage Reflection

### What the AI does

IntelliKnow uses Claude for two high-value tasks:

1. **Intent Classification** (`core/classifier.py`): Claude reads the user's query and outputs a JSON object identifying which intent space (HR, Legal, Finance, General) the query belongs to, with a confidence score and one-sentence reasoning. This is a much better approach than keyword matching — Claude understands the semantic meaning of the query.

2. **Cited Answer Generation** (`core/responder.py`): Claude receives the top-k retrieved document chunks and produces a grounded, cited answer. It's explicitly instructed to use only the provided context, preventing hallucination, and to cite sources inline using `[Source N]` notation.

### What the AI does NOT do

Embedding is handled locally by `sentence-transformers/all-MiniLM-L6-v2` (384-dim, ~22MB). This runs entirely on CPU with no API cost, making it fast and free for bulk document indexing. Claude's API is only called at query time (two calls per query).

### Design trade-offs

- **IndexFlatIP vs IVFFlat**: Chose exact search (IndexFlatIP) for correctness at MVP scale. IVFFlat is faster for millions of vectors but requires training and introduces approximation error.
- **Rebuild-on-delete for FAISS**: FAISS has no native `remove()` for flat indices. We store raw vectors in `metadata.pkl` alongside the index, enabling rebuild-without-re-embedding when a document is deleted.
- **Sync document processing**: Upload → chunk → embed → index happens synchronously in the request handler. This is acceptable for MVP. A production system would use a task queue (Celery/RQ) with progress tracking.
- **SQLite over PostgreSQL**: Sufficient for the MVP's query volume and simplifies deployment. The `get_db_connection()` context manager with WAL mode handles concurrent reads well.
