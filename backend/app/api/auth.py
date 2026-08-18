"""Admin auth middleware + helpers."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.security import api_protection_enabled, is_authorized_bearer

PUBLIC_API_PREFIXES = (
    "/api/v1/auth/login",
    "/api/v1/auth/status",
)


def _is_export_download_with_ticket(request: Request) -> bool:
    if request.method not in ("GET", "HEAD"):
        return False
    path = request.url.path
    if not path.startswith("/api/v1/numbers/export-jobs/"):
        return False
    if not path.endswith("/download"):
        return False
    ticket = (request.query_params.get("ticket") or "").strip()
    return bool(ticket)


class AdminAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not api_protection_enabled():
            return await call_next(request)
        path = request.url.path
        if not path.startswith("/api/v1"):
            return await call_next(request)
        if any(path == p or path.startswith(p + "/") for p in PUBLIC_API_PREFIXES):
            return await call_next(request)
        if _is_export_download_with_ticket(request):
            return await call_next(request)
        auth_header = request.headers.get("Authorization")
        if is_authorized_bearer(auth_header):
            return await call_next(request)
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "message": "Требуется вход администратора",
                    "code": "UNAUTHORIZED",
                    "details": {},
                }
            },
        )
