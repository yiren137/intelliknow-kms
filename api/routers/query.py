import logging

from fastapi import APIRouter, HTTPException
from api.schemas import QueryRequest, QueryResponse
from core.orchestrator import run_query

router = APIRouter(prefix="/api/v1", tags=["query"])
logger = logging.getLogger("intelliknow.query")


@router.post("/query", response_model=QueryResponse)
def query_endpoint(request: QueryRequest):
    logger.info("Query received: '%s' (source=%s)", request.query, request.source)
    try:
        history = [tuple(pair) for pair in request.conversation_history] if request.conversation_history else None
        result = run_query(
            query=request.query,
            source=request.source,
            user_id=request.user_id,
            conversation_history=history,
        )
        logger.info("Query resolved to intent_space=%s", result.get("intent_space"))
        return QueryResponse(**result)
    except Exception as e:
        logger.exception("Error processing query: '%s'", request.query)
        raise HTTPException(status_code=500, detail=str(e))
