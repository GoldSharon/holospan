from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

from holospan_api.core.contracts import ErrorBody, ErrorEnvelope


@dataclass(slots=True)
class IdentityProblem(Exception):
    status_code: int
    code: str
    message: str


async def identity_problem_handler(request: Request, exc: IdentityProblem) -> JSONResponse:
    body = ErrorEnvelope(
        error=ErrorBody.model_validate(
            {
                "code": exc.code,
                "message": exc.message,
                "requestId": getattr(request.state, "request_id", str(uuid4())),
                "timestamp": datetime.now(UTC),
            }
        )
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=body.model_dump(mode="json", by_alias=True),
    )


def identity_not_configured() -> IdentityProblem:
    return IdentityProblem(503, "IDENTITY_NOT_CONFIGURED", "Identity is not configured.")


def authentication_required() -> IdentityProblem:
    return IdentityProblem(401, "AUTHENTICATION_REQUIRED", "Authentication is required.")


def permission_denied() -> IdentityProblem:
    return IdentityProblem(403, "PERMISSION_DENIED", "The requested action is not permitted.")
