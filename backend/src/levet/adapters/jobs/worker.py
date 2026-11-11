"""In-process background processing: one worker thread and an in-memory queue.

Exams are processed one at a time, which keeps memory use flat and is all a
single-user app needs. The queue does not survive a restart; exams caught
mid-processing are marked failed at the next start-up so they can be retried.
"""

import logging
import queue
import threading
from collections.abc import Callable
from uuid import UUID

from levet.application.ports import Progress

log = logging.getLogger(__name__)


class ThreadedJobQueue:
    def __init__(self, handler: Callable[[UUID], None]) -> None:
        self._handler = handler
        self._queue: queue.Queue[UUID | None] = queue.Queue()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._work, name="levet-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Stop after the job in progress. Jobs still queued are dropped."""
        if self._thread is None:
            return
        self._queue.put(None)
        self._thread.join(timeout)
        self._thread = None

    def enqueue(self, exam_id: UUID) -> None:
        self._queue.put(exam_id)

    def _work(self) -> None:
        while True:
            exam_id = self._queue.get()
            if exam_id is None:
                return
            try:
                self._handler(exam_id)
            except Exception:
                log.exception("job for exam %s crashed", exam_id)


class InMemoryProgress:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._progress: dict[UUID, Progress] = {}

    def report(self, exam_id: UUID, progress: Progress) -> None:
        with self._lock:
            self._progress[exam_id] = progress

    def get(self, exam_id: UUID) -> Progress | None:
        with self._lock:
            return self._progress.get(exam_id)

    def clear(self, exam_id: UUID) -> None:
        with self._lock:
            self._progress.pop(exam_id, None)
