from types import TracebackType
from typing import Self

from sqlalchemy.orm import Session, sessionmaker

from levet.adapters.db.repositories import (
    SqlAttemptRepository,
    SqlExamRepository,
    SqlReviewStateRepository,
    SqlSettingsRepository,
    SqlSubjectRepository,
    SqlTaskRepository,
    SqlTopicRepository,
)


class SqlAlchemyUnitOfWork:
    """One session and transaction. Leaving the block without ``commit`` rolls back."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def __enter__(self) -> Self:
        self._session = self._session_factory()
        self.subjects = SqlSubjectRepository(self._session)
        self.topics = SqlTopicRepository(self._session)
        self.exams = SqlExamRepository(self._session)
        self.tasks = SqlTaskRepository(self._session)
        self.attempts = SqlAttemptRepository(self._session)
        self.review_states = SqlReviewStateRepository(self._session)
        self.settings = SqlSettingsRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._session.rollback()
        self._session.close()

    def commit(self) -> None:
        self._session.commit()
