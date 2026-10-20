"""Utilidades compartidas por las ventanas GTK."""

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib  # noqa: E402


def in_thread(work, done=None) -> None:
    """Ejecuta `work()` en un hilo y `done(resultado)` en el hilo de GTK."""

    def target():
        result = work()
        if done is not None:
            GLib.idle_add(lambda: (done(result), False)[1])

    threading.Thread(target=target, daemon=True).start()
