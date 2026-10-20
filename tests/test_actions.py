from fakes import FakeRun

from xampp.actions import Controller
from xampp.config import Settings
from xampp.ports import Owner
from xampp.systemd import Result


class FakeSystemd:
    def __init__(self, states=None, fail=None, journal=""):
        self.states = states or {}
        self.fail = fail or {}
        self.calls = []
        self._journal = journal

    def _do(self, verb, unit):
        self.calls.append((verb, unit))
        return self.fail.get(unit, Result(True, ""))

    def start(self, unit):
        return self._do("start", unit)

    def stop(self, unit):
        return self._do("stop", unit)

    def restart(self, unit):
        return self._do("restart", unit)

    def daemon_reload(self):
        return Result(True, "")

    def state(self, unit):
        return self.states.get(unit, "inactive")

    def journal(self, unit, lines=20):
        return self._journal


class FakeBusy:
    def __init__(self, result=None):
        self.result = result or {}
        self.asked = []

    def __call__(self, ports):
        self.asked.append(list(ports))
        return {p: o for p, o in self.result.items() if p in ports}


def _cert(paths):
    paths.ssl.mkdir(parents=True, exist_ok=True)
    (paths.ssl / "localhost.pem").write_text("c")
    (paths.ssl / "localhost-key.pem").write_text("k")


def make(paths, settings=None, sd=None, busy=None, run=None):
    return Controller(paths, settings or Settings(), sd or FakeSystemd(),
                      busy_fn=busy or FakeBusy(), run=run or FakeRun())


def test_start_refuses_when_port_busy(paths):
    sd = FakeSystemd()
    c = make(paths, sd=sd, busy=FakeBusy({80: Owner(10026, "httpd")}))
    r = c.start("apache")
    assert not r.ok
    assert "80" in r.output and "httpd" in r.output
    assert not any(v == "start" for v, _ in sd.calls)


def test_check_ports_returns_owners(paths):
    c = make(paths, busy=FakeBusy({3306: Owner(5, "python3")}))
    assert c.check_ports("mariadb") == {3306: Owner(5, "python3")}


def test_start_apache_relies_on_systemd_deps(paths):
    _cert(paths)
    sd, busy = FakeSystemd(), FakeBusy()
    assert make(paths, sd=sd, busy=busy).start("apache").ok
    assert sd.calls == [("start", "xampp-apache.service")]
    assert [80, 443] in busy.asked


def test_apache_ports_follow_effective_https(paths):
    busy = FakeBusy()
    make(paths, busy=busy).start("apache")
    assert [80] in busy.asked and [80, 443] not in busy.asked


def test_active_services_ports_not_checked(paths):
    sd = FakeSystemd(states={"xampp-mariadb.service": "active"})
    busy = FakeBusy({3306: Owner(1, "mariadbd")})
    assert make(paths, sd=sd, busy=busy).start("mariadb").ok


def test_restart_apache_validates_first(paths):
    run = FakeRun({"/usr/bin/httpd -t": (1, "", "Syntax error on line 3\n")})
    sd = FakeSystemd()
    r = make(paths, sd=sd, run=run).restart("apache")
    assert not r.ok and "line 3" in r.output
    assert sd.calls == []
    assert run.calls[0] == ["/usr/bin/httpd", "-t", "-f", str(paths.etc / "httpd.conf")]


def test_start_apache_validates_first(paths):
    run = FakeRun({"/usr/bin/httpd -t": (1, "", "Syntax error\n")})
    sd = FakeSystemd()
    assert not make(paths, sd=sd, run=run).start("apache").ok
    assert sd.calls == []


def test_start_failure_includes_journal(paths):
    sd = FakeSystemd(fail={"xampp-mariadb.service": Result(False, "x")}, journal="Address in use")
    r = make(paths, sd=sd).start("mariadb")
    assert not r.ok and "x" in r.output and "Address in use" in r.output


def test_missing_setcap_hint(paths):
    sd = FakeSystemd(fail={"xampp-apache.service": Result(False, "fallo")},
                     journal="(13)Permission denied: AH00072: make_sock: could not bind to address [::]:80")
    r = make(paths, sd=sd).start("apache")
    assert "xampp --setup" in r.output


def test_start_all_reports_failures(paths):
    sd = FakeSystemd(fail={"xampp-mariadb.service": Result(False, "no arranca")})
    r = make(paths, sd=sd).start_all()
    assert not r.ok and "MariaDB:" in r.output
    assert ("start", "xampp-mail.service") in sd.calls


def test_stop_all_reverse_order(paths):
    sd = FakeSystemd()
    assert make(paths, sd=sd).stop_all().ok
    assert [u for _, u in sd.calls] == [
        "xampp-mail.service", "xampp-mariadb.service", "xampp-php.service", "xampp-apache.service"]


def test_change_root_password_requires_running_mariadb(paths):
    run = FakeRun()
    r = make(paths, run=run).change_root_password("", "nueva")
    assert not r.ok and "Inicia MariaDB" in r.output
    assert run.calls == []


def test_change_root_password_runs_alter_user(paths):
    run = FakeRun()
    sd = FakeSystemd(states={"xampp-mariadb.service": "active"})
    assert make(paths, sd=sd, run=run).change_root_password("vieja", "o'k\\")
    args = run.calls[0]
    assert args[:4] == ["/usr/bin/mariadb", "-uroot", "-S", str(paths.run / "mariadb.sock")]
    assert args[-1] == "ALTER USER 'root'@'localhost' IDENTIFIED BY 'o\\'k\\\\'"
    assert "vieja" not in " ".join(args)


def test_change_root_password_passes_old_via_env(paths):
    seen = {}

    def run(args, **kw):
        seen.update(kw.get("env") or {})
        import subprocess
        return subprocess.CompletedProcess(args, 0, "", "")

    sd = FakeSystemd(states={"xampp-mariadb.service": "active"})
    make(paths, sd=sd, run=run).change_root_password("vieja", "nueva")
    assert seen.get("MYSQL_PWD") == "vieja"
