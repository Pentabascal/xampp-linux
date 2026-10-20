"""Detección de puertos TCP ocupados y del proceso que los ocupa."""

import re
import subprocess
from dataclasses import dataclass

_PROC = re.compile(r'users:\(\("([^"]+)",pid=(\d+)')


@dataclass(frozen=True)
class Owner:
    pid: int | None
    process: str | None


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


def busy(ports: list[int], run=subprocess.run) -> dict[int, Owner]:
    out = run(["ss", "-ltnpH"], capture_output=True, text=True).stdout
    listening = parse_ss(out)
    return {p: listening[p] for p in ports if p in listening}


def describe(port: int, owner: Owner) -> str:
    if owner.process is None:
        return f"El puerto {port} está ocupado por otro usuario o por root"
    return f"El puerto {port} está ocupado por {owner.process} (PID {owner.pid})"
