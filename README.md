# IntelliKnow KMS

A **Gen AI-powered Knowledge Management System** that lets employees ask natural-language questions against your company's internal documents and receive cited, grounded answers — routed to the right knowledge domain automatically.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Architecture Overview](#architecture-overview)
- [Setup](#setup)
- [Environment Variables](#environment-variables)
- [Running the System](#running-the-system)
- [API Integration Guide](#api-integration-guide)
- [Bot Integration Guide](#bot-integration-guide)
- [Admin UI](#admin-ui)
- [Project Structure](#project-structure)
- [Design Trade-offs](#design-trade-offs)

---

## Features

- **Intent Space Routing** — Queries are automatically classified into knowledge domains (HR, Legal, Finance, General) using local embedding similarity; no API call required
- **Hybrid Search** — BM25 lexical search + FAISS vector search fused with Reciprocal Rank Fusion (RRF) for best-of-both retrieval
- **Cross-Encoder Reranking** — Retrieved candidates are reranked by `ms-marco-MiniLM-L-6-v2` before being sent to the LLM
- **Cited Answers** — Gemini generates answers grounded strictly in retrieved chunks, with inline `[Source N]` citations
- **Document Management** — Upload PDF/DOCX, auto-chunk, embed, and index; replace or delete documents at any time
- **Query Cache** — Identical queries are served from an in-memory cache (TTL: 5 min) with cache-hit tracking
- **User Feedback** — Thumbs up / thumbs down per query, surfaced in Analytics
- **Telegram Bot** — Polling-based; users ask questions via Telegram chat with conversation history
- **Slack Bot** — Socket Mode (no public URL needed); responds to `@mentions` and DMs
- **Admin UI** — Streamlit dashboard for KB management, intent space config, analytics, and bot status

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **API** | FastAPI | REST backend, request validation, OpenAPI docs |
| **Admin UI** | Streamlit | Internal dashboard (KB management, analytics) |
| **LLM** | Google Gemini 2.5 Flash | Cited answer generation |
| **Embeddings** | `BAAI/bge-base-en-v1.5` (local, 768-dim) | Query & document embeddings — no API cost |
| **Vector Search** | FAISS `IndexFlatIP` | Exact inner-product (cosine) search per intent space |
| **Lexical Search** | BM25 (`rank-bm25`) | Keyword-based retrieval fused with vector search |
| **Reranker** | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Cross-encoder precision reranking |
| **Classifier** | Local cosine similarity + temperature-scaled softmax | Zero-cost intent routing |
| **Database** | SQLite (WAL mode) | Documents, chunks, query logs, analytics |
| **Document Parsing** | LangChain + PyMuPDF / python-docx | PDF/DOCX loading and chunking |
| **Telegram** | python-telegram-bot v21 | Polling-based bot |
| **Slack** | slack-bolt Socket Mode | Event-driven bot without public URL |

---

## Architecture Overview

```
User query
    │
    ▼
1. Embed query          (BAAI/bge-base-en-v1.5, local, free)
    │
    ▼
2. Classify intent      (cosine similarity → temperature softmax → intent space)
    │
    ▼
3. Hybrid search        (BM25 + FAISS vector → Reciprocal Rank Fusion)
    │
    ▼
4. Cross-encoder rerank (ms-marco-MiniLM-L-6-v2, local, free)
    │
    ▼
5. Generate answer      (Gemini 2.5 Flash, cited, context-grounded)
    │
    ▼
6. Log + cache          (SQLite, in-memory TTL cache)
```

All embedding, classification, and reranking steps are **local and free**. Only step 5 (answer generation) calls an external API.

---

## Setup

### Prerequisites

- Python 3.11+
- Google Gemini API key ([aistudio.google.com](https://aistudio.google.com))
- (Optional) Telegram bot token
- (Optional) Slack app credentials

### Install

```bash
# Clone and enter the project
cd intelliknow-kms

# Create virtual environment
python3 -m venv .venv && source .venv/bin/activate

# Install dependencies (includes local ML models)
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — at minimum set GEMINI_API_KEY

# Initialise database and data directories
python scripts/init_db.py
```

> **First run note:** On first startup the embedding model (`BAAI/bge-base-en-v1.5`, ~440 MB) and reranker (`ms-marco-MiniLM-L-6-v2`, ~90 MB) are downloaded automatically from HuggingFace and cached locally.

---

## Environment Variables

All variables are read from `.env` (see `.env.example`):

| Variable | Required | Default | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | **Yes** | — | Google Gemini API key |
| `GEMINI_MODEL` | No | `gemini-2.5-flash` | Gemini model ID |
| `TELEGRAM_BOT_TOKEN` | No | — | Telegram bot token (from BotFather) |
| `SLACK_BOT_TOKEN` | No | — | Slack bot token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | No | — | Slack app-level token (`xapp-...`) |
| `API_BASE_URL` | No | `http://localhost:8000` | Backend URL used by bots and admin UI |
| `DB_PATH` | No | `data/intelliknow.db` | SQLite database path |
| `FAISS_DIR` | No | `data/faiss_indices` | FAISS index storage directory |
| `UPLOADS_DIR` | No | `data/uploads` | Uploaded document storage |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `DEBUG` | No | `false` | FastAPI debug mode |

---

## Running the System

Open separate terminals for each component (or run only what you need):

```bash
# Terminal 1: FastAPI backend (required)
source .venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Streamlit admin UI (recommended)
source .venv/bin/activate
streamlit run admin/app.py --server.port 8501

# Terminal 3: Telegram bot (optional)
source .venv/bin/activate
python bots/telegram_bot.py

# Terminal 4: Slack bot (optional)
source .venv/bin/activate
python bots/slack_bot.py
```

**Quick verification:**

```bash
curl http://localhost:8000/health
# → {"status": "ok"}
```

Interactive API docs: `http://localhost:8000/docs`
Admin UI: `http://localhost:8501`

---

## API Integration Guide

The REST API allows any external application to query the knowledge base, upload documents, and read analytics.

### Query the Knowledge Base

```bash
POST /api/v1/query
Content-Type: application/json

{
  "query": "What is the parental leave policy?",
  "source": "my-app",          # optional — identifies the caller in logs
  "user_id": "user-123",       # optional — for per-user tracking
  "conversation_history": [    # optional — for multi-turn conversations
    ["What is sick leave?", "Employees receive 10 paid sick days..."]
  ]
}
```

**Response:**

```json
{
  "query": "What is the parental leave policy?",
  "query_log_id": 42,
  "intent_space": "hr",
  "intent_space_name": "Human Resources",
  "confidence": 0.87,
  "reasoning": "Embedding similarity 0.821 (confidence 0.87)",
  "answer": "Employees are entitled to 16 weeks of paid parental leave [Source 1]...",
  "sources": [
    { "document_name": "hr_handbook.pdf", "document_id": 3, "page_number": 12, "score": 0.91 }
  ],
  "latency_ms": 1240,
  "status": "success"
}
```

### Submit User Feedback

```bash
POST /api/v1/query/{query_log_id}/feedback
Content-Type: application/json

{ "feedback": 1 }   # 1 = thumbs up, -1 = thumbs down
```

### Upload a Document

```bash
POST /api/v1/documents/upload
Content-Type: multipart/form-data

file=@/path/to/policy.pdf
intent_space=hr             # which knowledge domain this belongs to
```

**Response:**

```json
{
  "id": 5,
  "original_name": "policy.pdf",
  "intent_space": "hr",
  "chunk_count": 18,
  "status": "indexed"
}
```

### Replace a Document (in-place update)

```bash
POST /api/v1/documents/{id}/replace
Content-Type: multipart/form-data

file=@/path/to/updated_policy.pdf
```

Replaces the file and re-indexes without changing the document ID.

### Full API Reference

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check |
| POST | `/api/v1/query` | Run a query through the full pipeline |
| POST | `/api/v1/query/{id}/feedback` | Submit thumbs up / thumbs down |
| POST | `/api/v1/documents/upload` | Upload and index a PDF or DOCX |
| GET | `/api/v1/documents` | List all indexed documents |
| GET | `/api/v1/documents/{id}/chunks` | View parsed chunks for a document |
| POST | `/api/v1/documents/{id}/replace` | Replace a document file in-place |
| DELETE | `/api/v1/documents/{id}` | Delete document and its vectors |
| GET | `/api/v1/intent-spaces` | List intent spaces |
| POST | `/api/v1/intent-spaces` | Create a new intent space |
| PUT | `/api/v1/intent-spaces/{id}` | Update description / threshold |
| DELETE | `/api/v1/intent-spaces/{id}` | Delete an intent space |
| GET | `/api/v1/analytics/summary` | Aggregated stats |
| GET | `/api/v1/analytics/queries` | Paginated query log |
| GET | `/api/v1/analytics/documents` | Per-document access counts |
| GET | `/api/v1/analytics/daily` | Daily query volume |
| GET | `/api/v1/analytics/cache-stats` | Cache hit rate over time |
| GET | `/api/v1/analytics/feedback-summary` | Thumbs up / down totals |
| DELETE | `/api/v1/analytics/queries` | Clear all query logs |
| GET | `/api/v1/bots` | Bot integration status |
| PUT | `/api/v1/bots/{platform}` | Enable / disable a bot |

---

## Bot Integration Guide

### Telegram

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts to create a bot
3. Copy the token (format: `123456789:ABCdef...`)
4. Set `TELEGRAM_BOT_TOKEN=<token>` in `.env`
5. Run `python bots/telegram_bot.py`

Users can now send messages directly to the bot. Conversation history is retained per chat (last 5 turns).

### Slack

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From Scratch**
2. Under **OAuth & Permissions → Bot Token Scopes**, add:
   - `app_mentions:read`
   - `chat:write`
   - `im:history`
   - `im:read`
3. Under **Socket Mode**, enable it → generate an **App-Level Token** (`xapp-`) with scope `connections:write`
4. Under **Event Subscriptions**, enable and subscribe to bot events:
   - `app_mention`
   - `message.im`
5. Install the app to your workspace → copy the **Bot Token** (`xoxb-`)
6. Set in `.env`:
   ```
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_APP_TOKEN=xapp-...
   ```
7. Run `python bots/slack_bot.py`

Users can then `@mention` the bot in any channel or message it directly.

---

## Admin UI

The Streamlit admin (`http://localhost:8501`) provides:

| Page | Description |
|---|---|
| **Overview** | System health, component status, quick stats |
| **Query** | Ask questions directly from the admin UI |
| **KB Management** | Upload, view chunks, replace, or delete documents |
| **Intent Configuration** | Create/edit intent spaces, set confidence thresholds |
| **Analytics** | Query volume, latency, cache hit rate, document access, user satisfaction |

---

## Project Structure

```
intelliknow-kms/
├── config/
│   └── settings.py              # Pydantic BaseSettings — all config via .env
├── db/
│   └── database.py              # SQLite context manager, schema init, migrations
├── core/
│   ├── embedder.py              # BAAI/bge-base-en-v1.5 singleton (local, 768-dim)
│   ├── classifier.py            # Cosine similarity + temperature softmax classifier
│   ├── vector_store.py          # FAISS IndexFlatIP + BM25 hybrid search (RRF fusion)
│   ├── reranker.py              # Cross-encoder reranker (ms-marco-MiniLM-L-6-v2)
│   ├── document_processor.py    # PDF/DOCX loader + recursive text splitter
│   ├── responder.py             # Gemini cited answer generation
│   └── orchestrator.py          # Full pipeline: embed→classify→search→rerank→respond
├── api/
│   ├── main.py                  # FastAPI app with lifespan
│   ├── schemas.py               # Pydantic request/response models
│   └── routers/
│       ├── query.py
│       ├── documents.py
│       ├── intent_spaces.py
│       ├── analytics.py
│       ├── feedback.py
│       └── bots.py
├── bots/
│   ├── telegram_bot.py          # python-telegram-bot v21, polling, multi-turn history
│   └── slack_bot.py             # slack-bolt Socket Mode, app_mention + DM
├── admin/
│   ├── app.py                   # Streamlit entry point
│   └── pages/                   # 5 admin pages
├── tests/                       # pytest test suite (85 tests)
├── scripts/
│   └── init_db.py               # One-time setup script
├── .env.example                 # Environment variable template
└── data/                        # Runtime data (gitignored)
    ├── intelliknow.db
    ├── uploads/
    └── faiss_indices/
```

---

## Design Trade-offs

**Local embedding + reranking vs fully cloud-based**
Embedding (`BAAI/bge-base-en-v1.5`) and reranking (`ms-marco-MiniLM-L-6-v2`) run entirely on CPU with no API cost. Only final answer generation hits an external API (Gemini). This makes bulk document indexing free and keeps per-query API cost minimal.

**FAISS `IndexFlatIP` vs `IVFFlat`**
Exact search (`IndexFlatIP`) is used for correctness at MVP scale. `IVFFlat` is faster for millions of vectors but requires training and introduces approximation error. Raw vectors are stored in `metadata.pkl` alongside the FAISS index to enable rebuilding without re-embedding when documents are deleted (FAISS flat indices have no native `remove()`).

**BM25 + vector hybrid (RRF) vs vector-only**
Pure vector search misses exact keyword matches (e.g. product codes, names). BM25 covers these; Reciprocal Rank Fusion merges both rankings without requiring score normalisation across incompatible scales.

**Cross-encoder reranking as a second pass**
Bi-encoder (FAISS) retrieval is fast but imprecise — it scores query and document independently. The cross-encoder sees the query and document together, giving much higher precision for the final top-K sent to the LLM. The two-stage approach keeps latency acceptable.

**Temperature-scaled softmax classifier**
Raw cosine similarities between BGE embeddings cluster in a narrow range (0.75–0.85), making plain softmax output near-uniform (~1/N per space). Multiplying by temperature=10 before softmax sharpens the distribution so the winning space scores 0.4–0.9+ for clear matches, enabling a meaningful confidence threshold.

**SQLite over PostgreSQL**
Sufficient for the expected query volume and significantly simplifies deployment (single file, no server). WAL mode handles concurrent reads from the API and bots without locking.

**Synchronous document processing**
Upload → chunk → embed → index happens synchronously in the request handler. Acceptable for MVP where documents are uploaded infrequently. A production system would use a task queue (Celery/RQ) with background processing and progress tracking.
