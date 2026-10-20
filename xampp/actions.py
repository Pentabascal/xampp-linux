"""Iniciar, parar y reiniciar servicios con las comprobaciones previas."""

import subprocess
from dataclasses import replace

from . import ports
from .config import Paths, Settings, https_effective
from .ports import Owner
from .services import SERVICES, get, start_order
from .systemd import Result, Systemd

SETCAP_HINT = (
    "Apache no tiene permiso para usar el puerto; "
    "ejecuta `xampp --setup` para volver a aplicarlo."
)


class Controller:
    def __init__(self, paths: Paths, settings: Settings, systemd: Systemd,
                 busy_fn=ports.busy, run=subprocess.run):
        self.paths = paths
        self.settings = settings
        self.systemd = systemd
        self._busy = busy_fn
        self._run = run

    def state(self, id: str) -> str:
        return self.systemd.state(get(id).unit)

    def check_ports(self, id: str) -> dict[int, Owner]:
        effective = replace(self.settings, https=https_effective(self.paths, self.settings))
        wanted: list[int] = []
        for sid in start_order([id]):
            if self.state(sid) != "active":
                wanted += get(sid).ports(effective)
        return self._busy(wanted) if wanted else {}

    def validate_apache(self) -> Result:
        p = self._run(
            ["/usr/bin/httpd", "-t", "-f", str(self.paths.etc / "httpd.conf")],
            capture_output=True, text=True,
        )
        return Result(p.returncode == 0, p.stderr.strip())

    def _with_journal(self, unit: str, r: Result) -> Result:
        journal = self.systemd.journal(unit)
        output = "\n".join(x for x in (r.output, journal) if x)
        if "make_sock" in journal and "Permission denied" in journal:
            output += "\n" + SETCAP_HINT
        return Result(False, output)

    def start(self, id: str) -> Result:
        taken = self.check_ports(id)
        if taken:
            return Result(False, "\n".join(ports.describe(p, o) for p, o in taken.items()))
        if id == "apache":
            valid = self.validate_apache()
            if not valid.ok:
                return valid
        unit = get(id).unit
        r = self.systemd.start(unit)
        return r if r.ok else self._with_journal(unit, r)

    def stop(self, id: str) -> Result:
        return self.systemd.stop(get(id).unit)

    def restart(self, id: str) -> Result:
        if id == "apache":
            valid = self.validate_apache()
            if not valid.ok:
                return valid
        unit = get(id).unit
        r = self.systemd.restart(unit)
        return r if r.ok else self._with_journal(unit, r)

    def _all(self, action, services) -> Result:
        failures = []
        for svc in services:
            r = action(svc.id)
            if not r.ok:
                failures.append(f"{svc.name}: {r.output}")
        return Result(not failures, "\n".join(failures))

    def start_all(self) -> Result:
        return self._all(self.start, SERVICES)

    def stop_all(self) -> Result:
        return self._all(self.stop, reversed(SERVICES))
