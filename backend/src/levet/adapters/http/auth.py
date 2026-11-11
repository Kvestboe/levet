"""Single-user password login with a signed session cookie."""

import hashlib
import hmac
import os
import secrets
import threading
import time
from collections.abc import Callable
from pathlib import Path

from itsdangerous import BadSignature, URLSafeTimedSerializer

SESSION_COOKIE = "levet_session"


class SessionManager:
    def __init__(self, password: str, secret_key: str, max_age_seconds: int) -> None:
        self._password = password.encode()
        self._serializer = URLSafeTimedSerializer(secret_key, salt="levet.session")
        self.max_age_seconds = max_age_seconds
        # Sessions carry a fingerprint of the password, so changing the password
        # invalidates every session issued under the old one.
        self._fingerprint = hmac.new(
            secret_key.encode(), self._password, hashlib.sha256
        ).hexdigest()

    def password_matches(self, candidate: str) -> bool:
        return hmac.compare_digest(candidate.encode(), self._password)

    def issue(self) -> str:
        return self._serializer.dumps(self._fingerprint)

    def is_valid(self, token: str | None) -> bool:
        if not token:
            return False
        try:
            value = self._serializer.loads(token, max_age=self.max_age_seconds)
        except BadSignature:  # also covers an expired signature
            return False
        return isinstance(value, str) and hmac.compare_digest(value, self._fingerprint)


class LoginThrottle:
    """Slows down password guessing.

    After ``max_failures`` wrong passwords in a row, further attempts are
    refused until ``lockout_seconds`` have passed since the last wrong one.
    The count is global rather than per client address: there is one user, and
    an address is easy to fake behind a reverse proxy.
    """

    def __init__(
        self,
        max_failures: int = 5,
        lockout_seconds: float = 60.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_failures = max_failures
        self._lockout_seconds = lockout_seconds
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._failures = 0
        self._last_failure = 0.0

    def retry_after(self) -> float:
        """Seconds until the next attempt is allowed; 0 if one is allowed now."""
        with self._lock:
            if self._failures < self._max_failures:
                return 0.0
            remaining = self._last_failure + self._lockout_seconds - self._monotonic()
            return max(0.0, remaining)

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            self._last_failure = self._monotonic()

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0


def load_or_create_secret_key(path: Path) -> str:
    """The key that signs session cookies, created on first use and then kept."""
    if path.is_file():
        key = path.read_text().strip()
        if key:
            return key
    key = secrets.token_urlsafe(48)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as file:
        file.write(key)
    return key
