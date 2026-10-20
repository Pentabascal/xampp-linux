from pathlib import Path

from fakes import FakeRun

from xampp import setup
from xampp.config import Settings, is_installed, load_settings, save_settings
from xampp.systemd import Systemd

TEMPLATES = Path(__file__).parent.parent / "xampp" / "templates"


def make_steps(paths, tmp_path, run=None, settings=None):
    run = run or FakeRun()
    return {s.id: s for s in setup.steps(paths, settings or Settings(), Systemd(run),
                                         run=run, home=tmp_path / "home")}, run


def test_missing_packages_parses_pacman_T():
    run = FakeRun({"pacman -T": (127, "mariadb\nmkcert\n", "")})
    assert setup.missing_packages(run) == ["mariadb", "mkcert"]
    assert run.calls[0][:2] == ["pacman", "-T"]
    assert setup.missing_packages(FakeRun()) == []


def test_step_order(paths, tmp_path):
    steps = setup.steps(paths, Settings(), Systemd(FakeRun()), run=FakeRun(), home=tmp_path)
    assert [s.id for s in steps] == ["root", "interactive", "files", "cert", "db", "units", "launcher"]


def test_root_step_runs_pkexec_with_missing(paths, tmp_path):
    run = FakeRun({"pacman -T": (127, "mkcert\n", "")})
    steps, run = make_steps(paths, tmp_path, run)
    assert steps["root"].fn().ok
    pk = [c for c in run.calls if c[0] == "pkexec"][0]
    assert pk[1] == "/bin/sh" and pk[-1] == "mkcert"


def test_files_step_idempotent(paths, tmp_path):
    steps, _ = make_steps(paths, tmp_path)
    assert steps["files"].fn().ok and steps["files"].fn().ok
    assert (paths.etc / "httpd.conf").exists()
    assert not is_installed(paths)


def test_launcher_step_keeps_existing_settings(paths, tmp_path):
    save_settings(paths, Settings(http_port=8080))
    steps, _ = make_steps(paths, tmp_path)
    assert steps["launcher"].fn().ok
    assert load_settings(paths).http_port == 8080
    launcher = tmp_path / "home/.local/bin/xampp"
    assert launcher.exists() and launcher.stat().st_mode & 0o111
    assert str(Path(setup.__file__).resolve().parents[1]) in launcher.read_text()
    assert (tmp_path / "home/.local/share/applications/xampp.desktop").exists()


def test_launcher_step_marks_installed(paths, tmp_path):
    steps, _ = make_steps(paths, tmp_path)
    steps["launcher"].fn()
    assert is_installed(paths)


def test_db_step_skips_when_initialized(paths, tmp_path):
    (paths.mysql / "mysql").mkdir(parents=True)
    steps, run = make_steps(paths, tmp_path)
    assert steps["db"].fn().ok
    assert not any("mariadb-install-db" in c[0] for c in run.calls)


def test_db_step_initializes(paths, tmp_path):
    steps, run = make_steps(paths, tmp_path)
    assert steps["db"].fn().ok
    assert run.calls[-1][:2] == ["/usr/bin/mariadb-install-db", f"--datadir={paths.mysql}"]


def test_cert_step_enables_https(paths, tmp_path):
    steps, run = make_steps(paths, tmp_path)
    steps["files"].fn()
    paths.ssl.mkdir(parents=True, exist_ok=True)
    (paths.ssl / "localhost.pem").write_text("c")
    (paths.ssl / "localhost-key.pem").write_text("k")
    assert steps["cert"].fn().ok
    assert run.calls[-1][0] == "mkcert"
    assert "Listen 443" in (paths.etc / "httpd.conf").read_text()


def test_step_failure_is_reported(paths, tmp_path):
    run = FakeRun({"/usr/bin/mariadb-install-db": (1, "", "sin permisos\n")})
    steps, _ = make_steps(paths, tmp_path, run)
    r = steps["db"].fn()
    assert not r.ok and "sin permisos" in r.output


def test_hook_content():
    hook = (TEMPLATES / "xampp-setcap.hook").read_text()
    assert "Target = apache" in hook
    assert "When = PostTransaction" in hook
    assert "Exec = /usr/bin/setcap cap_net_bind_service=+ep /usr/bin/httpd" in hook


def test_root_script_guarded():
    script = (TEMPLATES / "root-setup.sh").read_text()
    assert "// xampp-linux" in script
    assert "grep -q" in script
    assert "AllowNoPassword" in script
