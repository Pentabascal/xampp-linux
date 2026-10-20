"""Utilidades compartidas por las ventanas GTK."""

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gio, GLib  # noqa: E402

from .systemd import error_result  # noqa: E402,F401


def in_thread(work, done=None, on_error=None) -> None:
    """Ejecuta `work()` en un hilo y `done(resultado)` en el hilo de GTK.

    Si `work()` lanza una excepción se llama a `on_error(e)`; por defecto,
    a `done(error_result(e))`, para que la interfaz nunca se quede esperando.
    """

    def target():
        try:
            result = work()
        except Exception as e:
            exc = e  # `e` deja de existir al salir del except
            handler = on_error or (lambda e: done and done(error_result(e)))
            GLib.idle_add(lambda: (handler(exc), False)[1])
            return
        if done is not None:
            GLib.idle_add(lambda: (done(result), False)[1])

    threading.Thread(target=target, daemon=True).start()


def show_folder(path, fallback) -> None:
    """Abre `path` en el explorador de archivos (org.freedesktop.FileManager1).

    El tipo por defecto de las carpetas puede ser una terminal (kitty-open), así
    que se pide al explorador directamente; si no hay ninguno, `fallback()`.
    """

    def done(bus, res):
        try:
            bus.call_finish(res)
        except GLib.Error:
            fallback()

    Gio.bus_get_sync(Gio.BusType.SESSION).call(
        "org.freedesktop.FileManager1", "/org/freedesktop/FileManager1",
        "org.freedesktop.FileManager1", "ShowFolders",
        GLib.Variant("(ass)", ([Gio.File.new_for_path(str(path)).get_uri()], "")),
        None, Gio.DBusCallFlags.NONE, 5000, None, done,
    )
