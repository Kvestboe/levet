import os
import re
import tempfile
from pathlib import Path

_SAFE_KEY = re.compile(r"[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*")


class LocalFileStore:
    """Stores files in a directory tree on the local disk."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def write(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temporary file and rename, so a crash never leaves half a file.
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as tmp:
                tmp.write(data)
            os.replace(tmp_name, path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def _path(self, key: str) -> Path:
        if not _SAFE_KEY.fullmatch(key) or ".." in key.split("/"):
            raise ValueError(f"invalid file key: {key!r}")
        return self._root / key
