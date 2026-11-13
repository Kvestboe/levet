"""End-to-end tests of the HTTP API: real database, file store, renderer and worker."""

import time

import pytest
from fastapi.testclient import TestClient

from levet.adapters.http.app import create_app
from levet.adapters.http.auth import SESSION_COOKIE
from levet.bootstrap import build_container
from levet.config import Settings

PASSWORD = "correct horse battery staple"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
BROKEN_PDF = b"%PDF-1.7\nthis only looks like a PDF"


@pytest.fixture
def settings(tmp_path):
    return Settings(password=PASSWORD, data_dir=tmp_path / "data", max_upload_bytes=1024 * 1024)


@pytest.fixture
def anonymous(settings):
    with TestClient(create_app(build_container(settings))) as client:
        yield client


@pytest.fixture
def client(anonymous):
    assert anonymous.post("/api/auth/login", json={"password": PASSWORD}).status_code == 204
    return anonymous


@pytest.fixture
def subject(client):
    response = client.post(
        "/api/subjects",
        json={"code": "idatt2202", "name": "Operativsystemer", "exam_date": "2026-12-01"},
    )
    assert response.status_code == 201
    return response.json()


def upload(client, pdf, solution=None, label="Høst 2023", subject_code="IDATT2202"):
    files = {"pdf": ("exam.pdf", pdf, "application/pdf")}
    if solution is not None:
        files["solution_pdf"] = ("solution.pdf", solution, "application/pdf")
    return client.post(
        "/api/exams", data={"subject_code": subject_code, "label": label}, files=files
    )


def wait_until_processed(client, exam_id, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        exam = client.get(f"/api/exams/{exam_id}").json()
        if exam["status"] != "processing":
            return exam
        time.sleep(0.02)
    raise AssertionError("exam was still processing after the timeout")


# --- authentication ----------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/subjects"),
        ("POST", "/api/subjects"),
        ("PUT", "/api/subjects/IDATT2202"),
        ("DELETE", "/api/subjects/IDATT2202"),
        ("GET", "/api/exams"),
        ("POST", "/api/exams"),
        ("GET", "/api/exams/00000000-0000-0000-0000-000000000000"),
        ("POST", "/api/exams/00000000-0000-0000-0000-000000000000/retry"),
        ("GET", "/api/exams/00000000-0000-0000-0000-000000000000/pages/exam/1"),
    ],
)
def test_every_data_endpoint_requires_a_session(anonymous, method, path):
    assert anonymous.request(method, path).status_code == 401


def test_wrong_password_is_rejected_and_sets_no_cookie(anonymous):
    response = anonymous.post("/api/auth/login", json={"password": "guess"})
    assert response.status_code == 401
    assert SESSION_COOKIE not in response.cookies
    assert anonymous.get("/api/auth/session").json() == {"authenticated": False}


def test_login_sets_an_http_only_cookie_that_opens_the_api(anonymous):
    response = anonymous.post("/api/auth/login", json={"password": PASSWORD})
    assert response.status_code == 204
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "secure" not in cookie  # plain-HTTP request
    assert anonymous.get("/api/auth/session").json() == {"authenticated": True}
    assert anonymous.get("/api/subjects").status_code == 200


def test_cookie_is_marked_secure_when_the_request_came_over_https(settings):
    app = create_app(build_container(settings))
    with TestClient(app, base_url="https://levet.example") as https:
        response = https.post("/api/auth/login", json={"password": PASSWORD})
    assert "secure" in response.headers["set-cookie"].lower()


def test_forged_cookie_is_rejected(anonymous):
    anonymous.cookies.set(SESSION_COOKIE, "forged")
    assert anonymous.get("/api/subjects").status_code == 401


def test_logout_ends_the_session(client):
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/subjects").status_code == 401


def test_repeated_wrong_passwords_are_throttled_even_for_the_right_one(anonymous):
    for _ in range(5):
        assert anonymous.post("/api/auth/login", json={"password": "guess"}).status_code == 401
    locked = anonymous.post("/api/auth/login", json={"password": PASSWORD})
    assert locked.status_code == 429
    assert int(locked.headers["retry-after"]) > 0


def test_api_documentation_is_not_exposed(anonymous):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert anonymous.get(path).status_code == 404


# --- subjects ----------------------------------------------------------------


def test_subject_can_be_created_listed_updated_and_deleted(client, subject):
    assert subject == {"code": "IDATT2202", "name": "Operativsystemer", "exam_date": "2026-12-01"}
    assert client.get("/api/subjects").json() == [subject]

    updated = client.put(
        "/api/subjects/idatt2202", json={"name": "Operating systems", "exam_date": None}
    )
    assert updated.status_code == 200
    assert updated.json() == {"code": "IDATT2202", "name": "Operating systems", "exam_date": None}

    assert client.delete("/api/subjects/IDATT2202").status_code == 204
    assert client.get("/api/subjects").json() == []


def test_subject_errors_map_to_http_statuses(client, subject):
    duplicate = client.post("/api/subjects", json={"code": "IDATT2202", "name": "Again"})
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.json()["detail"]

    assert client.post("/api/subjects", json={"code": " ", "name": "x"}).status_code == 422
    assert client.post("/api/subjects", json={"code": "X", "exam_date": "soon"}).status_code == 422
    assert client.put("/api/subjects/NOPE", json={"name": "x"}).status_code == 404
    assert client.delete("/api/subjects/NOPE").status_code == 404


# --- exams -------------------------------------------------------------------


def test_uploaded_exam_is_rendered_in_the_background_and_its_pages_can_be_fetched(
    client, subject, make_pdf
):
    response = upload(
        client,
        make_pdf("Oppgave 1", "Oppgave 2", "Oppgave 3"),
        solution=make_pdf("Løsning 1", "Løsning 2"),
    )
    assert response.status_code == 202
    exam = response.json()
    assert exam["status"] == "processing"
    assert exam["subject_code"] == "IDATT2202"
    assert exam["label"] == "Høst 2023"
    assert exam["has_solution"] is True

    processed = wait_until_processed(client, exam["id"])
    assert processed["status"] == "needs_review"
    assert processed["error"] is None
    assert processed["progress"] is None
    assert (processed["page_count"], processed["solution_page_count"]) == (3, 2)
    assert [e["id"] for e in client.get("/api/exams").json()] == [exam["id"]]

    pages = [client.get(f"/api/exams/{exam['id']}/pages/exam/{n}") for n in (1, 2, 3)]
    for page in pages:
        assert page.status_code == 200
        assert page.headers["content-type"] == "image/png"
        assert page.content.startswith(PNG_SIGNATURE)
    assert len({page.content for page in pages}) == 3

    assert client.get(f"/api/exams/{exam['id']}/pages/solution/2").status_code == 200
    assert client.get(f"/api/exams/{exam['id']}/pages/solution/3").status_code == 404
    assert client.get(f"/api/exams/{exam['id']}/pages/exam/4").status_code == 404
    assert client.get(f"/api/exams/{exam['id']}/pages/cover/1").status_code == 422


def test_exams_can_be_filtered_by_subject(client, subject, make_pdf):
    client.post("/api/subjects", json={"code": "TDT4100", "name": "OOP"})
    first = upload(client, make_pdf()).json()
    second = upload(client, make_pdf(), subject_code="TDT4100").json()
    assert [e["id"] for e in client.get("/api/exams", params={"subject": "tdt4100"}).json()] == [
        second["id"]
    ]
    assert {e["id"] for e in client.get("/api/exams").json()} == {first["id"], second["id"]}


def test_exam_that_cannot_be_rendered_fails_visibly_and_can_be_retried(client, subject):
    exam = upload(client, BROKEN_PDF).json()

    failed = wait_until_processed(client, exam["id"])
    assert failed["status"] == "failed"
    assert failed["error"] == "Exam PDF: the file could not be read as a PDF"
    assert failed["page_count"] is None

    retried = client.post(f"/api/exams/{exam['id']}/retry")
    assert retried.status_code == 202
    assert retried.json()["status"] == "processing"
    assert wait_until_processed(client, exam["id"])["status"] == "failed"


def test_retry_is_refused_unless_the_exam_failed(client, subject, make_pdf):
    exam = upload(client, make_pdf()).json()
    wait_until_processed(client, exam["id"])
    assert client.post(f"/api/exams/{exam['id']}/retry").status_code == 409
    assert client.post("/api/exams/00000000-0000-0000-0000-000000000000/retry").status_code == 404


def test_invalid_uploads_are_rejected_without_creating_an_exam(client, subject, make_pdf):
    pdf = make_pdf()
    assert upload(client, b"just some text").status_code == 422
    assert upload(client, pdf, solution=b"<html></html>").status_code == 422
    assert upload(client, pdf, subject_code="NOPE").status_code == 404
    assert upload(client, pdf, label=" ").status_code == 422
    missing_file = client.post(
        "/api/exams", data={"subject_code": "IDATT2202", "label": "Høst 2023"}
    )
    assert missing_file.status_code == 422
    assert client.get("/api/exams").json() == []

    assert upload(client, pdf).status_code == 202
    assert upload(client, pdf).status_code == 409


def test_oversized_upload_is_rejected(client, subject):
    too_big = b"%PDF-1.7\n" + b"0" * (1024 * 1024)
    response = upload(client, too_big)
    assert response.status_code == 413
    assert "1 MB" in response.json()["detail"]
    assert client.get("/api/exams").json() == []


def test_upload_far_over_the_limit_is_refused_from_its_declared_size(client, subject):
    response = upload(client, b"%PDF-1.7\n" + b"0" * (3 * 1024 * 1024))
    assert response.status_code == 413


def test_an_empty_solution_field_means_no_solution(client, subject, make_pdf):
    exam = upload(client, make_pdf(), solution=b"").json()
    assert exam["has_solution"] is False


def test_unknown_exam_and_malformed_id(client):
    assert client.get("/api/exams/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get("/api/exams/not-a-uuid").status_code == 422


# --- restart -----------------------------------------------------------------


def test_data_survives_a_restart_and_interrupted_exams_become_retryable(settings, make_pdf):
    first = build_container(settings)
    # Not started: the worker never runs, as if the server died right after the upload.
    first.subjects.create("IDATT2202", "Operativsystemer")
    exam = first.exams.upload("IDATT2202", "Høst 2023", make_pdf("a", "b"))
    first.engine.dispose()

    with TestClient(create_app(build_container(settings))) as restarted:
        restarted.post("/api/auth/login", json={"password": PASSWORD})
        assert [s["code"] for s in restarted.get("/api/subjects").json()] == ["IDATT2202"]

        interrupted = restarted.get(f"/api/exams/{exam.id}").json()
        assert interrupted["status"] == "failed"
        assert "interrupted" in interrupted["error"]

        assert restarted.post(f"/api/exams/{exam.id}/retry").status_code == 202
        recovered = wait_until_processed(restarted, exam.id)
        assert recovered["status"] == "needs_review"
        assert recovered["page_count"] == 2


def test_sessions_survive_a_restart_because_the_signing_key_is_kept(settings):
    with TestClient(create_app(build_container(settings))) as before:
        before.post("/api/auth/login", json={"password": PASSWORD})
        cookie = before.cookies.get(SESSION_COOKIE)

    with TestClient(create_app(build_container(settings))) as after:
        after.cookies.set(SESSION_COOKIE, cookie)
        assert after.get("/api/subjects").status_code == 200


# --- extraction and review ---------------------------------------------------


@pytest.fixture
def reviewed_exam(client, subject, exam_pdf, solution_pdf):
    """An uploaded exam with a solution, processed and waiting for review."""
    exam = upload(client, exam_pdf, solution=solution_pdf).json()
    processed = wait_until_processed(client, exam["id"])
    assert processed["status"] == "needs_review", processed["error"]
    return processed


def tasks_of(client, exam):
    response = client.get(f"/api/exams/{exam['id']}/tasks")
    assert response.status_code == 200
    return response.json()


def task(client, exam, number):
    return next(t for t in tasks_of(client, exam)["tasks"] if t["number"] == number)


def test_uploaded_exam_is_split_into_tasks_with_images_solutions_and_topics(client, reviewed_exam):
    body = tasks_of(client, reviewed_exam)
    tasks = body["tasks"]

    # Each Oppgave is one task, its parts a) and b) included.
    assert [(t["number"], t["title"], t["points"]) for t in tasks] == [
        ("1", "Normalfordeling", 2),
        ("2", "Hypotesetest", 3),
    ]
    assert [t["parent_id"] for t in tasks] == [None, None]
    assert [t["position"] for t in tasks] == [0, 1]
    assert sorted(t["name"] for t in body["topics"]) == ["Hypotesetest", "Normalfordeling"]
    assert [[topic["name"] for topic in t["topics"]] for t in tasks] == [
        ["Normalfordeling"],
        ["Hypotesetest"],
    ]

    # Task 1 runs over a page break: two images, one region each.
    first = tasks[0]
    assert [region["page"] for region in first["regions"]] == [2, 3]
    assert len(first["images"]) == 2
    assert all(len(t["images"]) == len(t["regions"]) for t in tasks)
    assert all(len(t["solution_images"]) == 1 for t in tasks)
    assert "Standardiserer" in first["solution_text"]
    assert "Var(2X) = 4 Var(X) = 8." in first["solution_text"]

    for url in (*first["images"], *first["solution_images"]):
        image = client.get(url)
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"
        assert image.content.startswith(PNG_SIGNATURE)
        assert "immutable" in image.headers["cache-control"]


def test_task_images_need_a_session_and_a_real_name(client, anonymous, reviewed_exam):
    url = task(client, reviewed_exam, "1")["images"][0]
    exam_id = reviewed_exam["id"]
    assert client.get(f"/api/exams/{exam_id}/task-images/{'0' * 32}.png").status_code == 404
    assert client.get(f"/api/exams/{exam_id}/task-images/exam.pdf").status_code == 404
    client.post("/api/auth/logout")
    assert anonymous.get(url).status_code == 401
    assert anonymous.get(f"/api/exams/{exam_id}/tasks").status_code == 401


def test_a_task_can_be_relabelled_retitled_and_retagged(client, reviewed_exam):
    first = task(client, reviewed_exam, "1")

    response = client.patch(
        f"/api/tasks/{first['id']}",
        json={"number": "1x", "title": "Normalfordelingen", "topics": ["Fordelinger", "Varians"]},
    )
    assert response.status_code == 204

    changed = task(client, reviewed_exam, "1x")
    assert changed["title"] == "Normalfordelingen"
    assert changed["points"] == 2  # not mentioned, so kept
    assert [topic["name"] for topic in changed["topics"]] == ["Fordelinger", "Varians"]
    # "Normalfordeling" is no longer used by any task and is gone.
    names = [t["name"] for t in tasks_of(client, reviewed_exam)["topics"]]
    assert names == ["Fordelinger", "Hypotesetest", "Varians"]
    assert (
        client.get("/api/subjects/idatt2202/topics").json()
        == tasks_of(client, reviewed_exam)["topics"]
    )

    cleared = client.patch(f"/api/tasks/{first['id']}", json={"title": None, "points": None})
    assert cleared.status_code == 204
    after = task(client, reviewed_exam, "1x")
    assert (after["title"], after["points"]) == (None, None)


def test_invalid_task_changes_are_rejected(client, reviewed_exam):
    first = task(client, reviewed_exam, "1")
    url = f"/api/tasks/{first['id']}"
    assert client.patch(url, json={"number": " "}).status_code == 422
    assert client.patch(url, json={"points": -1}).status_code == 422
    assert client.patch(url, json={"topics": ["A", "B", "C", "D"]}).status_code == 422
    missing = "/api/tasks/00000000-0000-0000-0000-000000000000"
    assert client.patch(missing, json={"number": "1"}).status_code == 404
    assert client.delete(missing).status_code == 404


def test_a_task_can_be_split_and_merged_back(client, reviewed_exam):
    first = task(client, reviewed_exam, "1")
    original_image = client.get(first["images"][0]).content

    split = client.post(f"/api/tasks/{first['id']}/split", json={"image_index": 0, "fraction": 0.4})
    assert split.status_code == 204

    numbers = [t["number"] for t in tasks_of(client, reviewed_exam)["tasks"]]
    assert numbers == ["1", "2", "2"]  # the new piece's label is only a suggestion
    upper, lower = tasks_of(client, reviewed_exam)["tasks"][0:2]
    assert upper["id"] == first["id"]
    assert lower["parent_id"] is None
    assert upper["regions"][0]["bottom"] <= lower["regions"][0]["top"]
    assert len(lower["images"]) == 2  # the rest of page 2, and page 3
    for piece in (upper, lower):
        image = client.get(piece["images"][0])
        assert image.status_code == 200
        assert image.content != original_image
    assert client.get(first["images"][0]).status_code == 404  # the old image is gone

    merged = client.post(f"/api/tasks/{lower['id']}/merge-previous")
    assert merged.status_code == 204
    after = tasks_of(client, reviewed_exam)["tasks"]
    assert [t["number"] for t in after] == ["1", "2"]
    assert len(after[0]["images"]) == 3


def test_split_and_merge_report_what_is_wrong(client, reviewed_exam):
    first = task(client, reviewed_exam, "1")
    part_a = first
    assert client.post(f"/api/tasks/{first['id']}/merge-previous").status_code == 409
    assert (
        client.post(
            f"/api/tasks/{part_a['id']}/split", json={"image_index": 5, "fraction": 0.5}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/tasks/{part_a['id']}/split", json={"image_index": 0, "fraction": 1.5}
        ).status_code
        == 422
    )


def test_deleting_a_task_removes_it_and_its_images(client, reviewed_exam):
    first = task(client, reviewed_exam, "1")
    image = first["images"][1]

    assert client.delete(f"/api/tasks/{first['id']}").status_code == 204

    body = tasks_of(client, reviewed_exam)
    assert [t["number"] for t in body["tasks"]] == ["2"]
    assert [t["name"] for t in body["topics"]] == ["Hypotesetest"]
    assert client.get(image).status_code == 404


def test_approving_makes_the_exam_ready_and_closes_it_for_changes(client, reviewed_exam):
    exam_id = reviewed_exam["id"]

    approved = client.post(f"/api/exams/{exam_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "ready"
    assert client.get(f"/api/exams/{exam_id}").json()["status"] == "ready"

    part = task(client, reviewed_exam, "1")
    assert [topic["name"] for topic in part["topics"]] == ["Normalfordeling"]

    assert client.post(f"/api/exams/{exam_id}/approve").status_code == 409
    assert client.patch(f"/api/tasks/{part['id']}", json={"number": "9"}).status_code == 409
    assert client.delete(f"/api/tasks/{part['id']}").status_code == 409
    assert client.get(part["images"][0]).status_code == 200  # still viewable


def test_approval_is_refused_while_a_task_has_no_topic(client, reviewed_exam):
    second = task(client, reviewed_exam, "2")
    client.patch(f"/api/tasks/{second['id']}", json={"topics": []})

    refused = client.post(f"/api/exams/{reviewed_exam['id']}/approve")

    assert refused.status_code == 409
    assert refused.json()["detail"] == "These tasks have no topic yet: 2."
    assert client.get(f"/api/exams/{reviewed_exam['id']}").json()["status"] == "needs_review"


def test_a_second_exam_of_the_subject_reuses_the_topics_of_the_first(
    client, reviewed_exam, build_pdf
):
    second_pdf = build_pdf(
        [
            ("Oppgave 1: Hypotesetesting", {"bold": True}),
            "Regn ut p-verdien.",
            ("Oppgave 2: Normalfordelingen", {"bold": True, "gap": 30}),
            "Finn sannsynligheten.",
            ("Oppgave 3: Regresjon", {"bold": True, "gap": 30}),
            "Tilpass en linje.",
        ]
    )
    second = upload(client, second_pdf, label="Vår 2024").json()
    assert wait_until_processed(client, second["id"])["status"] == "needs_review"

    body = tasks_of(client, second)
    assert [[topic["name"] for topic in t["topics"]] for t in body["tasks"]] == [
        ["Hypotesetest"],
        ["Normalfordeling"],
        ["Regresjon"],
    ]
    assert [t["name"] for t in body["topics"]] == ["Hypotesetest", "Normalfordeling", "Regresjon"]


def test_a_topic_can_be_renamed_and_merged_into_another(client, reviewed_exam):
    topics = {t["name"]: t["id"] for t in tasks_of(client, reviewed_exam)["topics"]}

    renamed = client.patch(f"/api/topics/{topics['Normalfordeling']}", json={"name": "Fordelinger"})
    assert renamed.status_code == 200
    assert renamed.json() == {"id": topics["Normalfordeling"], "name": "Fordelinger"}
    assert [t["name"] for t in task(client, reviewed_exam, "1")["topics"]] == ["Fordelinger"]

    merged = client.patch(f"/api/topics/{topics['Hypotesetest']}", json={"name": "fordelinger"})
    assert merged.status_code == 200
    assert merged.json()["id"] == topics["Normalfordeling"]
    body = tasks_of(client, reviewed_exam)
    assert [t["name"] for t in body["topics"]] == ["Fordelinger"]
    assert [t["name"] for t in task(client, reviewed_exam, "2")["topics"]] == ["Fordelinger"]

    assert (
        client.patch(f"/api/topics/{topics['Normalfordeling']}", json={"name": " "}).status_code
        == 422
    )
    assert (
        client.patch(f"/api/topics/{topics['Hypotesetest']}", json={"name": "X"}).status_code == 404
    )


def test_retrying_a_failed_exam_starts_extraction_over(client, subject, exam_pdf, settings):
    exam = upload(client, BROKEN_PDF).json()
    assert wait_until_processed(client, exam["id"])["status"] == "failed"
    assert tasks_of(client, exam)["tasks"] == []
    assert client.post(f"/api/exams/{exam['id']}/approve").status_code == 409

    # Put a readable PDF where the broken one was, as if the file had been fixed.
    (settings.files_dir / "exams" / exam["id"] / "exam.pdf").write_bytes(exam_pdf)
    assert client.post(f"/api/exams/{exam['id']}/retry").status_code == 202

    assert wait_until_processed(client, exam["id"])["status"] == "needs_review"
    assert [t["number"] for t in tasks_of(client, exam)["tasks"]] == ["1", "2"]


def test_tasks_of_an_unknown_exam_are_not_found(client):
    assert client.get("/api/exams/00000000-0000-0000-0000-000000000000/tasks").status_code == 404


# --- practice ----------------------------------------------------------------


@pytest.fixture
def approved_exam(client, reviewed_exam):
    assert client.post(f"/api/exams/{reviewed_exam['id']}/approve").status_code == 200
    return reviewed_exam


def practice_queue(client, **params):
    response = client.get("/api/practice/queue", params=params)
    assert response.status_code == 200
    return response.json()


def test_nothing_is_queued_until_an_exam_is_approved(client, reviewed_exam):
    assert practice_queue(client) == {"entries": [], "total": 0, "due_count": 0}
    assert client.get("/api/practice/topics").json() == []
    assert client.get(f"/api/practice/exams/{reviewed_exam['id']}/tasks").status_code == 409


def test_the_queue_serves_whole_tasks_with_solution_and_topics(client, approved_exam):
    queue = practice_queue(client)

    assert (queue["total"], queue["due_count"]) == (2, 0)
    assert [(e["task"]["number"], e["reason"]) for e in queue["entries"]] == [
        ("1", "new"),
        ("2", "new"),
    ]
    first = queue["entries"][0]["task"]
    assert first["title"] == "Normalfordeling"
    assert first["exam"] == {
        "id": approved_exam["id"],
        "label": "Høst 2023",
        "subject_code": "IDATT2202",
    }
    assert first["context"] is None
    assert [member["number"] for member in first["group"]] == ["1"]
    assert len(first["images"]) == 2  # the whole task, over two pages
    assert [topic["name"] for topic in first["topics"]] == ["Normalfordeling"]
    assert queue["entries"][0]["topic"]["name"] == "Normalfordeling"
    assert (first["attempt_count"], first["last_grade"], first["due"]) == (0, None, None)
    assert len(first["solution"]["images"]) == 1
    assert "0.16" in first["solution"]["text"]
    assert "Var(2X)" in first["solution"]["text"]

    for url in (*first["images"], *first["solution"]["images"]):
        assert client.get(url).content.startswith(PNG_SIGNATURE)


def test_logging_attempts_reorders_the_queue_and_updates_topics(client, approved_exam):
    first, second = (e["task"] for e in practice_queue(client)["entries"])

    failed = client.post(
        "/api/practice/attempts",
        json={
            "task_id": first["id"],
            "grade": "again",
            "time_spent_seconds": 312.5,
            "answer": "0.84",
            "note": "leste av feil hale",
        },
    )
    assert failed.status_code == 201
    body = failed.json()
    assert (body["task_id"], body["grade"], body["score"]) == (first["id"], "again", 0.0)
    assert body["due"] > body["attempted_at"]

    # The failed task is not due for a minute: the untouched one leads.
    assert [e["task"]["number"] for e in practice_queue(client)["entries"]] == ["2", "1"]

    assert (
        client.post(
            "/api/practice/attempts", json={"task_id": second["id"], "grade": "easy"}
        ).json()["score"]
        == 1.0
    )

    queue = practice_queue(client)
    by_number = {e["task"]["number"]: e["task"] for e in queue["entries"]}
    assert (by_number["1"]["attempt_count"], by_number["1"]["last_grade"]) == (1, "again")
    assert by_number["2"]["last_grade"] == "easy"
    # The task that went well, and is not due for days, comes last.
    assert [e["task"]["number"] for e in queue["entries"]] == ["1", "2"]

    topics = client.get("/api/practice/topics").json()
    assert [t["name"] for t in topics] == ["Normalfordeling", "Hypotesetest"]
    weak, strong = topics
    assert (weak["task_count"], weak["attempted_count"]) == (1, 1)
    assert weak["mastery"] == 0.0
    # Not exactly zero: a few milliseconds have passed since the attempt.
    assert weak["weakness"] > strong["weakness"] == pytest.approx(0.0, abs=1e-6)
    assert weak["priority"] == pytest.approx(weak["weakness"] * weak["urgency"])
    assert weak["subject_code"] == "IDATT2202"


def test_the_queue_can_be_limited_to_a_topic_and_in_length(client, approved_exam):
    topics = {t["name"]: t["id"] for t in client.get("/api/practice/topics").json()}

    only = practice_queue(client, topic_id=topics["Hypotesetest"])
    assert [e["task"]["number"] for e in only["entries"]] == ["2"]
    assert only["total"] == 1

    short = practice_queue(client, limit=1)
    assert len(short["entries"]) == 1
    assert short["total"] == 2

    assert client.get("/api/practice/queue", params={"limit": 0}).status_code == 422
    unknown = "00000000-0000-0000-0000-000000000000"
    assert client.get("/api/practice/queue", params={"topic_id": unknown}).status_code == 404


def test_a_mock_exam_lists_the_exams_tasks_in_order(client, approved_exam):
    response = client.get(f"/api/practice/exams/{approved_exam['id']}/tasks")
    assert response.status_code == 200
    tasks = response.json()
    assert [(t["number"], t["points"]) for t in tasks] == [("1", 2), ("2", 3)]
    assert len(tasks[0]["images"]) == 2  # the task that runs over a page break
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/practice/exams/{missing}/tasks").status_code == 404


def test_invalid_attempts_are_rejected(client, approved_exam, anonymous):
    part = tasks_of(client, approved_exam)["tasks"][0]

    def attempt(**fields):
        return client.post("/api/practice/attempts", json={"task_id": part["id"], **fields})

    assert attempt(grade="perfect").status_code == 422
    assert attempt(grade="good", time_spent_seconds=-1).status_code == 422
    assert attempt().status_code == 422
    missing = "00000000-0000-0000-0000-000000000000"
    assert (
        client.post(
            "/api/practice/attempts", json={"task_id": missing, "grade": "good"}
        ).status_code
        == 404
    )
    assert practice_queue(client)["entries"][0]["task"]["attempt_count"] == 0

    client.post("/api/auth/logout")
    for method, path in [
        ("GET", "/api/practice/queue"),
        ("GET", "/api/practice/topics"),
        ("POST", "/api/practice/attempts"),
        ("GET", f"/api/practice/exams/{approved_exam['id']}/tasks"),
    ]:
        assert anonymous.request(method, path).status_code == 401


# --- dashboard, topic detail and settings ------------------------------------


def test_health_check_needs_no_session(anonymous):
    response = anonymous.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_dashboard_before_and_after_practising(client, approved_exam):
    before = client.get("/api/dashboard", params={"tz": "Europe/Oslo"}).json()
    assert [s["code"] for s in before["subjects"]] == ["IDATT2202"]
    assert (before["task_count"], before["attempted_count"]) == (2, 0)
    assert (before["due_count"], before["streak_days"], before["attempts_today"]) == (0, 0, 0)
    assert {t["name"] for t in before["weakest_topics"]} == {"Normalfordeling", "Hypotesetest"}
    assert all(t["weakness"] == 1.0 for t in before["weakest_topics"])

    first = practice_queue(client)["entries"][0]["task"]
    client.post("/api/practice/attempts", json={"task_id": first["id"], "grade": "good"})

    after = client.get("/api/dashboard", params={"tz": "Europe/Oslo"}).json()
    assert (after["attempted_count"], after["streak_days"], after["attempts_today"]) == (1, 1, 1)
    assert [t["name"] for t in after["weakest_topics"]] == ["Hypotesetest", "Normalfordeling"]


def test_dashboard_accepts_any_time_zone_name_and_falls_back_to_utc(client, approved_exam):
    for tz in ("Europe/Oslo", "America/Los_Angeles", "Not/AZone", ""):
        assert client.get("/api/dashboard", params={"tz": tz}).status_code == 200
    assert client.get("/api/dashboard").status_code == 200


def test_topic_detail_shows_history_tasks_and_attempts(client, approved_exam):
    topics = {t["name"]: t["id"] for t in client.get("/api/practice/topics").json()}
    first = practice_queue(client)["entries"][0]["task"]
    client.post(
        "/api/practice/attempts",
        json={"task_id": first["id"], "grade": "hard", "time_spent_seconds": 90, "note": "tregt"},
    )

    response = client.get(f"/api/topics/{topics['Normalfordeling']}", params={"tz": "Europe/Oslo"})
    assert response.status_code == 200
    detail = response.json()

    assert detail["topic"]["name"] == "Normalfordeling"
    assert (detail["topic"]["task_count"], detail["topic"]["attempted_count"]) == (1, 1)
    assert [(t["number"], t["attempt_count"], t["last_grade"]) for t in detail["tasks"]] == [
        ("1", 1, "hard"),
    ]
    assert detail["tasks"][0]["exam"]["label"] == "Høst 2023"
    (attempt,) = detail["attempts"]
    assert (attempt["grade"], attempt["score"], attempt["time_spent_seconds"]) == ("hard", 0.4, 90)
    assert (attempt["note"], attempt["task_number"], attempt["exam_label"]) == (
        "tregt",
        "1",
        "Høst 2023",
    )
    (point,) = detail["history"]
    assert point["mastery"] == pytest.approx(0.4)

    untouched = client.get(f"/api/topics/{topics['Hypotesetest']}").json()
    assert (untouched["history"], untouched["attempts"]) == ([], [])
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/topics/{missing}").status_code == 404


def test_settings_can_be_read_and_changed_and_change_the_scores(client, approved_exam):
    assert client.get("/api/settings").json() == {
        "mastery_weight": 0.6,
        "staleness_weight": 0.25,
        "coverage_weight": 0.15,
        "preferred_language": "nb",
    }
    first = practice_queue(client)["entries"][0]["task"]
    client.post("/api/practice/attempts", json={"task_id": first["id"], "grade": "easy"})

    changed = client.put(
        "/api/settings",
        json={"mastery_weight": 0, "staleness_weight": 0, "coverage_weight": 1},
    )
    assert changed.status_code == 200
    assert changed.json()["coverage_weight"] == 1
    assert changed.json()["preferred_language"] == "nb"  # not mentioned, so kept

    # Only coverage counts now: the attempted topic is covered, the other untried.
    topics = {t["name"]: t for t in client.get("/api/practice/topics").json()}
    assert topics["Normalfordeling"]["weakness"] == pytest.approx(0.0)
    assert topics["Hypotesetest"]["weakness"] == pytest.approx(1.0)

    assert (
        client.put("/api/settings", json={"preferred_language": "en"}).json()["preferred_language"]
        == "en"
    )
    assert client.get("/api/settings").json()["preferred_language"] == "en"


def test_invalid_settings_are_rejected(client):
    for body in (
        {"mastery_weight": -1},
        {"mastery_weight": 0, "staleness_weight": 0, "coverage_weight": 0},
        {"preferred_language": "german"},
        {"mastery_weight": "much"},
    ):
        assert client.put("/api/settings", json=body).status_code == 422
    assert client.get("/api/settings").json()["mastery_weight"] == 0.6


def test_the_language_setting_decides_which_version_of_the_next_exam_is_kept(
    client, subject, build_pdf
):
    def page(word, question, order):
        return [(f"{word} 1", {"bold": True}), question, (f"{word} 2", {"bold": True}), order]

    pdf = build_pdf(
        ["Eksamen / Exam"],
        page("Oppgave", "Hva er sannsynligheten for at kula ikke er defekt?", "Regn ut svaret."),
        page("Problem", "What is the probability that the ball is not defective?", "Compute it."),
    )

    norwegian = upload(client, pdf, label="Bokmål").json()
    wait_until_processed(client, norwegian["id"])
    client.put("/api/settings", json={"preferred_language": "en"})
    english = upload(client, pdf, label="English").json()
    wait_until_processed(client, english["id"])

    def pages(exam):
        return {r["page"] for t in tasks_of(client, exam)["tasks"] for r in t["regions"]}

    assert [t["number"] for t in tasks_of(client, norwegian)["tasks"]] == ["1", "2"]
    assert [t["number"] for t in tasks_of(client, english)["tasks"]] == ["1", "2"]
    assert pages(norwegian) == {2}
    assert pages(english) == {3}


def test_new_endpoints_require_a_session(anonymous):
    for method, path in [
        ("GET", "/api/dashboard"),
        ("GET", "/api/settings"),
        ("PUT", "/api/settings"),
        ("GET", "/api/topics/00000000-0000-0000-0000-000000000000"),
    ]:
        assert anonymous.request(method, path).status_code == 401


# --- serving the built frontend ----------------------------------------------


@pytest.fixture
def served(tmp_path, settings):
    """The app with a (stand-in) built frontend for the backend to serve."""
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><title>levet</title>")
    (static / "assets" / "index-abc123.js").write_text("console.log('app')")
    (static / "manifest.webmanifest").write_text('{"name": "levet"}')
    (static / "sw.js").write_text("// service worker")
    (tmp_path / "secret.txt").write_text("outside the static directory")
    with_static = Settings(password=PASSWORD, data_dir=settings.data_dir, static_dir=static)
    with TestClient(create_app(build_container(with_static))) as client:
        yield client


def test_the_backend_serves_the_app_and_its_files(served):
    page = served.get("/")
    assert page.status_code == 200
    assert "<title>levet</title>" in page.text
    assert page.headers["cache-control"] == "no-cache"

    script = served.get("/assets/index-abc123.js")
    assert script.text == "console.log('app')"
    assert "immutable" in script.headers["cache-control"]

    manifest = served.get("/manifest.webmanifest")
    assert manifest.headers["content-type"].startswith("application/manifest+json")
    assert manifest.headers["cache-control"] == "no-cache"
    assert served.get("/sw.js").headers["cache-control"] == "no-cache"


def test_any_other_path_gets_the_app_so_that_deep_links_and_reloads_work(served):
    for path in ("/practice", "/practice/topics/123", "/exams/abc", "/assets/missing.js"):
        response = served.get(path)
        assert response.status_code == 200
        assert "<title>levet</title>" in response.text


def test_the_api_is_untouched_by_the_frontend_route(served):
    assert served.get("/api/health").json() == {"status": "ok"}
    assert served.get("/api/subjects").status_code == 401
    unknown = served.get("/api/nothing/here")
    assert unknown.status_code == 404
    assert unknown.headers["content-type"].startswith("application/json")
    assert served.get("/api").status_code == 404


def test_files_outside_the_static_directory_are_never_served(served):
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"):
        response = served.get(path)
        assert "outside the static directory" not in response.text


def test_without_a_static_directory_only_the_api_exists(anonymous):
    assert anonymous.get("/").status_code == 404
    assert anonymous.get("/practice").status_code == 404


def test_a_static_directory_without_the_app_is_refused_at_start(tmp_path, settings):
    empty = tmp_path / "empty"
    empty.mkdir()
    broken = Settings(password=PASSWORD, data_dir=settings.data_dir, static_dir=empty)
    with pytest.raises(RuntimeError, match="index.html"):
        create_app(build_container(broken))
