import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from levet.domain.language import DEFAULT_LANGUAGE, Language


class ConfigError(Exception):
    """The environment does not describe a runnable configuration."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime configuration, read from environment variables.

    LEVET_PASSWORD        required  the single user's login password
    LEVET_DATA_DIR        ./data    where the database and all files live
    LEVET_SECRET_KEY      (auto)    signs session cookies; generated and kept in
                                    the data directory when not set
    LEVET_RENDER_DPI      150       resolution of rendered page images
    LEVET_MAX_UPLOAD_MB   50        largest accepted PDF
    LEVET_SESSION_DAYS    30        how long a login lasts
    LEVET_LANGUAGE        nb        which version to keep of an exam printed in
                                    several languages: nb, nn or en
    """

    password: str
    data_dir: Path = Path("data")
    secret_key: str | None = None
    render_dpi: int = 150
    max_upload_bytes: int = 50 * 1024 * 1024
    session_days: int = 30
    preferred_language: Language = DEFAULT_LANGUAGE

    def __post_init__(self) -> None:
        if not self.password:
            raise ConfigError("LEVET_PASSWORD must be set to a non-empty password")
        if self.render_dpi < 36:
            raise ConfigError("LEVET_RENDER_DPI is too low to produce readable pages")
        if self.max_upload_bytes <= 0:
            raise ConfigError("LEVET_MAX_UPLOAD_MB must be positive")
        if self.session_days <= 0:
            raise ConfigError("LEVET_SESSION_DAYS must be positive")

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Self:
        return cls(
            password=env.get("LEVET_PASSWORD", ""),
            data_dir=Path(env.get("LEVET_DATA_DIR") or "data"),
            secret_key=env.get("LEVET_SECRET_KEY") or None,
            render_dpi=_int(env, "LEVET_RENDER_DPI", 150),
            max_upload_bytes=_int(env, "LEVET_MAX_UPLOAD_MB", 50) * 1024 * 1024,
            session_days=_int(env, "LEVET_SESSION_DAYS", 30),
            preferred_language=_language(env.get("LEVET_LANGUAGE")),
        )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "levet.db"

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"

    @property
    def secret_key_path(self) -> Path:
        return self.data_dir / "secret_key"


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a whole number, got {raw!r}") from exc


def _language(raw: str | None) -> Language:
    if raw is None or raw.strip() == "":
        return DEFAULT_LANGUAGE
    try:
        return Language(raw.strip().lower())
    except ValueError as exc:
        choices = ", ".join(language.value for language in Language)
        raise ConfigError(f"LEVET_LANGUAGE must be one of {choices}; got {raw!r}") from exc
