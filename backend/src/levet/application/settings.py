"""Settings that are changed in the app rather than in the environment."""

from collections.abc import Callable
from dataclasses import dataclass, replace

from levet.application.errors import InvalidInput
from levet.application.ports import UnitOfWorkFactory
from levet.domain import Language
from levet.domain.language import DEFAULT_LANGUAGE
from levet.domain.scoring import DEFAULT_SCORING, ScoringConfig

_KEY = "app"
_WEIGHTS = ("mastery_weight", "staleness_weight", "coverage_weight")


@dataclass(frozen=True, slots=True)
class AppSettings:
    scoring: ScoringConfig = DEFAULT_SCORING
    # Which version to keep of an exam printed in several languages.
    preferred_language: Language = DEFAULT_LANGUAGE


SettingsProvider = Callable[[], AppSettings]


class SettingsService:
    """Reads and stores the settings. What has not been set falls back to ``defaults``."""

    def __init__(self, uow_factory: UnitOfWorkFactory, defaults: AppSettings | None = None) -> None:
        self._uow_factory = uow_factory
        self._defaults = defaults or AppSettings()

    def get(self) -> AppSettings:
        with self._uow_factory() as uow:
            stored = uow.settings.get(_KEY) or {}
        try:
            return self._build(stored)
        except InvalidInput:
            # Something unusable is stored, by hand or by an older version.
            return self._defaults

    def update(
        self,
        *,
        mastery_weight: float | None = None,
        staleness_weight: float | None = None,
        coverage_weight: float | None = None,
        preferred_language: str | None = None,
    ) -> AppSettings:
        """Change the settings given and keep the rest.

        Nothing is saved if the result would be invalid.
        """
        changes: dict[str, float | str | None] = {
            "mastery_weight": mastery_weight,
            "staleness_weight": staleness_weight,
            "coverage_weight": coverage_weight,
            "preferred_language": None if preferred_language is None else str(preferred_language),
        }
        with self._uow_factory() as uow:
            stored = dict(uow.settings.get(_KEY) or {})
            stored.update({name: value for name, value in changes.items() if value is not None})
            settings = self._build(stored)
            uow.settings.set(_KEY, stored)
            uow.commit()
        return settings

    def _build(self, stored: dict) -> AppSettings:
        try:
            weights = {name: float(stored[name]) for name in _WEIGHTS if name in stored}
            scoring = replace(self._defaults.scoring, **weights)
        except (TypeError, ValueError) as exc:
            raise InvalidInput(str(exc)) from exc

        language = stored.get("preferred_language")
        if language is None:
            return AppSettings(scoring, self._defaults.preferred_language)
        try:
            return AppSettings(scoring, Language(language))
        except ValueError as exc:
            choices = ", ".join(choice.value for choice in Language)
            raise InvalidInput(f"the language must be one of {choices}; got {language!r}") from exc
