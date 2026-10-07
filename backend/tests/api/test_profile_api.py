"""Exercise the separate-process profiling CLI without TikTok credentials."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Runner requires Linux /proc")
def test_profile_api_cli_flushes_and_removes_temporary_files(tmp_path: Path) -> None:
    backend = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [
            sys.executable,
            "profile_api.py",
            "--duration",
            "1",
            "--comment-rate",
            "100",
            "--concurrency",
            "2",
            "--directory",
            str(tmp_path),
            "--profile",
        ],
        cwd=backend,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["ok"] and result["checks"] and all(result["checks"].values()), result
    generated = result["server"]["generated"]
    assert 95 <= generated <= 100
    assert result["server"]["sqlite_comments"] == generated
    assert len(result["clients"]) == 2
    assert all(peer["received"] == generated and peer["in_order"] for peer in result["clients"])
    assert result["server"]["profile"]["main"]["total_self_seconds"] > 0
    assert result["server"]["profile"]["writer"]["total_self_seconds"] > 0
    assert result["driver_profile"]["total_self_seconds"] > 0
    assert result["temporary_directory_removed"]
    assert not list(tmp_path.iterdir())
