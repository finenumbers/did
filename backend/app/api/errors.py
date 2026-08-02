from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.providers.errors import ProviderCapabilityLimitedError, ProviderError
from app.schemas.common import ErrorBody, ErrorResponse


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProviderCapabilityLimitedError)
    async def capability_limited(_request: Request, exc: ProviderCapabilityLimitedError):
        body = ErrorResponse(
            error=ErrorBody(
                code=exc.code,
                message=exc.message,
                provider=exc.provider,
                capability=exc.capability,
                details=exc.details,
            )
        )
        return JSONResponse(status_code=409, content=body.model_dump())

    @app.exception_handler(ProviderError)
    async def provider_error(_request: Request, exc: ProviderError):
        body = ErrorResponse(
            error=ErrorBody(code=exc.code, message=exc.message, details=exc.details)
        )
        if exc.code == "SYNC_RUN_NOT_FOUND":
            status = 404
        elif exc.code == "INVALID_CREDENTIALS":
            status = 401
        elif exc.code in {
            "SYNC_ALREADY_RUNNING",
            "PSTN_INN_CACHE_NOT_READY",
            "PSTN_INN_CACHE_REFRESH_RUNNING",
            "REQUIRED_OPERATOR_LOCKED",
            "OPERATOR_INN_EXISTS",
            "AUTH_DISABLED",
        }:
            status = 409
        else:
            status = 400
        return JSONResponse(status_code=status, content=body.model_dump())
