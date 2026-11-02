"""Request middleware: API-key auth, scope context and a per-request trace line.

A request with a valid X-API-Key runs in that key's user scope
(request.state.scope); an unknown key gets 401. A request without a key is
let through with no scope, so endpoints that need one must ask for it.
"""

import secrets
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.services import logger

API_KEY_HEADER = "X-API-Key"
TRACE_ID_HEADER = "X-Trace-Id"


def _scope_for(key: str, key_scopes: Mapping[str, str]) -> str | None:
    for known, scope in key_scopes.items():
        if secrets.compare_digest(key.encode(), known.encode()):
            return scope
    return None


class ScopeContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, key_scopes: Mapping[str, str]) -> None:
        super().__init__(app)
        self._key_scopes = key_scopes

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        trace_id = f"t-{uuid.uuid4().hex[:12]}"
        request.state.trace_id = trace_id
        request.state.scope = None
        started = time.perf_counter()

        key = request.headers.get(API_KEY_HEADER)
        if key is not None:
            request.state.scope = _scope_for(key, self._key_scopes)
            if request.state.scope is None:
                logger.log("[AUTH]", trace_id=trace_id, path=request.url.path, result="invalid_key")
                return JSONResponse(
                    {"detail": "Invalid API key"},
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    headers={TRACE_ID_HEADER: trace_id},
                )

        response = await call_next(request)
        response.headers[TRACE_ID_HEADER] = trace_id
        logger.log(
            "[HTTP]",
            trace_id=trace_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            scope=request.state.scope,
            ms=round((time.perf_counter() - started) * 1000),
        )
        return response
