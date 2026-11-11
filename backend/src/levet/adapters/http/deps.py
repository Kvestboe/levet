from typing import Annotated

from fastapi import Depends, HTTPException, Request

from levet.adapters.http.auth import SESSION_COOKIE
from levet.bootstrap import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


ContainerDep = Annotated[Container, Depends(get_container)]


def require_session(request: Request, container: ContainerDep) -> None:
    if not container.sessions.is_valid(request.cookies.get(SESSION_COOKIE)):
        raise HTTPException(status_code=401, detail="Not logged in.")
