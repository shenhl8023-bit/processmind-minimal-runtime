"""Production frontend hosting helpers."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from app.core.compat import run_in_thread
from app.core.product_profile import get_product_profile


class SPAStaticFiles(StaticFiles):
    """Serve Vite assets and fall back to the SPA entrypoint for history URLs."""

    async def get_response(self, path: str, scope: Scope):
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404 and scope["method"] in {"GET", "HEAD"}:
                requested_path = path.replace("\\", "/").strip("/").lower()
                is_api_path = requested_path == "api" or requested_path.startswith("api/")
                is_asset_path = requested_path == "assets" or requested_path.startswith("assets/")
                accepts_html = any(
                    item.split(";", 1)[0].strip().lower()
                    in {"text/html", "application/xhtml+xml"}
                    for item in Headers(scope=scope).get("accept", "").split(",")
                )
                if not is_api_path and not is_asset_path and not Path(path).suffix and accepts_html:
                    response = await super().get_response("index.html", scope)
                else:
                    raise
            else:
                raise

        if isinstance(response, FileResponse) and Path(response.path).resolve() == (Path(self.directory) / "index.html").resolve():
            # Publish the explicit delivery edition with the entrypoint itself,
            # so a full installation never waits for a separate status request.
            content = await run_in_thread(Path(response.path).read_text, encoding="utf-8")
            marker = '<meta name="processmind-edition" content="full" />'
            content = content.replace(marker, '<meta name="processmind-edition" content="%s" />' % get_product_profile().edition)
            return HTMLResponse(content, headers={"Cache-Control": "no-store"})
        return response


def install_frontend(app: FastAPI, frontend_dir: Path) -> None:
    """Mount a built frontend after API routes have been registered."""

    directory = Path(frontend_dir).expanduser().resolve()
    if not directory.is_dir():
        raise RuntimeError("Configured frontend directory does not exist: %s" % directory)
    app.mount("/", SPAStaticFiles(directory=str(directory), html=True), name="frontend")
