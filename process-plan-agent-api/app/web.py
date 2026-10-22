"""Production frontend hosting helpers."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class SPAStaticFiles(StaticFiles):
    """Serve Vite assets and fall back to the SPA entrypoint for history URLs."""

    async def get_response(self, path: str, scope: Scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404 and scope["method"] in {"GET", "HEAD"}:
                return await super().get_response("index.html", scope)
            raise


def install_frontend(app: FastAPI, frontend_dir: Path) -> None:
    """Mount a built frontend after API routes have been registered."""

    directory = Path(frontend_dir).expanduser().resolve()
    if not directory.is_dir():
        raise RuntimeError("Configured frontend directory does not exist: %s" % directory)
    app.mount("/", SPAStaticFiles(directory=str(directory), html=True), name="frontend")
