"""Ventana del asistente de primera instalación."""

from .ui import in_thread  # noqa: I001  (fija versiones de GTK/Adw antes de importarlas)
from gi.repository import Adw, Gtk

from .config import Paths, load_settings
from .setup import steps
from .systemd import Systemd


class SetupWindow(Adw.ApplicationWindow):
    def __init__(self, app, paths: Paths, on_done):
        super().__init__(application=app, title="Instalar XAMPP", default_width=560, default_height=620)
        self._on_done = on_done
        self._steps = steps(paths, load_settings(paths), Systemd())
        self._next = 0

        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(
            title="Instalación",
            description="Instala los paquetes, prepara ~/xampp y crea los servicios. "
                        "Pedirá tu contraseña una vez y abrirá una terminal para Mailpit y mkcert.",
        )
        page.add(group)

        self._rows = []
        for step in self._steps:
            row = Adw.ExpanderRow(title=step.title, subtitle="Pendiente")
            icon = Gtk.Image(icon_name="content-loading-symbolic")
            row.add_prefix(icon)
            output = Gtk.Label(wrap=True, selectable=True, xalign=0,
                               margin_top=6, margin_bottom=6, margin_start=12, margin_end=12)
            output.add_css_class("monospace")
            row.add_row(output)
            group.add(row)
            self._rows.append((row, icon, output))

        self._button = Gtk.Button(label="Instalar", halign=Gtk.Align.CENTER, margin_top=12)
        self._button.add_css_class("suggested-action")
        self._button.add_css_class("pill")
        self._button.connect("clicked", lambda *_: self._run_next())
        group_bottom = Adw.PreferencesGroup()
        group_bottom.add(self._button)
        page.add(group_bottom)

        view = Adw.ToolbarView(content=page)
        view.add_top_bar(Adw.HeaderBar())
        self.set_content(view)

    def _run_next(self) -> None:
        if self._next >= len(self._steps):
            self.close()
            self._on_done()
            return
        self._button.set_sensitive(False)
        step = self._steps[self._next]
        row, icon, _ = self._rows[self._next]
        row.set_subtitle("En curso…")
        icon.set_from_icon_name("emblem-synchronizing-symbolic")
        in_thread(step.fn, self._step_done)

    def _step_done(self, result) -> None:
        row, icon, output = self._rows[self._next]
        output.set_label(result.output or "(sin salida)")
        if result.ok:
            row.set_subtitle("Hecho")
            icon.set_from_icon_name("object-select-symbolic")
            icon.add_css_class("success")
            self._next += 1
            if self._next < len(self._steps):
                self._run_next()
                return
            self._button.set_label("Abrir XAMPP")
        else:
            row.set_subtitle("Error")
            row.set_expanded(True)
            icon.set_from_icon_name("dialog-error-symbolic")
            icon.add_css_class("error")
            self._button.set_label("Reintentar")
        self._button.set_sensitive(True)
