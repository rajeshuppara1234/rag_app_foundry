"""One endpoint for the existing RAG query pipeline."""

from functools import lru_cache
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.retrieval.augument_gen import AugmentGen
from app.retrieval.retriever import RAGRetriever
from app.retrieval.vector_store import VectorStore

router = APIRouter()
logger = logging.getLogger(__name__)


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, examples=["What is LangChain?"])

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value


class QueryResponse(BaseModel):
    answer: str


@lru_cache(maxsize=1)
def get_rag_components():
    return RAGRetriever(VectorStore()), AugmentGen()


@router.post("/query", response_model=QueryResponse)
def query_documents(request: QueryRequest) -> QueryResponse:
    """Retrieve relevant documents and return the generated answer."""
    try:
        retriever, generator = get_rag_components()
        answer = generator.rag_simple(request.query, retriever, generator.llm)
    except Exception as exc:
        logger.exception("RAG query failed")
        raise HTTPException(
            status_code=503,
            detail="Query failed. Check the terminal logs and root .env settings.",
        ) from exc
    return QueryResponse(answer=answer)
