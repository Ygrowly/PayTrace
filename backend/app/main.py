"""FastAPI application entrypoint."""

import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1 import api_v1_router
from app.config import get_settings


class TraceIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique trace_id to every request.

    The trace_id is available at ``request.state.trace_id`` and is also
    returned in the ``X-Trace-Id`` response header.
    """

    async def dispatch(self, request: Request, call_next):
        trace_id = str(uuid.uuid4())
        request.state.trace_id = trace_id
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach browser-facing security headers to every API response."""

    def __init__(self, app, *, enable_hsts: bool = False):  # noqa: ANN001
        super().__init__(app)
        self._enable_hsts = enable_hsts

    async def dispatch(self, request: Request, call_next):  # noqa: ANN001, ANN201
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if self._enable_hsts:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="PayTrace Backend",
        version="0.0.1",
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.trusted_hosts,
    )
    app.add_middleware(
        SecurityHeadersMiddleware,
        enable_hsts=settings.app_env in {"staging", "production"},
    )
    app.add_middleware(TraceIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
    )
    app.include_router(api_v1_router)
    return app


app = create_app()
