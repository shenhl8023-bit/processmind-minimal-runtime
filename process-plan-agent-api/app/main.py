"""ProcessMind backend entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.paths import FRONTEND_DIR
from app.core.compat import run_in_thread
from app.core.product_profile import TRIAL_EXPIRED_MESSAGE, get_product_profile
from app.database import init_db
from app.services.extraction_parallel import shutdown_pdf_extraction_pool
from app.routers import analysis_guidance, documents, executable_revisions, extract, generate, knowledge, projects, public_rule_package_identities, rule_packages, settings
from app.web import install_frontend


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: 创建数据库表
    await init_db()
    try:
        yield
    finally:
        await run_in_thread(shutdown_pdf_extraction_pool)


def create_app(frontend_dir: Optional[Path] = None) -> FastAPI:
    """Build the API application, optionally serving a production frontend."""

    get_product_profile()  # Invalid or missing delivery configuration must fail closed.

    app = FastAPI(
        title="ProcessMind API",
        description="典型工艺规程智能体后端服务",
        version="1.0.0",
        lifespan=lifespan,
    )

    allowed_origins = [
        origin.strip()
        for origin in os.getenv(
            "PROCESSMIND_CORS_ORIGINS",
            "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:5174,http://localhost:5174,http://127.0.0.1:8080,http://localhost:8080",
        ).split(",")
        if origin.strip()
    ]

    # The packaged deployment is same-origin. Development origins are explicit so
    # arbitrary websites cannot read or mutate the local API.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def enforce_product_limits(request: Request, call_next):
        path = request.url.path.rstrip("/")
        profile = get_product_profile()
        status_or_health = path in {"/api/product-status", "/api/startup-ping"}
        business_api = path == "/api" or path.startswith("/api/")
        api_documentation = path in {"/docs", "/redoc", "/openapi.json"} or path.startswith("/docs/")
        if not status_or_health and (business_api or api_documentation) and profile.is_expired():
            return JSONResponse(status_code=403, content={"detail": {
                "code": "trial_expired", "message": TRIAL_EXPIRED_MESSAGE,
            }})
        template_api = any(path.startswith(prefix) for prefix in (
            "/api/extract/group-templates", "/api/extract/template-group-mappings",
            "/api/extract/template-step-mappings", "/api/extract/template-process-precisions",
        ))
        if template_api and not profile.template_mapping_enabled:
            return JSONResponse(status_code=403, content={"detail": {
                "code": "feature_disabled", "message": "当前版本不提供模板分组编排功能。",
            }})
        return await call_next(request)

    @app.get("/api/product-status")
    async def product_status():
        return get_product_profile().status()

    app.include_router(documents.router)
    app.include_router(extract.router)
    app.include_router(rule_packages.router)
    app.include_router(executable_revisions.router)
    app.include_router(public_rule_package_identities.router)
    app.include_router(generate.router)
    app.include_router(projects.router)
    app.include_router(analysis_guidance.router)
    app.include_router(settings.router)
    app.include_router(knowledge.router)

    @app.get("/api/startup-ping")
    async def startup_ping():
        return {"status": "ok", "app": "ProcessMind", "kind": "api"}

    configured_frontend = FRONTEND_DIR if frontend_dir is None else Path(frontend_dir)
    if configured_frontend is not None:
        install_frontend(app, configured_frontend)
    else:

        @app.get("/")
        async def root():
            return {
                "service": "ProcessMind API",
                "version": "1.0.0",
                "docs": "/docs",
            }

    return app


app = create_app()
