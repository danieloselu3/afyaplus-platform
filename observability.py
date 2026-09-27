# observability.py - one request id per request, one log line per request.
# The same id is the agent's trace id, so `grep trace=<id> logs/*.log` rebuilds
# a request across the API, the agent loop and the MCP server.
import time
from uuid import uuid4

from fastapi import FastAPI, Request


def add_request_logging(app: FastAPI, log) -> None:
    """Give every request a short trace id (or honour X-Request-ID), echo it in the
    response header, and write one line: trace, method, path, status, ms."""
    @app.middleware("http")
    async def request_log(request: Request, call_next):
        trace_id = (request.headers.get("X-Request-ID") or uuid4().hex[:8])[:32]
        request.state.trace_id = trace_id
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = trace_id
            return response
        finally:
            ms = int((time.perf_counter() - started) * 1000)
            log.info("trace=%s method=%s path=%s status=%s ms=%s",
                     trace_id, request.method, request.url.path, status, ms)
