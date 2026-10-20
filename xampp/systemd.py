"""Envoltorio de `systemctl --user` y `journalctl --user`."""

import subprocess
from dataclasses import dataclass

STATES = ("active", "inactive", "failed", "activating", "deactivating")


@dataclass(frozen=True)
class Result:
    ok: bool
    output: str


class Systemd:
    def __init__(self, run=subprocess.run):
        self._run = run

    def _ctl(self, *args: str) -> Result:
        p = self._run(["systemctl", "--user", *args], capture_output=True, text=True)
        return Result(p.returncode == 0, (p.stdout + p.stderr).strip())

    def start(self, unit: str) -> Result:
        return self._ctl("start", unit)

    def stop(self, unit: str) -> Result:
        return self._ctl("stop", unit)

    def restart(self, unit: str) -> Result:
        return self._ctl("restart", unit)

    def daemon_reload(self) -> Result:
        return self._ctl("daemon-reload")

    def state(self, unit: str) -> str:
        state = self._ctl("is-active", unit).output
        return state if state in STATES else "inactive"

    def journal(self, unit: str, lines: int = 20) -> str:
        p = self._run(
            ["journalctl", "--user", "-u", unit, "-n", str(lines), "--no-pager"],
            capture_output=True, text=True,
        )
        return p.stdout.strip()
