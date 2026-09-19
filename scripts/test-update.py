"""Run with python3 scripts/test-update.py; uses local Git repos and a fake Docker."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="monitor-update-") as directory:
        root = Path(directory)
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "Update test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Update test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
        }

        def run(*args, cwd=root, check=True):
            return subprocess.run(
                args, cwd=cwd, env=env, text=True, capture_output=True, check=check
            )

        remote, seed, checkout = (root / name for name in ("remote.git", "seed", "checkout"))
        run("git", "init", "--bare", str(remote))
        run("git", "init", "--initial-branch=main", str(seed))
        (seed / "scripts").mkdir()
        for name in ("update.sh", "build.sh"):
            shutil.copy2(ROOT / "scripts" / name, seed / "scripts" / name)
        (seed / ".gitignore").write_text(".env\n")
        run("git", "add", ".", cwd=seed)
        run("git", "commit", "-m", "Initial", cwd=seed)
        run("git", "remote", "add", "origin", str(remote), cwd=seed)
        run("git", "push", "-u", "origin", "main", cwd=seed)
        run("git", "clone", "--branch", "main", str(remote), str(checkout))
        settings = checkout / ".env"
        settings.write_text("COMMENT_HISTORY_SIZE=17\n")
        original_settings = settings.read_bytes()

        bin_dir = root / "bin"
        bin_dir.mkdir()
        log = root / "docker.log"
        docker = bin_dir / "docker"
        docker.write_text(
            "#!/bin/bash\n"
            'printf "%s\\n" "$*" >> "$UPDATE_TEST_LOG"\n'
            'if [[ "$*" == "${UPDATE_TEST_FAIL:-never}" ]]; then exit 7; fi\n'
        )
        docker.chmod(0o755)
        env.update(PATH=f"{bin_dir}:{env['PATH']}", UPDATE_TEST_LOG=str(log))

        def update(success, *args):
            log.write_text("")
            result = run("bash", str(checkout / "scripts/update.sh"), *args, check=False)
            assert (result.returncode == 0) == success, result.stdout + result.stderr
            assert settings.read_bytes() == original_settings
            return log.read_text().splitlines()

        assert update(True, "--help") == []
        assert update(False, "--unknown") == []
        (checkout / "untracked.txt").write_text("keep me")
        assert update(False) == []
        assert (checkout / "untracked.txt").read_text() == "keep me"
        (checkout / "untracked.txt").unlink()
        (checkout / ".gitignore").write_text(".env\nlocal-change\n")
        assert update(False) == []
        run("git", "add", ".gitignore", cwd=checkout)
        assert update(False) == []
        run("git", "restore", "--staged", "--worktree", ".gitignore", cwd=checkout)
        settings.rename(checkout / ".env.saved")
        result = run("bash", str(checkout / "scripts/update.sh"), check=False)
        assert result.returncode != 0 and ".env" in result.stderr
        (checkout / ".env.saved").rename(settings)
        run("git", "checkout", "--detach", cwd=checkout)
        assert update(False) == []
        run("git", "checkout", "main", cwd=checkout)

        # Pull changes to the running script itself and use the updated build script.
        with (seed / "scripts/update.sh").open("a") as script:
            script.write("\n# New remote revision\n")
        with (seed / "scripts/build.sh").open("a") as script:
            script.write("\ndocker updated-build\n")
        run("git", "add", ".", cwd=seed)
        run("git", "commit", "-m", "Update scripts", cwd=seed)
        run("git", "push", cwd=seed)
        commands = update(True)
        assert commands == [
            "compose version",
            "info",
            "compose build",
            "updated-build",
            "compose up -d --wait --wait-timeout 120",
        ], commands
        assert (
            run("git", "rev-parse", "HEAD", cwd=checkout).stdout
            == run("git", "rev-parse", "HEAD", cwd=seed).stdout
        )
        env["UPDATE_TEST_FAIL"] = "compose build"
        assert update(False)[-1] == "compose build"  # Never replace after a failed build.
        env["UPDATE_TEST_FAIL"] = "compose up -d --wait --wait-timeout 120"
        assert update(False)[-1] == env["UPDATE_TEST_FAIL"]
        del env["UPDATE_TEST_FAIL"]

        for repo in (seed, checkout):
            (repo / "different.txt").write_text(repo.name)
            run("git", "add", ".", cwd=repo)
            run("git", "commit", "-m", "Diverging history", cwd=repo)
        run("git", "push", cwd=seed)
        assert update(False) == ["compose version", "info"]
        assert (checkout / "different.txt").read_text() == "checkout"
    print("Update checks passed: fast-forward, local changes, .env, build and health failures.")


if __name__ == "__main__":
    main()
