from fakes import FakeRun

from xampp.systemd import Result, Systemd


def test_start_calls_systemctl_user():
    run = FakeRun()
    assert Systemd(run).start("xampp-apache.service") == Result(True, "")
    assert run.calls == [["systemctl", "--user", "start", "xampp-apache.service"]]


def test_stop_restart_reload_args():
    run = FakeRun()
    sd = Systemd(run)
    sd.stop("u")
    sd.restart("u")
    sd.daemon_reload()
    assert run.calls == [
        ["systemctl", "--user", "stop", "u"],
        ["systemctl", "--user", "restart", "u"],
        ["systemctl", "--user", "daemon-reload"],
    ]


def test_failed_result():
    run = FakeRun({"systemctl --user start": (1, "", "boom\n")})
    assert Systemd(run).start("u") == Result(False, "boom")


def test_state_values():
    assert Systemd(FakeRun({"systemctl": (3, "failed\n", "")})).state("u") == "failed"
    assert Systemd(FakeRun({"systemctl": (0, "active\n", "")})).state("u") == "active"
    assert Systemd(FakeRun({"systemctl": (4, "unknown\n", "")})).state("u") == "inactive"


def test_state_args():
    run = FakeRun()
    Systemd(run).state("u")
    assert run.calls == [["systemctl", "--user", "is-active", "u"]]


def test_journal_args():
    run = FakeRun({"journalctl": (0, "linea\n", "")})
    assert Systemd(run).journal("u", lines=5) == "linea"
    assert run.calls == [["journalctl", "--user", "-u", "u", "-n", "5", "--no-pager"]]
