"""Rutas de datos y ajustes del usuario."""

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    root: Path
    etc: Path
    logs: Path
    data: Path
    mysql: Path
    ssl: Path
    run: Path
    htdocs: Path
    units: Path

    @classmethod
    def at(cls, root: Path, units: Path) -> "Paths":
        root = Path(root)
        return cls(
            root=root,
            etc=root / "etc",
            logs=root / "logs",
            data=root / "data",
            mysql=root / "data" / "mysql",
            ssl=root / "ssl",
            run=root / "run",
            htdocs=root / "htdocs",
            units=Path(units),
        )

    @classmethod
    def default(cls) -> "Paths":
        home = Path.home()
        root = os.environ.get("XAMPP_HOME") or home / "xampp"
        units = os.environ.get("XAMPP_UNITS_DIR") or home / ".config/systemd/user"
        return cls.at(Path(root), Path(units))

    def ensure_dirs(self) -> None:
        for d in (self.etc, self.logs, self.mysql, self.ssl, self.run, self.htdocs):
            d.mkdir(parents=True, exist_ok=True)


@dataclass
class Settings:
    http_port: int = 80
    https_port: int = 443
    mariadb_port: int = 3306
    smtp_port: int = 1025
    mail_web_port: int = 8025
    https: bool = True
    mariadb_root_password: str = ""


def _settings_file(paths: Paths) -> Path:
    return paths.etc / "settings.json"


def is_installed(paths: Paths) -> bool:
    return _settings_file(paths).exists()


def load_settings(paths: Paths) -> Settings:
    f = _settings_file(paths)
    if not f.exists():
        return Settings()
    raw = json.loads(f.read_text())
    known = {fl.name for fl in fields(Settings)}
    return Settings(**{k: v for k, v in raw.items() if k in known})


def save_settings(paths: Paths, s: Settings) -> None:
    paths.etc.mkdir(parents=True, exist_ok=True)
    _settings_file(paths).write_text(json.dumps(asdict(s), indent=2) + "\n")
