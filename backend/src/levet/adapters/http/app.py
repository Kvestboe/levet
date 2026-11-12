from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from levet.adapters.http import routes_auth, routes_exams, routes_review, routes_subjects
from levet.adapters.http.deps import require_session
from levet.application.errors import ApplicationError, Conflict, InvalidInput, NotFound
from levet.bootstrap import Container

_STATUS_BY_ERROR: dict[type[ApplicationError], int] = {
    NotFound: 404,
    Conflict: 409,
    InvalidInput: 422,
}


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
    api.include_router(routes_auth.router)
    # Everything except logging in requires a valid session.
    protected = APIRouter(dependencies=[Depends(require_session)])
    protected.include_router(routes_subjects.router)
    protected.include_router(routes_exams.router)
    protected.include_router(routes_review.router)
    api.include_router(protected)
    app.include_router(api)

    @app.exception_handler(ApplicationError)
    async def application_error(request: Request, exc: ApplicationError) -> JSONResponse:
        status = _STATUS_BY_ERROR.get(type(exc), 400)
        return JSONResponse(status_code=status, content={"detail": _as_sentence(str(exc))})

    return app


def _as_sentence(message: str) -> str:
    """Error messages are shown to the user as they are, so make them read as sentences."""
    message = message.strip()
    if not message:
        return "Something went wrong."
    message = message[0].upper() + message[1:]
    return message if message[-1] in ".!?" else message + "."
