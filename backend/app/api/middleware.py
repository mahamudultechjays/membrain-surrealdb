"""Request middleware: a trace id and one console line per request."""

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.services import logger

TRACE_ID_HEADER = "X-Trace-Id"


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        trace_id = f"t-{uuid.uuid4().hex[:12]}"
        request.state.trace_id = trace_id
        started = time.perf_counter()

        response = await call_next(request)
        response.headers[TRACE_ID_HEADER] = trace_id
        logger.log(
            "[HTTP]",
            trace_id=trace_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            user=(request.scope.get("session") or {}).get("user", {}).get("email"),
            ms=round((time.perf_counter() - started) * 1000),
        )
        return response
