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
        return JSONResponse(status_code=400, content=body.model_dump())
