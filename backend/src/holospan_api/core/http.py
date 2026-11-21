from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from holospan_api.core.contracts import ErrorBody, ErrorDetail, ErrorEnvelope, Meta


def response_meta(request: Request) -> Meta:
    return Meta(request_id=request.state.request_id, timestamp=datetime.now(UTC))


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid4()))[:128]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = "no-store"
        return response


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    error = ErrorEnvelope(
        error=ErrorBody(
            code="VALIDATION_ERROR",
            message="The request contains invalid parameters.",
            details=[
                ErrorDetail(
                    field=".".join(str(part) for part in item["loc"]),
                    code=str(item["type"]),
                    message=str(item["msg"]),
                )
                for item in exc.errors()
            ],
            request_id=request_id,
            timestamp=datetime.now(UTC),
        )
    )
    return JSONResponse(status_code=422, content=error.model_dump(mode="json", by_alias=True))
