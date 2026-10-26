"""Приложение FastAPI: REST API (OpenAPI 3 — /api/docs, И-1) и веб-интерфейс АРМ."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text

from . import __version__, db
from .config import get_settings
from .errors import DomainError

STATIC = Path(__file__).resolve().parent / "static"


def _routers():
    from .api import (admin, applications, auth, dashboard, integration, methodology, nsi, reports)
    return [m.router for m in (auth, applications, methodology, nsi, reports, admin, integration, dashboard)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    s.ensure_dirs()
    app.state.scheduler = None
    if s.scheduler_enabled:
        from .scheduler import start
        app.state.scheduler = start()
    yield
    if app.state.scheduler is not None:
        app.state.scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="СППР «Кредитный скоринг» — API", version=__version__, lifespan=lifespan,
                  description="Поддержка принятия решений по оценке кредитоспособности физических лиц. "
                              "Сервис скоринга — отдельный процесс creditdss.scoring_service, метод POST /score.",
                  docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")
    if s.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in s.cors_origins.split(",")],
                           allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError):
        return JSONResponse(status_code=exc.status, content={"detail": exc.message, **exc.data})

    for r in _routers():
        app.include_router(r)

    @app.get("/api/health", tags=["Служебное"])
    def health():
        with db.engine().connect() as c:
            c.execute(text("SELECT 1"))
        return {"status": "ok", "version": __version__}

    if (STATIC / "index.html").exists():
        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path == "api" or path.startswith("api/"):
                raise HTTPException(404, "Не найдено")
            f = (STATIC / path).resolve()
            if path and f.is_file() and STATIC in f.parents:
                return FileResponse(f)
            return FileResponse(STATIC / "index.html")
    return app


app = create_app()
