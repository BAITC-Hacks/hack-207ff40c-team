"""Loopback web host for the existing station API and a local React build."""
import ipaddress
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.staticfiles import StaticFiles

from .config import Settings
from .main import create_app


class StripPrefix:
    """Apply the same API path rewrite as the deployed Caddy proxy."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            scope = dict(scope)
            prefix = scope.get("root_path", "")
            if prefix and scope["path"].startswith(prefix):
                scope["path"] = scope["path"][len(prefix):] or "/"
                scope["raw_path"] = scope["path"].encode("utf-8")
            scope["root_path"] = ""
        await self.app(scope, receive, send)


def check_frontend(directory):
    directory = Path(directory).resolve()
    if not (directory / "index.html").is_file():
        raise ValueError("Build the local frontend first; dist/index.html is missing")
    try:
        marker = json.loads((directory / "meeting-build.json").read_text())
    except (OSError, ValueError) as exc:
        raise ValueError("Frontend build metadata is missing; rebuild with both local flags") from exc
    if marker != {"version": 1, "station": True, "local": True}:
        raise ValueError("Local hosting requires VITE_MEETING_STATION=true VITE_MEETING_LOCAL=true")
    return directory


def create_local_app(settings=None, frontend=None, **station_options):
    settings = settings or Settings.from_env()
    host = "127.0.0.1" if settings.bind_host == "localhost" else settings.bind_host
    if not ipaddress.ip_address(host).is_loopback:
        raise ValueError("The standalone web host must bind to loopback")
    directory = check_frontend(frontend)
    station = create_app(settings, **station_options)
    station.router.redirect_slashes = False

    @asynccontextmanager
    async def lifespan(app):
        # Starlette does not run mounted applications' lifespan automatically.
        async with station.router.lifespan_context(station):
            yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])
    app.mount("/api/meeting-worker", StripPrefix(station))

    @app.get("/")
    @app.get("/meeting-intelligence")
    def index():
        return FileResponse(directory / "index.html", headers={"Cache-Control": "no-store"})

    app.mount("/", StaticFiles(directory=directory), name="frontend")
    app.state.station = station
    return app
