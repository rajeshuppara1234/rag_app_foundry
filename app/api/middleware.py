"""Bound request bodies and log request IDs without prompts or tokens."""

import asyncio
import json
import logging
from time import monotonic
from uuid import uuid4
from urllib.parse import urlsplit
from starlette.responses import JSONResponse

logger = logging.getLogger("rag.http")


class RequestSafetyMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        start = monotonic()
        status = 500

        async def safe_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                settings = scope["app"].state.settings
                authority = "https://" + urlsplit(settings.auth_authority).netloc
                headers = list(message.get("headers", []))
                policy = (
                    "default-src 'self'; script-src 'self'; style-src 'self'; "
                    f"connect-src 'self' {authority} https://login.microsoftonline.com; "
                    f"frame-src {authority} https://login.microsoftonline.com; "
                    "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
                )
                headers.extend(
                    [
                        (b"x-request-id", request_id.encode()),
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"cache-control", b"no-store"),
                        (b"content-security-policy", policy.encode()),
                        (b"x-frame-options", b"DENY"),
                    ]
                )
                if settings.app_env == "production":
                    headers.append((b"strict-transport-security", b"max-age=31536000"))
                message["headers"] = headers
            await send(message)

        async def reject(code, detail):
            await JSONResponse(
                {"detail": detail, "request_id": request_id}, status_code=code
            )(scope, receive, safe_send)

        try:
            headers = dict(scope["headers"])
            origin = headers.get(b"origin")
            if scope["path"].startswith("/api/") and origin is not None:
                if (
                    origin.decode("latin-1")
                    != scope["app"].state.settings.public_origin
                ):
                    return await reject(403, "Origin is not allowed")
            body = bytearray()
            try:
                async with asyncio.timeout(10):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        body.extend(message.get("body", b""))
                        if len(body) > 32768:
                            return await reject(413, "Request body is too large")
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                return await reject(408, "Request body took too long to arrive")
            sent = False

            async def replay():
                nonlocal sent
                if not sent:
                    sent = True
                    return {
                        "type": "http.request",
                        "body": bytes(body),
                        "more_body": False,
                    }
                return await receive()

            await self.app(scope, replay, safe_send)
        finally:
            logger.info(
                json.dumps(
                    {
                        "request_id": request_id,
                        "method": scope["method"],
                        "path": scope["path"],
                        "status": status,
                        "duration_ms": round((monotonic() - start) * 1000),
                    }
                )
            )
