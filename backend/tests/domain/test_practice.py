from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from levet.domain import Attempt, Grade
from levet.domain.practice import Candidate, Reason, build_queue, score_topics
from levet.domain.scheduling import review

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
TODAY = NOW.date()
NO_DATES = {"STAT": None, "OS": None}


class World:
    """A small set of tasks with their attempts, to build queues from."""

    def __init__(self):
        self.candidates = []
        self.attempts = []
        self.states = {}
        self.names = {}

    def task(self, name, *topics, subject="STAT"):
        candidate = Candidate(
            task_id=uuid4(),
            subject_code=subject,
            topic_ids=frozenset(topics),
            order=(len(self.candidates),),
        )
        self.candidates.append(candidate)
        self.names[candidate.task_id] = name
        return candidate.task_id

    def attempt(self, task_id, grade, minutes_ago=0.0, days_ago=0.0):
        at = NOW - timedelta(minutes=minutes_ago, days=days_ago)
        self.attempts.append(Attempt(task_id=task_id, attempted_at=at, grade=grade))
        self.attempts.sort(key=lambda a: a.attempted_at)
        self.states[task_id] = review(self.states.get(task_id), task_id, grade, at)

    def queue(self, now=NOW, exam_dates=NO_DATES, topic_id=None):
        return build_queue(
            self.candidates, self.attempts, self.states, exam_dates, now, topic_id=topic_id
        )

    def order(self, **kwargs):
        return [self.names[item.task_id] for item in self.queue(**kwargs)]

    def reasons(self, **kwargs):
        return {self.names[item.task_id]: item.reason for item in self.queue(**kwargs)}


@pytest.fixture
def world():
    return World()


# --- the two sources ---------------------------------------------------------


def test_with_no_attempts_every_task_is_new_and_in_document_order(world):
    topic = uuid4()
    for name in ("1a", "1b", "2"):
        world.task(name, topic)
    assert world.order() == ["1a", "1b", "2"]
    assert set(world.reasons().values()) == {Reason.NEW}


def test_a_failed_task_that_is_due_again_goes_to_the_front(world):
    topic = uuid4()
    failed = world.task("failed", topic)
    for name in ("new 1", "new 2", "new 3"):
        world.task(name, topic)
    world.attempt(failed, Grade.AGAIN, minutes_ago=5)  # due again after one minute

    assert world.order()[0] == "failed"
    assert world.reasons()["failed"] is Reason.DUE


def test_a_failed_task_waits_until_it_is_due(world):
    topic = uuid4()
    failed = world.task("failed", topic)
    world.task("new", topic)
    world.attempt(failed, Grade.AGAIN)  # failed this very moment: due in a minute

    assert world.order() == ["new", "failed"]
    assert world.order(now=NOW + timedelta(minutes=2)) == ["failed", "new"]


def test_a_task_that_was_never_failed_does_not_count_as_due_again(world):
    topic = uuid4()
    passed = world.task("passed", topic)
    world.task("new", topic)
    world.attempt(passed, Grade.GOOD, days_ago=30)  # long overdue, but never failed

    assert world.reasons()["passed"] is Reason.WEAK
    assert world.order() == ["new", "passed"]


def test_a_task_failed_once_keeps_coming_back_when_due_even_after_a_success(world):
    topic = uuid4()
    task = world.task("once failed", topic)
    world.task("new", topic)
    world.attempt(task, Grade.AGAIN, days_ago=20)
    world.attempt(task, Grade.GOOD, days_ago=19.99)
    world.attempt(task, Grade.GOOD, days_ago=19.9)  # now under review, due after a day

    assert world.reasons()["once failed"] is Reason.DUE
    assert world.order()[0] == "once failed"


def test_due_tasks_come_most_overdue_first(world):
    topic = uuid4()
    recent = world.task("failed recently", topic)
    long_ago = world.task("failed long ago", topic)
    world.attempt(recent, Grade.AGAIN, minutes_ago=10)
    world.attempt(long_ago, Grade.AGAIN, days_ago=3)
    assert world.order() == ["failed long ago", "failed recently"]


def test_due_tasks_and_weak_topic_tasks_alternate(world):
    topic = uuid4()
    failed = [world.task(f"failed {n}", topic) for n in (1, 2, 3)]
    for n in (1, 2):
        world.task(f"new {n}", topic)
    for minutes, task in zip((30, 20, 10), failed, strict=True):
        world.attempt(task, Grade.AGAIN, minutes_ago=minutes)

    assert world.order() == ["failed 1", "new 1", "failed 2", "new 2", "failed 3"]


# --- weak topics -------------------------------------------------------------


def test_tasks_from_the_weakest_topic_come_first(world):
    strong, weak = uuid4(), uuid4()
    mastered = [world.task(f"strong {n}", strong) for n in (1, 2, 3)]
    struggled = [world.task(f"weak {n}", weak) for n in (1, 2, 3)]
    world.attempt(mastered[0], Grade.EASY, days_ago=1)
    world.attempt(struggled[0], Grade.HARD, days_ago=1)

    order = world.order()

    assert order[:2] == ["weak 2", "weak 3"]
    assert order.index("weak 1") < order.index("strong 1")


def test_an_untouched_topic_outranks_one_that_has_been_practised(world):
    practised, untouched = uuid4(), uuid4()
    done = world.task("practised 1", practised)
    world.task("practised 2", practised)
    world.task("untouched 1", untouched)
    world.attempt(done, Grade.GOOD, days_ago=1)

    assert world.order()[0] == "untouched 1"


def test_within_a_topic_never_attempted_tasks_come_before_attempted_ones(world):
    topic = uuid4()
    old = world.task("attempted long ago", topic)
    recent = world.task("attempted recently", topic)
    world.task("never attempted", topic)
    world.attempt(old, Grade.GOOD, days_ago=40)
    world.attempt(recent, Grade.GOOD, days_ago=20)

    assert world.order() == ["never attempted", "attempted long ago", "attempted recently"]
    assert world.reasons() == {
        "never attempted": Reason.NEW,
        "attempted long ago": Reason.WEAK,
        "attempted recently": Reason.WEAK,
    }


def test_a_task_in_several_topics_is_placed_by_its_weakest(world):
    strong, weak = uuid4(), uuid4()
    mastered = world.task("strong only", strong)
    world.task("strong and weak", strong, weak)
    world.task("strong only, new", strong)
    world.attempt(mastered, Grade.EASY, days_ago=1)

    queue = world.queue()

    assert world.names[queue[0].task_id] == "strong and weak"
    assert queue[0].topic_id == weak


def test_the_subject_with_the_closer_exam_comes_first(world):
    stats, os_topic = uuid4(), uuid4()
    world.task("statistics", stats, subject="STAT")
    world.task("operating systems", os_topic, subject="OS")

    soon_os = {"STAT": TODAY + timedelta(days=30), "OS": TODAY + timedelta(days=3)}
    soon_stat = {"STAT": TODAY + timedelta(days=3), "OS": TODAY + timedelta(days=30)}

    assert world.order(exam_dates=soon_os) == ["operating systems", "statistics"]
    assert world.order(exam_dates=soon_stat) == ["statistics", "operating systems"]


def test_tasks_done_and_not_yet_due_come_last(world):
    weak, strong = uuid4(), uuid4()
    done = world.task("done today", weak)
    struggling = world.task("weak, attempted", weak)
    world.task("strong, new", strong)
    world.attempt(struggling, Grade.HARD, days_ago=5)
    world.attempt(done, Grade.EASY)  # due again in several days

    assert world.order()[-1] == "done today"


def test_a_task_without_topics_is_still_queued_after_the_tagged_ones(world):
    topic = uuid4()
    world.task("untagged")
    world.task("tagged", topic)
    queue = world.queue()
    assert [world.names[item.task_id] for item in queue] == ["tagged", "untagged"]
    assert queue[1].topic_id is None


def test_the_queue_holds_every_task_exactly_once(world):
    topics = [uuid4() for _ in range(3)]
    tasks = [world.task(f"t{n}", topics[n % 3], topics[(n + 1) % 3]) for n in range(12)]
    for n, grade in enumerate([Grade.AGAIN, Grade.GOOD, Grade.EASY, Grade.HARD, Grade.AGAIN]):
        world.attempt(tasks[n], grade, days_ago=n + 1)
    assert sorted(world.order()) == sorted(world.names.values())


# --- one topic ---------------------------------------------------------------


def test_the_queue_can_be_limited_to_one_topic(world):
    wanted, other = uuid4(), uuid4()
    failed = world.task("wanted, failed", wanted)
    world.task("wanted, new", wanted)
    world.task("both", wanted, other)
    elsewhere = world.task("other, failed", other)
    world.attempt(failed, Grade.AGAIN, minutes_ago=5)
    world.attempt(elsewhere, Grade.AGAIN, minutes_ago=5)

    queue = world.queue(topic_id=wanted)

    assert [world.names[item.task_id] for item in queue] == [
        "wanted, failed",
        "wanted, new",
        "both",
    ]
    assert {item.topic_id for item in queue} == {wanted}


def test_an_unknown_topic_gives_an_empty_queue(world):
    world.task("task", uuid4())
    assert world.queue(topic_id=uuid4()) == []


# --- topic scores ------------------------------------------------------------


def test_topics_are_scored_from_their_tasks_and_attempts(world):
    topic, untouched = uuid4(), uuid4()
    first = world.task("1", topic)
    world.task("2", topic)
    world.task("3", untouched)
    world.attempt(first, Grade.GOOD)

    scores = score_topics(world.candidates, world.attempts, {"STAT": TODAY}, NOW)

    assert set(scores) == {topic, untouched}
    assert (scores[topic].task_count, scores[topic].attempted_count) == (2, 1)
    assert scores[topic].weakness.mastery == pytest.approx(0.8)
    assert scores[topic].weakness.coverage_gap == pytest.approx(0.5)
    assert scores[untouched].weakness.weakness == 1.0
    assert scores[untouched].attempted_count == 0
    # The exam is today: urgency is at its highest and priority equals weakness.
    assert scores[topic].urgency == pytest.approx(1.0)
    assert scores[topic].priority == pytest.approx(scores[topic].weakness.weakness)
    assert scores[topic].subject_code == "STAT"


def test_priority_is_weakness_scaled_by_how_close_the_exam_is(world):
    topic = uuid4()
    world.task("1", topic)
    near = score_topics(world.candidates, [], {"STAT": TODAY + timedelta(days=1)}, NOW)[topic]
    far = score_topics(world.candidates, [], {"STAT": TODAY + timedelta(days=60)}, NOW)[topic]
    undated = score_topics(world.candidates, [], {"STAT": None}, NOW)[topic]
    assert near.weakness == far.weakness
    assert near.priority > far.priority > 0
    assert undated.priority == pytest.approx(0.2)


# --- the acceptance criterion ------------------------------------------------


def test_after_logging_attempts_weak_topics_and_failed_tasks_rise_in_the_queue(world):
    """A practice history across three topics, then: what is first in the queue?"""
    regression, probability, estimation = uuid4(), uuid4(), uuid4()
    reg = [world.task(f"regression {n}", regression) for n in range(1, 5)]
    prob = [world.task(f"probability {n}", probability) for n in range(1, 5)]
    est = [world.task(f"estimation {n}", estimation) for n in range(1, 5)]
    exam = {"STAT": date(2026, 12, 1)}

    before = world.order(exam_dates=exam)
    assert before[:4] == ["regression 1", "regression 2", "regression 3", "regression 4"]

    # Regression goes well, probability badly, estimation is not touched.
    for task in reg:
        world.attempt(task, Grade.EASY, days_ago=2)
    world.attempt(prob[0], Grade.AGAIN, days_ago=1)
    world.attempt(prob[1], Grade.HARD, days_ago=1)
    world.attempt(prob[2], Grade.AGAIN, minutes_ago=30)

    order = world.order(exam_dates=exam)
    reasons = world.reasons(exam_dates=exam)

    # The failed tasks are due again and lead, alternating with untouched material.
    assert order[0] == "probability 1"
    assert order[2] == "probability 3"
    assert reasons["probability 1"] is reasons["probability 3"] is Reason.DUE
    assert order[1] == "estimation 1"
    assert reasons["estimation 1"] is Reason.NEW
    # The topic that went well has dropped to the back.
    assert order[-4:] == sorted(order[-4:])
    assert all(name.startswith("regression") for name in order[-4:])
    assert max(order.index(f"probability {n}") for n in range(1, 5)) < order.index("regression 1")

    scores = score_topics(world.candidates, world.attempts, exam, NOW)
    assert scores[estimation].priority > scores[probability].priority > scores[regression].priority
    assert est and scores[regression].weakness.mastery == pytest.approx(1.0)
