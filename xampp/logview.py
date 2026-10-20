"""Ventana que muestra un log y lo sigue en vivo."""

from .ui import in_thread  # noqa: F401,I001  (fija versiones de GTK/Adw antes de importarlas)
from gi.repository import Adw, Gio, GLib, Gtk

from .config import Paths
from .services import Service
from .tail import Follower, tail


class LogWindow(Adw.Window):
    def __init__(self, parent: Gtk.Window, paths: Paths, svc: Service):
        super().__init__(transient_for=parent, title=f"Log de {svc.name}",
                         default_width=820, default_height=520)
        self._files = [paths.logs / name for name in svc.logs]
        self._follower = None
        self._closed = False

        self.view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True,
                                 wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                 top_margin=8, bottom_margin=8, left_margin=8, right_margin=8)
        self.scroller = Gtk.ScrolledWindow(child=self.view, vexpand=True)

        header = Adw.HeaderBar()
        if len(self._files) > 1:
            chooser = Gtk.DropDown.new_from_strings([f.name for f in self._files])
            chooser.connect("notify::selected", lambda d, _: self._load(self._files[d.get_selected()]))
            header.pack_start(chooser)
        open_btn = Gtk.Button(label="Abrir archivo")
        open_btn.connect("clicked", self._open_file)
        header.pack_end(open_btn)

        view = Adw.ToolbarView(content=self.scroller)
        view.add_top_bar(header)
        self.set_content(view)
        self.connect("close-request", self._on_close)

        self._load(self._files[0])
        GLib.timeout_add(1000, self._poll)

    def _load(self, path) -> None:
        self._current = path
        text = tail(path) or f"(todavía no hay nada en {path})\n"
        self.view.get_buffer().set_text(text)
        self._follower = Follower(path)
        self._scroll_end()

    def _poll(self) -> bool:
        if self._closed:
            return False
        new = self._follower.read_new()
        if new:
            buf = self.view.get_buffer()
            buf.insert(buf.get_end_iter(), new)
            self._scroll_end()
        return True

    def _scroll_end(self) -> None:
        GLib.idle_add(lambda: self.view.scroll_to_iter(self.view.get_buffer().get_end_iter(), 0, False, 0, 0)
                      and False)

    def _open_file(self, *_):
        Gtk.FileLauncher(file=Gio.File.new_for_path(str(self._current))).launch(self, None, None)

    def _on_close(self, *_):
        self._closed = True
        return False
