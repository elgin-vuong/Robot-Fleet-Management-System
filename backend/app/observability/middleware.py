"""HTTP-level observability: request IDs, access logs, and metrics.

One middleware does all three because they share the same "wrap the
request" shape and the same timing measurement — splitting them into three
middlewares would mean computing the duration twice or passing state
between them via request.state for no real benefit.
"""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.app.observability.logging import request_id_var
from backend.app.observability.metrics import (
    http_request_duration_seconds,
    http_requests_in_flight,
    http_requests_total,
)

logger = logging.getLogger("backend.app.http")

REQUEST_ID_HEADER = "X-Request-ID"


def _route_template(request: Request) -> str:
    """The matched route's path template (e.g. "/robots/{robot_id}"),
    falling back to the raw path for unmatched requests (404s, or a path no
    route claims) so those don't each create a distinct, unbounded metric
    label.

    Reads `request.scope["route"]` rather than walking `request.app.routes`
    and re-matching by hand: Starlette's routing sets this key on the scope
    once it resolves the request, and it's already the specific `APIRoute`
    matched (correct regardless of how deeply routers are nested, or of
    FastAPI-version-specific router wrapper types) — but it's only set
    *after* routing runs, i.e. after `call_next()` returns, not before.
    """
    route = request.scope.get("route")
    if route is not None:
        return getattr(route, "path", request.url.path)

    return "unmatched"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER, str(uuid.uuid4()))
        token = request_id_var.set(request_id)
        request.state.request_id = request_id

        http_requests_in_flight.inc()
        start = time.perf_counter()
        status_code = 500

        try:
            response: Response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration = time.perf_counter() - start
            route = _route_template(request)

            http_requests_in_flight.dec()
            http_requests_total.labels(method=request.method, route=route, status_code=str(status_code)).inc()
            http_request_duration_seconds.labels(method=request.method, route=route).observe(duration)

            # request_id is not passed here — it's already attached to every
            # log record automatically via request_id_var (see logging.py).
            logger.info(
                "http.request",
                extra={
                    "http_method": request.method,
                    "http_route": route,
                    "http_status_code": status_code,
                    "duration_ms": round(duration * 1000, 2),
                },
            )

            request_id_var.reset(token)
