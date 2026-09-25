"""ASGI entry point. Clients are created during lifespan, never on import."""

from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from app.api.auth import TokenValidator
from app.api.limits import RequestLimits
from app.api.middleware import RequestSafetyMiddleware
from app.api.routes import router
from app.chains.service import RAGService
from app.config import Settings

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings | None = None, service_factory=RAGService) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        config = settings or Settings()
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("azure").setLevel(logging.WARNING)
        app.state.settings = config
        app.state.token_validator = TokenValidator(config)
        app.state.limits = RequestLimits(
            config.requests_per_minute,
            config.max_concurrent_requests,
            config.total_requests_per_minute,
        )
        app.state.service = await run_in_threadpool(service_factory, config)
        app.state.executor = ThreadPoolExecutor(
            max_workers=config.max_concurrent_requests
        )
        try:
            yield
        finally:
            await run_in_threadpool(
                app.state.executor.shutdown, wait=True, cancel_futures=True
            )
            await run_in_threadpool(app.state.service.close)

    app = FastAPI(
        title="Foundry Knowledge Assistant",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(RequestSafetyMiddleware)
    app.include_router(router)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error):
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {"loc": e["loc"], "msg": e["msg"], "type": e["type"]}
                    for e in error.errors()
                ],
                "request_id": request.state.request_id,
            },
        )

    @app.get("/", include_in_schema=False)
    def index():
        page = STATIC_DIR / "index.html"
        if not page.exists():
            return JSONResponse(
                {"detail": "Build the web frontend first: npm --prefix web run build"},
                status_code=503,
            )
        return FileResponse(page)

    app.mount(
        "/assets",
        StaticFiles(directory=STATIC_DIR / "assets", check_dir=False),
        name="assets",
    )
    return app


app = create_app()
