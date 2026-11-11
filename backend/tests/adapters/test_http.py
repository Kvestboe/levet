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
