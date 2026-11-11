import stat
import threading
from uuid import uuid4

from levet.adapters.http.auth import LoginThrottle, SessionManager, load_or_create_secret_key
from levet.adapters.jobs.worker import InMemoryProgress, ThreadedJobQueue
from levet.application.ports import Progress

# --- sessions ----------------------------------------------------------------


def manager(password="hunter2", secret="secret-key", max_age=3600):
    return SessionManager(password, secret, max_age_seconds=max_age)


def test_only_the_exact_password_matches():
    sessions = manager()
    assert sessions.password_matches("hunter2")
    assert not sessions.password_matches("hunter")
    assert not sessions.password_matches("")
    assert not sessions.password_matches("hunter2 ")


def test_issued_token_is_valid_and_tampered_or_foreign_tokens_are_not():
    sessions = manager()
    token = sessions.issue()
    assert sessions.is_valid(token)
    assert not sessions.is_valid(None)
    assert not sessions.is_valid("")
    assert not sessions.is_valid(token[:-2] + "xx")
    assert not sessions.is_valid("garbage")


def test_token_signed_with_another_secret_is_rejected():
    assert not manager(secret="other-key").is_valid(manager().issue())


def test_changing_the_password_invalidates_existing_sessions():
    assert not manager(password="new-password").is_valid(manager().issue())


def test_expired_token_is_rejected():
    assert not manager(max_age=-1).is_valid(manager().issue())


# --- throttle ----------------------------------------------------------------


class FakeTime:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_throttle_allows_a_few_wrong_passwords_then_locks_for_a_while():
    time = FakeTime()
    throttle = LoginThrottle(max_failures=3, lockout_seconds=60, monotonic=time)

    for _ in range(3):
        assert throttle.retry_after() == 0
        throttle.record_failure()
    assert throttle.retry_after() == 60

    time.now += 45
    assert throttle.retry_after() == 15
    time.now += 15
    assert throttle.retry_after() == 0


def test_after_the_lock_expires_a_single_wrong_password_locks_again():
    time = FakeTime()
    throttle = LoginThrottle(max_failures=3, lockout_seconds=60, monotonic=time)
    for _ in range(3):
        throttle.record_failure()
    time.now += 61

    throttle.record_failure()
    assert throttle.retry_after() == 60


def test_a_successful_login_resets_the_throttle():
    throttle = LoginThrottle(max_failures=3, lockout_seconds=60, monotonic=FakeTime())
    for _ in range(2):
        throttle.record_failure()
    throttle.record_success()
    for _ in range(2):
        throttle.record_failure()
    assert throttle.retry_after() == 0


# --- secret key --------------------------------------------------------------


def test_secret_key_is_created_once_then_reused_and_only_readable_by_the_owner(tmp_path):
    path = tmp_path / "data" / "secret_key"
    key = load_or_create_secret_key(path)
    assert len(key) >= 32
    assert load_or_create_secret_key(path) == key
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


# --- job queue ---------------------------------------------------------------


def test_jobs_run_in_the_background_one_at_a_time_in_order():
    handled = []
    done = threading.Event()
    ids = [uuid4() for _ in range(5)]

    def handler(exam_id):
        handled.append((exam_id, threading.current_thread().name))
        if len(handled) == len(ids):
            done.set()

    jobs = ThreadedJobQueue(handler)
    jobs.start()
    try:
        for exam_id in ids:
            jobs.enqueue(exam_id)
        assert done.wait(5)
    finally:
        jobs.stop()

    assert [exam_id for exam_id, _ in handled] == ids
    assert {thread for _, thread in handled} == {"levet-worker"}


def test_a_crashing_job_does_not_stop_the_worker():
    handled = []
    done = threading.Event()
    bad, good = uuid4(), uuid4()

    def handler(exam_id):
        if exam_id == bad:
            raise RuntimeError("boom")
        handled.append(exam_id)
        done.set()

    jobs = ThreadedJobQueue(handler)
    jobs.start()
    try:
        jobs.enqueue(bad)
        jobs.enqueue(good)
        assert done.wait(5)
    finally:
        jobs.stop()
    assert handled == [good]


def test_jobs_enqueued_before_start_are_kept_and_stop_is_safe_to_repeat():
    handled = []
    done = threading.Event()
    exam_id = uuid4()
    jobs = ThreadedJobQueue(lambda job: (handled.append(job), done.set()))

    jobs.enqueue(exam_id)
    jobs.start()
    assert done.wait(5)
    jobs.stop()
    jobs.stop()
    assert handled == [exam_id]


# --- progress ----------------------------------------------------------------


def test_progress_keeps_the_latest_report_per_exam_until_cleared():
    progress = InMemoryProgress()
    a, b = uuid4(), uuid4()
    progress.report(a, Progress("rendering", 1, 4))
    progress.report(a, Progress("rendering", 2, 4))
    progress.report(b, Progress("rendering", 0, 9))

    assert progress.get(a) == Progress("rendering", 2, 4)
    progress.clear(a)
    progress.clear(a)
    assert progress.get(a) is None
    assert progress.get(b) == Progress("rendering", 0, 9)
