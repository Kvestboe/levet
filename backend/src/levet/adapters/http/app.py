from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from levet.adapters.http import (
    routes_auth,
    routes_exams,
    routes_practice,
    routes_progress,
    routes_review,
    routes_subjects,
)
from levet.adapters.http.deps import require_session
from levet.application.errors import ApplicationError, Conflict, InvalidInput, NotFound
from levet.bootstrap import Container

_STATUS_BY_ERROR: dict[type[ApplicationError], int] = {
    NotFound: 404,
    Conflict: 409,
    InvalidInput: 422,
}

# Files with a content hash in their name never change; everything else
# (the page itself, the service worker, the manifest) must be checked each time.
_IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}
_REVALIDATE = {"Cache-Control": "no-cache"}
_MEDIA_TYPES = {".webmanifest": "application/manifest+json"}


def create_app(container: Container) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container.start()
        try:
            yield
        finally:
            container.stop()

    # The interactive API docs are off: the app is meant to sit on a public domain.
    app = FastAPI(title="levet", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.container = container

    api = APIRouter(prefix="/api")

    @api.get("/health")
    def health() -> dict[str, str]:
        """For container health checks. Says nothing about the data."""
        return {"status": "ok"}

    api.include_router(routes_auth.router)
    # Everything except logging in requires a valid session.
    protected = APIRouter(dependencies=[Depends(require_session)])
    protected.include_router(routes_subjects.router)
    protected.include_router(routes_exams.router)
    protected.include_router(routes_review.router)
    protected.include_router(routes_practice.router)
    protected.include_router(routes_progress.router)
    api.include_router(protected)
    app.include_router(api)

    @app.exception_handler(ApplicationError)
    async def application_error(request: Request, exc: ApplicationError) -> JSONResponse:
        status = _STATUS_BY_ERROR.get(type(exc), 400)
        return JSONResponse(status_code=status, content={"detail": _as_sentence(str(exc))})

    static_dir = container.settings.static_dir
    if static_dir is not None:
        _serve_frontend(app, static_dir)
    return app


def _serve_frontend(app: FastAPI, static_dir: Path) -> None:
    """Serve the built frontend: its files where they exist, and the app's page
    for every other path, so that reloading /practice/topics works."""
    root = static_dir.resolve()
    index = root / "index.html"
    if not index.is_file():
        raise RuntimeError(f"LEVET_STATIC_DIR has no index.html: {static_dir}")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found.")
        file = (root / path).resolve()
        if path and file.is_file() and file.is_relative_to(root):
            return FileResponse(
                file,
                media_type=_MEDIA_TYPES.get(file.suffix),
                headers=_IMMUTABLE if path.startswith("assets/") else _REVALIDATE,
            )
        return FileResponse(index, headers=_REVALIDATE)


def _as_sentence(message: str) -> str:
    """Error messages are shown to the user as they are, so make them read as sentences."""
    message = message.strip()
    if not message:
        return "Something went wrong."
    message = message[0].upper() + message[1:]
    return message if message[-1] in ".!?" else message + "."
