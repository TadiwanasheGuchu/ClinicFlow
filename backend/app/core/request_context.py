"""Per-request context (request id, client IP) used by audit logging."""

import re
import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
source_ip_var: ContextVar[str | None] = ContextVar("source_ip", default=None)

_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RequestContextMiddleware:
    """Assigns a request id (honouring a well-formed X-Request-ID) and records the client IP.

    Behind a reverse proxy, run uvicorn with --proxy-headers and a trusted
    --forwarded-allow-ips so ``client`` reflects the real caller.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        client = scope.get("client")
        rid_token = request_id_var.set(request_id)
        ip_token = source_ip_var.set(client[0] if client else None)

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"].append((b"x-request-id", request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            request_id_var.reset(rid_token)
            source_ip_var.reset(ip_token)
