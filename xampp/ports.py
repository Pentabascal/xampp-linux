"""Detección de puertos TCP ocupados y del proceso que los ocupa."""

import os
import re
import subprocess
from dataclasses import dataclass

_PROC = re.compile(r'users:\(\("([^"]+)",pid=(\d+)')


@dataclass(frozen=True)
class Owner:
    pid: int | None
    process: str | None
    guessed: bool = False  # deducido con pgrep, ss no mostró el proceso


def parse_ss(text: str) -> dict[int, Owner]:
    """Parsea `ss -ltnpH`. Sin columna de proceso (root u otro usuario) → Owner(None, None)."""
    result: dict[int, Owner] = {}
    for line in text.splitlines():
        cols = line.split()
        if len(cols) < 4:
            continue
        port = cols[3].rsplit(":", 1)[-1]
        if not port.isdigit():
            continue
        m = _PROC.search(line)
        owner = Owner(int(m.group(2)), m.group(1)) if m else Owner(None, None)
        result.setdefault(int(port), owner)
    return result


def _own_httpd(run) -> Owner | None:
    """httpd con setcap no es "dumpable" y ss no muestra su proceso aunque sea nuestro."""
    p = run(["pgrep", "-u", str(os.getuid()), "-o", "-x", "httpd"], capture_output=True, text=True)
    pid = p.stdout.strip()
    return Owner(int(pid), "httpd", guessed=True) if p.returncode == 0 and pid.isdigit() else None


def busy(ports: list[int], run=subprocess.run) -> dict[int, Owner]:
    out = run(["ss", "-ltnpH"], capture_output=True, text=True).stdout
    listening = parse_ss(out)
    taken = {p: listening[p] for p in ports if p in listening}
    if any(o.pid is None for o in taken.values()):
        guess = _own_httpd(run)
        if guess:
            taken = {p: (guess if o.pid is None else o) for p, o in taken.items()}
    return taken


def describe(port: int, owner: Owner) -> str:
    if owner.process is None:
        return (f"El puerto {port} está ocupado por un proceso que no se puede identificar "
                f"(compruébalo con: sudo ss -ltnp 'sport = :{port}')")
    if owner.guessed:
        return (f"El puerto {port} está ocupado, probablemente por {owner.process} "
                f"(PID {owner.pid}), un Apache que quedó en marcha")
    return f"El puerto {port} está ocupado por {owner.process} (PID {owner.pid})"
