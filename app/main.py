"""Start with: uv run uvicorn app.main:app --reload."""

from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(title="RAG Query", redoc_url=None)
app.include_router(router)
