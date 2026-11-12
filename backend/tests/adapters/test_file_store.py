import pytest

from levet.adapters.files.local import LocalFileStore


def test_written_data_can_be_read_back(files):
    assert not files.exists("exams/abc/exam.pdf")
    files.write("exams/abc/exam.pdf", b"%PDF-1.7 data")
    assert files.exists("exams/abc/exam.pdf")
    assert files.read("exams/abc/exam.pdf") == b"%PDF-1.7 data"


def test_writing_again_replaces_the_content_and_leaves_no_temp_files(files, tmp_path):
    files.write("exams/abc/pages/exam-001.png", b"old")
    files.write("exams/abc/pages/exam-001.png", b"new")
    assert files.read("exams/abc/pages/exam-001.png") == b"new"
    assert [p.name for p in (tmp_path / "files/exams/abc/pages").iterdir()] == ["exam-001.png"]


def test_reading_a_missing_key_raises_file_not_found(files):
    with pytest.raises(FileNotFoundError):
        files.read("exams/abc/missing.png")


def test_data_survives_a_new_store_on_the_same_directory(files, tmp_path):
    files.write("a/b.bin", b"kept")
    assert LocalFileStore(tmp_path / "files").read("a/b.bin") == b"kept"


@pytest.mark.parametrize(
    "key",
    ["", "/etc/passwd", "../outside", "exams/../../outside", "exams//x", "exams/x/", "a b", "a\\b"],
)
def test_keys_that_could_escape_the_store_are_rejected(files, key):
    with pytest.raises(ValueError):
        files.write(key, b"x")
    with pytest.raises(ValueError):
        files.read(key)
    with pytest.raises(ValueError):
        files.exists(key)


def test_a_file_can_be_deleted_and_deleting_it_again_is_harmless(files):
    files.write("exams/abc/task-images/1.png", b"x")
    files.delete("exams/abc/task-images/1.png")
    files.delete("exams/abc/task-images/1.png")
    assert not files.exists("exams/abc/task-images/1.png")


def test_deleting_a_tree_removes_everything_under_it_and_nothing_else(files):
    files.write("exams/abc/task-images/1.png", b"x")
    files.write("exams/abc/task-images/2.png", b"x")
    files.write("exams/abc/exam.pdf", b"kept")
    files.write("exams/other/task-images/1.png", b"kept")

    files.delete_tree("exams/abc/task-images")
    files.delete_tree("exams/abc/task-images")  # already gone

    assert not files.exists("exams/abc/task-images/1.png")
    assert not files.exists("exams/abc/task-images/2.png")
    assert files.read("exams/abc/exam.pdf") == b"kept"
    assert files.read("exams/other/task-images/1.png") == b"kept"
