"""Diálogo de Ajustes: puertos, HTTPS, contraseña de root y regenerar configuraciones."""

from dataclasses import replace

from .ui import in_thread  # noqa: F401,I001  (fija versiones de GTK/Adw antes de importarlas)
from gi.repository import Adw, Gtk

from .config import Settings

PORTS = (
    ("http_port", "HTTP (Apache)"),
    ("https_port", "HTTPS (Apache)"),
    ("mariadb_port", "MariaDB"),
    ("smtp_port", "SMTP (Mailpit)"),
    ("mail_web_port", "Web de Mailpit"),
)

CONFIRM = ("Se regenerarán las configuraciones de ~/xampp/etc y se perderán "
           "los cambios hechos a mano. ¿Continuar?")


class SettingsDialog(Adw.PreferencesDialog):
    def __init__(self, settings: Settings, on_apply):
        """`on_apply(nuevos_ajustes)` se llama tras confirmar."""
        super().__init__(title="Ajustes")
        self._settings = settings
        self._on_apply = on_apply

        page = Adw.PreferencesPage()
        ports = Adw.PreferencesGroup(title="Puertos")
        self._spins = {}
        for field, title in PORTS:
            row = Adw.SpinRow.new_with_range(1, 65535, 1)
            row.set_title(title)
            row.set_value(getattr(settings, field))
            ports.add(row)
            self._spins[field] = row
        page.add(ports)

        other = Adw.PreferencesGroup(title="Opciones")
        self._https = Adw.SwitchRow(title="HTTPS en localhost", active=settings.https)
        other.add(self._https)
        self._password = Adw.PasswordEntryRow(title="Contraseña de root de MariaDB")
        self._password.set_text(settings.mariadb_root_password)
        other.add(self._password)
        page.add(other)

        buttons = Adw.PreferencesGroup()
        box = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        save = Gtk.Button(label="Guardar")
        save.add_css_class("suggested-action")
        save.add_css_class("pill")
        save.connect("clicked", lambda *_: self._confirm(self._collect()))
        regen = Gtk.Button(label="Regenerar configuraciones")
        regen.add_css_class("pill")
        regen.connect("clicked", lambda *_: self._confirm(self._settings))
        box.append(save)
        box.append(regen)
        buttons.add(box)
        page.add(buttons)
        self.add(page)

    def _collect(self) -> Settings:
        values = {field: int(row.get_value()) for field, row in self._spins.items()}
        return replace(self._settings, **values, https=self._https.get_active(),
                       mariadb_root_password=self._password.get_text())

    def _confirm(self, new: Settings) -> None:
        alert = Adw.AlertDialog(heading="Regenerar configuraciones", body=CONFIRM)
        alert.add_response("cancel", "Cancelar")
        alert.add_response("ok", "Continuar")
        alert.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_response(_d, response):
            if response == "ok":
                self.close()
                self._on_apply(new)

        alert.connect("response", on_response)
        alert.present(self)
