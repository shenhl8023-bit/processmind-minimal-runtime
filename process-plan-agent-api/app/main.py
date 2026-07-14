"""
ProcessMind 后端入口
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import documents, extract, generate, projects, settings
from app.services.route_rules_builtin_knowledge import preload_builtin_knowledge_cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: 创建数据库表
    await init_db()
    preload_builtin_knowledge_cache(force=True)
    yield
    # Shutdown


app = FastAPI(
    title="ProcessMind API",
    description="典型工艺规程智能体后端服务",
    version="1.0.0",
    lifespan=lifespan,
)

# 允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(extract.router)
app.include_router(generate.router)
app.include_router(projects.router)
app.include_router(settings.router)


@app.get("/")
async def root():
    return {
        "service": "ProcessMind API",
        "version": "1.0.0",
        "docs": "/docs"
    }
