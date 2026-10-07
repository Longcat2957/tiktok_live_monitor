from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCHIVE_PATH", str(tmp_path / "data" / "monitor.sqlite3"))
