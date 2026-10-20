import subprocess
from pathlib import Path

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
    assert "otro usuario o por root" in describe(3306, Owner(None, None))
