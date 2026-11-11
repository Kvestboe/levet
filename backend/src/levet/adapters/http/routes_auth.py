import math

from fastapi import APIRouter, HTTPException, Request, Response

from levet.adapters.http.auth import SESSION_COOKIE
from levet.adapters.http.deps import ContainerDep
from levet.adapters.http.schemas import LoginIn, SessionOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", status_code=204)
def login(body: LoginIn, request: Request, response: Response, container: ContainerDep) -> None:
    wait = container.throttle.retry_after()
    if wait > 0:
        raise HTTPException(
            status_code=429,
            detail="Too many wrong passwords. Wait a moment and try again.",
            headers={"Retry-After": str(math.ceil(wait))},
        )
    if not container.sessions.password_matches(body.password):
        container.throttle.record_failure()
        raise HTTPException(status_code=401, detail="Wrong password.")

    container.throttle.record_success()
    response.set_cookie(
        SESSION_COOKIE,
        container.sessions.issue(),
        max_age=container.sessions.max_age_seconds,
        httponly=True,
        samesite="lax",
        # Marked Secure whenever the request came in over HTTPS (directly or
        # through a reverse proxy that uvicorn is told to trust).
        secure=request.url.scheme == "https",
        path="/",
    )


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/session")
def session(request: Request, container: ContainerDep) -> SessionOut:
    return SessionOut(
        authenticated=container.sessions.is_valid(request.cookies.get(SESSION_COOKIE))
    )
