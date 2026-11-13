from datetime import UTC, tzinfo
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from levet.adapters.http.deps import ContainerDep
from levet.adapters.http.schemas import DashboardOut, SettingsIn, SettingsOut, TopicDetailOut

router = APIRouter(tags=["progress"])


def _zone(name: str | None) -> tzinfo:
    """The user's time zone, as the browser names it; UTC if it is missing or unknown."""
    if not name:
        return UTC
    try:
        return ZoneInfo(name)
    except (KeyError, ValueError, OSError):
        return UTC


@router.get("/dashboard")
def dashboard(container: ContainerDep, tz: str | None = None) -> DashboardOut:
    """The overview. ``tz`` (e.g. Europe/Oslo) decides where one day ends and the next begins."""
    return DashboardOut.of(container.progress.dashboard(_zone(tz)))


@router.get("/topics/{topic_id}")
def topic(topic_id: UUID, container: ContainerDep, tz: str | None = None) -> TopicDetailOut:
    return TopicDetailOut.of(container.progress.topic(topic_id, _zone(tz)))


@router.get("/settings")
def get_settings(container: ContainerDep) -> SettingsOut:
    return SettingsOut.of(container.preferences.get())


@router.put("/settings")
def update_settings(body: SettingsIn, container: ContainerDep) -> SettingsOut:
    return SettingsOut.of(
        container.preferences.update(
            mastery_weight=body.mastery_weight,
            staleness_weight=body.staleness_weight,
            coverage_weight=body.coverage_weight,
            preferred_language=body.preferred_language,
        )
    )
