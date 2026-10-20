from xampp.ui import error_result, in_thread
from gi.repository import GLib


def test_error_result_missing_binary():
    r = error_result(FileNotFoundError(2, "No such file or directory", "/usr/bin/httpd"))
    assert not r.ok
    assert "/usr/bin/httpd" in r.output and "xampp --setup" in r.output


def test_error_result_generic():
    r = error_result(PermissionError("denegado"))
    assert not r.ok and "PermissionError" in r.output and "denegado" in r.output


def test_in_thread_reports_exceptions():
    loop, got = GLib.MainLoop(), []

    def boom():
        raise RuntimeError("fallo")

    in_thread(boom, lambda r: (got.append(r), loop.quit()))
    GLib.timeout_add(2000, loop.quit)
    loop.run()
    assert got and not got[0].ok and "fallo" in got[0].output


def test_in_thread_custom_error_handler():
    loop, got = GLib.MainLoop(), []
    in_thread(lambda: 1 / 0, lambda r: got.append(("done", r)),
              on_error=lambda e: (got.append(("error", type(e).__name__)), loop.quit()))
    GLib.timeout_add(2000, loop.quit)
    loop.run()
    assert got == [("error", "ZeroDivisionError")]
