"""Pasos de la primera instalación. Cada paso es idempotente."""

import subprocess
import tempfile
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from string import Template
from typing import Callable

from .config import Paths, Settings, is_installed, render_all, save_settings
from .systemd import Result, Systemd, error_result

REPO_PACKAGES = ("apache", "php", "php-fpm", "php-gd", "mariadb", "phpmyadmin", "mkcert", "nss")
AUR_PACKAGES = ("mailpit-bin",)
HOOK_PATH = Path("/etc/pacman.d/hooks/xampp-setcap.hook")
REPO = Path(__file__).resolve().parents[1]


@dataclass
class Step:
    id: str
    title: str
    fn: Callable[[], Result]


def _template(name: str) -> str:
    return files("xampp").joinpath("templates", name).read_text()


def _result(p: subprocess.CompletedProcess) -> Result:
    return Result(p.returncode == 0, (p.stdout + p.stderr).strip())


def missing_packages(run=subprocess.run) -> list[str]:
    p = run(["pacman", "-T", *REPO_PACKAGES], capture_output=True, text=True)
    return p.stdout.split() if p.returncode != 0 else []


def steps(paths: Paths, settings: Settings, systemd: Systemd,
          run=subprocess.run, home: Path | None = None) -> list[Step]:
    home = home or Path.home()

    def sh(*args: str) -> Result:
        return _result(run(list(args), capture_output=True, text=True))

    def root() -> Result:
        missing = missing_packages(run)
        cap = run(["getcap", "/usr/bin/httpd"], capture_output=True, text=True).stdout
        stamp = paths.root / ".root-setup-done"
        if not missing and "cap_net_bind_service" in cap and HOOK_PATH.exists() and stamp.exists():
            return Result(True, "Ya configurado")
        with tempfile.TemporaryDirectory() as tmp:
            script, hook = Path(tmp) / "root-setup.sh", Path(tmp) / "xampp-setcap.hook"
            script.write_text(_template("root-setup.sh"))
            hook.write_text(_template("xampp-setcap.hook"))
            r = sh("pkexec", "/bin/sh", str(script), str(hook), *missing)
        if r.ok:
            paths.root.mkdir(parents=True, exist_ok=True)
            stamp.touch()
        return r

    def interactive() -> Result:
        def done() -> bool:
            if not Path("/usr/bin/mailpit").exists():
                return False
            caroot = run(["mkcert", "-CAROOT"], capture_output=True, text=True).stdout.strip()
            return bool(caroot) and (Path(caroot) / "rootCA.pem").exists()

        if done():
            return Result(True, "Ya configurado")
        sh("kitty", "--title", "xampp-setup", "sh", "-c",
           f"yay -S --needed {' '.join(AUR_PACKAGES)} && mkcert -install; "
           'echo; printf "Pulsa Enter para cerrar"; read _')
        if done():
            return Result(True, "Mailpit instalado y certificado raíz de mkcert creado")
        return Result(False, "Falta Mailpit o el certificado raíz de mkcert; vuelve a intentarlo")

    def files_step() -> Result:
        if (paths.etc / "httpd.conf").exists():
            return Result(True, f"Se conserva la configuración de {paths.etc} "
                                "(para regenerarla usa Ajustes)")
        warnings = render_all(paths, settings)
        return Result(True, "\n".join(warnings) or f"Configuración en {paths.etc}")

    def cert() -> Result:
        pems = (paths.ssl / "localhost.pem", paths.ssl / "localhost-key.pem")
        if all(p.exists() for p in pems):
            return Result(True, "El certificado ya existe")
        paths.ssl.mkdir(parents=True, exist_ok=True)
        r = sh("mkcert",
               "-cert-file", str(paths.ssl / "localhost.pem"),
               "-key-file", str(paths.ssl / "localhost-key.pem"),
               "localhost", "127.0.0.1", "::1")
        if r.ok:
            render_all(paths, settings)
        return r

    def db() -> Result:
        if (paths.mysql / "mysql").exists():
            return Result(True, "Base de datos ya inicializada")
        paths.mysql.mkdir(parents=True, exist_ok=True)
        return sh("/usr/bin/mariadb-install-db", f"--datadir={paths.mysql}",
                  "--auth-root-authentication-method=normal", "--skip-test-db")

    def units() -> Result:
        return systemd.daemon_reload()

    def launcher() -> Result:
        bin_dir, apps = home / ".local/bin", home / ".local/share/applications"
        bin_dir.mkdir(parents=True, exist_ok=True)
        apps.mkdir(parents=True, exist_ok=True)
        exe = bin_dir / "xampp"
        exe.write_text(Template(_template("launcher.sh")).substitute(repo=REPO))
        exe.chmod(0o755)
        (apps / "xampp.desktop").write_text(
            Template(_template("xampp.desktop")).substitute(launcher=exe))
        if not is_installed(paths):
            save_settings(paths, settings)
        return Result(True, f"Lanzador en {exe}")

    def safe(fn: Callable[[], Result]) -> Callable[[], Result]:
        def wrapper() -> Result:
            try:
                return fn()
            except Exception as e:
                return error_result(e)
        return wrapper

    return [Step(s.id, s.title, safe(s.fn)) for s in [
        Step("root", "Paquetes y permisos (pide contraseña)", root),
        Step("interactive", "Mailpit y certificado raíz (terminal)", interactive),
        Step("files", "Carpetas y configuración", files_step),
        Step("cert", "Certificado HTTPS", cert),
        Step("db", "Base de datos", db),
        Step("units", "Servicios", units),
        Step("launcher", "Acceso directo", launcher),
    ]]

