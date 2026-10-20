"""Leer el final de un log y seguir lo que se le añade."""

from collections import deque
from pathlib import Path


def tail(path: Path, lines: int = 500) -> str:
    try:
        with path.open(errors="replace") as f:
            return "".join(deque(f, maxlen=lines))
    except FileNotFoundError:
        return ""


class Follower:
    """Devuelve solo lo añadido desde la última lectura (empieza al final del archivo)."""

    def __init__(self, path: Path):
        self.path = path
        self._pos = self._size()

    def _size(self) -> int:
        try:
            return self.path.stat().st_size
        except FileNotFoundError:
            return 0

    def read_new(self) -> str:
        size = self._size()
        if size < self._pos:  # truncado o rotado
            self._pos = 0
        if size == self._pos:
            return ""
        with self.path.open("rb") as f:
            f.seek(self._pos)
            data = f.read(size - self._pos)
        self._pos = size
        return data.decode(errors="replace")
