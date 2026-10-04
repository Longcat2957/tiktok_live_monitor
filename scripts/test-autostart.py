"""Run with python3 scripts/test-autostart.py; never touches desktop settings."""

import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="monitor-autostart-") as directory:
        root = Path(directory)
        system = root / "system-autostart"
        system.write_bytes(b"/usr/bin/lwrespawn /usr/bin/wf-panel-pi &\n/usr/bin/kanshi &\n")
        config = root / "user's config"
        autostart = config / "labwc/autostart"
        autostart.parent.mkdir(parents=True)
        script = root / "repair.sh"
        script.write_text(
            (ROOT / "deploy/repair-autostart.sh").read_text().replace(
                "SYSTEM_AUTOSTART=/etc/xdg/labwc/autostart",
                f'SYSTEM_AUTOSTART="{system}"',
            )
        )

        def repair():
            subprocess.run(
                ["bash", str(script)],
                env={**os.environ, "XDG_CONFIG_HOME": str(config)},
                check=True,
                capture_output=True,
                text=True,
            )

        repair()
        assert not autostart.exists()
        custom = b"\n# tiktok-live-monitor kiosk\n/bin/bash '/app/wait-for-app.sh' &\n# keep me\n"
        # Unmanaged files and configurations we cannot identify stay untouched.
        for original in (system.read_bytes(), custom, b"# user changes\n" + system.read_bytes() + custom):
            autostart.write_bytes(original)
            repair()
            assert autostart.read_bytes() == original
            assert not list(autostart.parent.glob("autostart.backup.*"))

        original = system.read_bytes() + custom
        autostart.write_bytes(original)
        autostart.chmod(0o640)
        repair()
        assert autostart.read_bytes() == custom
        assert autostart.stat().st_mode & 0o777 == 0o640
        backups = list(autostart.parent.glob("autostart.backup.*"))
        assert len(backups) == 1 and backups[0].read_bytes() == original
        repair()
        assert autostart.read_bytes() == custom
        assert list(autostart.parent.glob("autostart.backup.*")) == backups
    print("Autostart checks passed: duplicate removal, backup, custom entries and repeat runs.")


if __name__ == "__main__":
    main()
