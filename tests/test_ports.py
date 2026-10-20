import subprocess
from pathlib import Path

from fakes import FakeRun

from xampp.ports import Owner, busy, describe, parse_ss

SS = (Path(__file__).parent / "fixtures" / "ss.txt").read_text()


def test_parse_ss_with_process():
    assert parse_ss(SS)[80] == Owner(10026, "httpd")


def test_parse_ss_without_process_info():
    assert parse_ss(SS)[3306] == Owner(None, None)


def test_parse_ipv6_and_scoped():
    ports = parse_ss(SS)
    assert ports[443] == Owner(10026, "httpd")
    assert 53 in ports


def test_busy_filters():
    calls = []

    def run(args, **kw):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, SS, "")

    assert busy([80, 8025], run=run) == {80: Owner(10026, "httpd")}
    assert calls == [["ss", "-ltnpH"]]


def test_describe():
    assert describe(80, Owner(10026, "httpd")) == "El puerto 80 está ocupado por httpd (PID 10026)"
    unknown = describe(3306, Owner(None, None))
    assert "no se puede identificar" in unknown and "sudo ss -ltnp" in unknown
    assert "root" not in unknown.split("(")[0]


def test_describe_guessed_owner():
    assert "probablemente" in describe(80, Owner(10026, "httpd", guessed=True))


def test_busy_guesses_own_httpd_when_ss_hides_process():
    # httpd con setcap no es "dumpable": ss no muestra su proceso aunque sea nuestro
    ss = "LISTEN 0 511 *:80 *:*\n"
    run = FakeRun({"ss": (0, ss, ""), "pgrep": (0, "10026\n", "")})
    assert busy([80], run=run) == {80: Owner(10026, "httpd", guessed=True)}
    pgrep = [c for c in run.calls if c[0] == "pgrep"][0]
    assert pgrep[:2] == ["pgrep", "-u"] and pgrep[-2:] == ["-x", "httpd"]


def test_busy_unknown_when_no_own_httpd():
    run = FakeRun({"ss": (0, "LISTEN 0 511 *:80 *:*\n", ""), "pgrep": (1, "", "")})
    assert busy([80], run=run) == {80: Owner(None, None)}
