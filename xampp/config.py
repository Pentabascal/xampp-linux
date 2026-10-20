"""Rutas de datos y ajustes del usuario."""

import json
import os
from dataclasses import asdict, dataclass, fields
from importlib.resources import files
from pathlib import Path
from string import Template


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


ETC_TEMPLATES = ("httpd.conf", "php-fpm.conf", "php.ini", "my.cnf")
UNIT_TEMPLATES = (
    "xampp-apache.service", "xampp-php.service",
    "xampp-mariadb.service", "xampp-mail.service",
)


def https_effective(paths: Paths, s: Settings) -> bool:
    return (
        s.https
        and (paths.ssl / "localhost.pem").exists()
        and (paths.ssl / "localhost-key.pem").exists()
    )


def _template(name: str) -> Template:
    return Template(files("xampp").joinpath("templates", name).read_text())


def render_all(paths: Paths, s: Settings) -> list[str]:
    """Genera etc/ y las units desde las plantillas. Devuelve avisos."""
    warnings = []
    paths.ensure_dirs()
    paths.units.mkdir(parents=True, exist_ok=True)

    values = {k: str(v) for k, v in asdict(paths).items()}
    values.update({k: str(v) for k, v in asdict(s).items()})
    values["ssl_block"] = ""
    if https_effective(paths, s):
        values["ssl_block"] = _template("httpd-ssl.conf").substitute(values)
    elif s.https:
        warnings.append(
            "HTTPS desactivado: falta el certificado en "
            f"{paths.ssl}. Ejecuta xampp --setup para crearlo."
        )

    for name in ETC_TEMPLATES:
        (paths.etc / name).write_text(_template(name).substitute(values))
    for name in UNIT_TEMPLATES:
        (paths.units / name).write_text(_template(f"units/{name}").substitute(values))

    if not any(paths.htdocs.iterdir()):
        (paths.htdocs / "index.php").write_text(_template("index.php").substitute(values))
    return warnings
