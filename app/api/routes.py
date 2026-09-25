import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.api.auth import User, current_user

router = APIRouter()
logger = logging.getLogger("rag.api")


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    question: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=10)

    @field_validator("question")
    @classmethod
    def trim_question(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Question must not be blank")
        return value


class Source(BaseModel):
    citation: int
    source: str
    page: int | None


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    request_id: str


@router.get("/health/live", include_in_schema=False)
def live():
    return {"status": "ok"}


@router.get("/health/ready", include_in_schema=False)
def ready(request: Request):
    try:
        if request.app.state.service.ready():
            return {"status": "ready"}
    except Exception:
        pass
    raise HTTPException(503, "Knowledge base is unavailable")


@router.get("/api/config", include_in_schema=False)
def browser_config(request: Request):
    return request.app.state.settings.browser_config()


@router.post("/api/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest, request: Request, user: User = Depends(current_user)
):
    limits = request.app.state.limits
    limits.check_user(user.subject)
    if not limits.slots.acquire(blocking=False):
        raise HTTPException(
            429,
            "The service is busy. Please try again shortly.",
            headers={"Retry-After": "5"},
        )
    try:
        # Keep the slot occupied until any timed-out upstream work actually finishes.
        future = request.app.state.executor.submit(
            request.app.state.service.answer, payload.question, payload.top_k
        )
    except Exception:
        limits.slots.release()
        raise HTTPException(
            503, "The answer service is temporarily unavailable"
        ) from None
    future.add_done_callback(lambda _: limits.slots.release())
    try:
        result = await asyncio.wait_for(
            asyncio.wrap_future(future),
            timeout=request.app.state.settings.request_timeout_seconds,
        )
        return {**result, "request_id": request.state.request_id}
    except TimeoutError:
        raise HTTPException(
            504, "The answer took too long. Please try again."
        ) from None
    except Exception as error:
        logger.error(
            "dependency_failure request_id=%s type=%s",
            request.state.request_id,
            type(error).__name__,
        )
        raise HTTPException(
            503, "The answer service is temporarily unavailable. Please try again."
        ) from None
