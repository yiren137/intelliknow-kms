"""FastAPI application entry point."""
import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from db.database import init_db
from api.routers import health, query, documents, intent_spaces, analytics, bots, feedback

# ── Logging setup ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("intelliknow")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting IntelliKnow KMS...")
    init_db()
    logger.info("Database initialised.")
    yield
    logger.info("Shutting down IntelliKnow KMS.")


app = FastAPI(
    title="IntelliKnow KMS API",
    description="Gen AI-powered Knowledge Management System",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Global error handler ───────────────────────────────────────────────────
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception on %s %s\n%s",
        request.method,
        request.url,
        traceback.format_exc(),
    )
    return JSONResponse(status_code=500, content={"detail": str(exc)})

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(query.router)
app.include_router(documents.router)
app.include_router(intent_spaces.router)
app.include_router(analytics.router)
app.include_router(bots.router)
app.include_router(feedback.router)


@app.get("/")
def root():
    return {"name": "IntelliKnow KMS", "version": "1.0.0", "docs": "/docs"}
