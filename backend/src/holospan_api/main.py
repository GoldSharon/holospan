import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from holospan_api.core.config import get_settings
from holospan_api.core.http import RequestContextMiddleware, validation_error_handler
from holospan_api.domains.assurance_generation.http import router as assurance_generation_router
from holospan_api.domains.identity_access.errors import IdentityProblem, identity_problem_handler
from holospan_api.domains.identity_access.http import platform_router, tenant_router
from holospan_api.domains.system_catalog.http import router as system_catalog_router
from holospan_api.domains.system_context.http import router as system_context_router
from holospan_api.platform.health import router as health_router

logger = structlog.get_logger()
settings = get_settings()


app = FastAPI(
    title=settings.app_name,
    description="Versioned control-plane API for the Holospan AI assurance platform.",
    version=settings.version,
    contact={"name": "Holospan API team"},
    license_info={"name": "Proprietary"},
    servers=[{"url": "/", "description": "Current Holospan deployment."}],
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Idempotency-Key",
        "X-Request-ID",
        "X-CSRF-Token",
        "X-Holospan-Tenant-ID",
    ],
)
app.add_middleware(RequestContextMiddleware)
app.include_router(health_router)
app.include_router(tenant_router)
app.include_router(platform_router)
app.include_router(system_catalog_router)
app.include_router(system_context_router)
app.include_router(assurance_generation_router)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return await validation_error_handler(request, exc)


@app.exception_handler(IdentityProblem)
async def handle_identity_problem(request: Request, exc: IdentityProblem) -> JSONResponse:
    return await identity_problem_handler(request, exc)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"service": "holospan-api", "docs": "/docs", "health": "/api/v1/health/liveness"}
