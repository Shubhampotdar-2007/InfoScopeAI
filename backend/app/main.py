"""
InfoScope AI — FastAPI Application Entry Point.
Production-minded foundation with CORS, structured responses, Swagger docs, and health checks.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.api.routes import api_router
from app.schemas.response import APIResponse
from app.database import close_db_http_client, DatabaseError


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    print(f"[{datetime.now(timezone.utc).isoformat()}] {settings.PROJECT_NAME} v{settings.VERSION} starting...")
    print(f"Environment: {settings.ENVIRONMENT} | Debug: {settings.DEBUG}")
    print(f"CORS Allowed Origins: {settings.CORS_ORIGINS}")
    yield
    # Shutdown actions
    await close_db_http_client()
    print(f"[{datetime.now(timezone.utc).isoformat()}] {settings.PROJECT_NAME} shutting down...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="AI-assisted information gap detection platform API.",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception Handler: HTTP Exceptions
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=APIResponse(
            success=False,
            status_code=exc.status_code,
            message=str(exc.detail),
            data=None
        ).model_dump(mode="json")
    )


# Exception Handler: Request Validation Errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    formatted_errors = [
        {"field": " -> ".join(str(loc) for loc in err["loc"]), "message": err["msg"]}
        for err in errors
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=APIResponse(
            success=False,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            message="Request validation failed.",
            data={"errors": formatted_errors}
        ).model_dump(mode="json")
    )


# Exception Handler: Database Exceptions
@app.exception_handler(DatabaseError)
async def database_exception_handler(request: Request, exc: DatabaseError):
    return JSONResponse(
        status_code=exc.status_code,
        content=APIResponse(
            success=False,
            status_code=exc.status_code,
            message=exc.message,
            data=None
        ).model_dump(mode="json")
    )


# Exception Handler: Catch-all Generic Exceptions
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=APIResponse(
            success=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="An unexpected internal server error occurred.",
            data={"error_type": exc.__class__.__name__} if settings.DEBUG else None
        ).model_dump(mode="json")
    )


# Include modular API routers
app.include_router(api_router, prefix=settings.API_V1_STR)


# Root Endpoint: GET /
@app.get(
    "/",
    response_model=APIResponse[dict],
    status_code=status.HTTP_200_OK,
    tags=["Root"],
    summary="API Root Information"
)
async def root() -> APIResponse[dict]:
    """Root endpoint welcoming clients and directing them to docs and health endpoints."""
    return APIResponse(
        success=True,
        status_code=status.HTTP_200_OK,
        message=f"Welcome to {settings.PROJECT_NAME} API",
        data={
            "service": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
            "docs_url": "/docs",
            "health_url": f"{settings.API_V1_STR}/health"
        }
    )
