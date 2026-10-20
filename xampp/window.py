"""Ventana principal: estado y control de los servicios."""

import os
import signal
import time

from .ui import error_result, in_thread, show_folder  # noqa: I001  (fija versiones de GTK/Adw antes de importarlas)
from gi.repository import Adw, Gio, GLib, Gtk

from . import ports
from .actions import Controller
from .config import Paths, Settings, https_effective, load_settings, render_all, save_settings
from .logview import LogWindow
from .services import SERVICES, Service
from .settings_dialog import SettingsDialog
from .systemd import Systemd

STATE_CLASS = {"active": "success", "failed": "error"}
STATE_TEXT = {"active": "Activo", "failed": "Error", "activating": "Iniciando…",
              "deactivating": "Parando…", "inactive": "Parado"}


class ServiceRow(Adw.ActionRow):
    def __init__(self, window: "MainWindow", svc: Service):
        super().__init__(title=svc.name)
        self.svc = svc
        self.state = "inactive"
        self.dot = Gtk.Label(label="●")
        self.add_prefix(self.dot)

        self.toggle = Gtk.Button(label="Iniciar", valign=Gtk.Align.CENTER, width_request=80)
        self.toggle.connect("clicked", lambda *_: window.toggle(self))
        self.log = Gtk.Button(icon_name="text-x-generic-symbolic", tooltip_text="Ver log",
                              valign=Gtk.Align.CENTER)
        self.log.connect("clicked", lambda *_: LogWindow(window, window.paths, svc).present())
        self.cfg = Gtk.Button(icon_name="document-edit-symbolic", tooltip_text="Editar configuración",
                              valign=Gtk.Align.CENTER)
        self.cfg.connect("clicked", lambda *_: window.edit_config(svc))
        for b in (self.log, self.cfg):
            b.add_css_class("flat")
        self.add_suffix(self.toggle)
        self.add_suffix(self.log)
        self.add_suffix(self.cfg)
        if not svc.config:  # hueco invisible para alinear los botones
            self.cfg.set_opacity(0)
            self.cfg.set_can_target(False)

    def set_state(self, state: str, ports_text: str) -> None:
        self.state = state
        for cls in ("success", "error", "dim-label"):
            self.dot.remove_css_class(cls)
        self.dot.add_css_class(STATE_CLASS.get(state, "dim-label"))
        self.set_subtitle(f"{STATE_TEXT.get(state, state)} · {ports_text}")
        self.toggle.set_label("Parar" if state == "active" else "Iniciar")
        if state == "active":
            self.toggle.remove_css_class("suggested-action")
        else:
            self.toggle.add_css_class("suggested-action")


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app, paths: Paths):
        super().__init__(application=app, title="XAMPP", default_width=640, default_height=720)
        self.paths = paths
        self._polling = False
        self._edited: dict[str, float] = {}  # servicio → mtime del config al abrirlo
        self.reload_settings()
        self.connect("notify::is-active", self._check_edited)

        self.toasts = Adw.ToastOverlay()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18,
                      margin_top=18, margin_bottom=18, margin_start=12, margin_end=12)

        actions = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        start_all = Gtk.Button(label="Iniciar todo")
        start_all.add_css_class("suggested-action")
        start_all.add_css_class("pill")
        start_all.connect("clicked", lambda *_: self._run_all(self.controller.start_all, "Iniciar todo"))
        stop_all = Gtk.Button(label="Parar todo")
        stop_all.add_css_class("pill")
        stop_all.connect("clicked", lambda *_: self._run_all(self.controller.stop_all, "Parar todo"))
        actions.append(start_all)
        actions.append(stop_all)
        box.append(actions)

        group = Adw.PreferencesGroup(title="Servicios")
        self.rows = {svc.id: ServiceRow(self, svc) for svc in SERVICES}
        for row in self.rows.values():
            group.add(row)
        box.append(group)

        links = Adw.PreferencesGroup(title="Accesos")
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4,
                           column_spacing=8, row_spacing=8, homogeneous=True)
        for label, icon, cb in (
            ("localhost", "network-server-symbolic", self._open_site),
            ("phpMyAdmin", "drive-multidisk-symbolic", lambda *_: self._open_uri(self._base() + "/phpmyadmin/")),
            ("Correo", "mail-unread-symbolic",
             lambda *_: self._open_uri(f"http://localhost:{self.settings.mail_web_port}/")),
            ("htdocs", "folder-symbolic", self._open_htdocs),
        ):
            content = Adw.ButtonContent(label=label, icon_name=icon)
            b = Gtk.Button(child=content)
            b.connect("clicked", cb)
            flow.append(b)
        links.add(flow)
        box.append(links)

        log_group = Adw.PreferencesGroup(title="Registro")
        self.log_view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True,
                                     wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                     top_margin=8, bottom_margin=8, left_margin=8, right_margin=8)
        scroller = Gtk.ScrolledWindow(child=self.log_view, min_content_height=140)
        scroller.add_css_class("card")
        log_group.add(scroller)
        box.append(log_group)

        clamp = Adw.Clamp(child=box, maximum_size=720)
        self.toasts.set_child(Gtk.ScrolledWindow(child=clamp, hscrollbar_policy=Gtk.PolicyType.NEVER))

        header = Adw.HeaderBar()
        self.settings_button = Gtk.Button(icon_name="emblem-system-symbolic", tooltip_text="Ajustes")
        self.settings_button.connect(
            "clicked", lambda *_: SettingsDialog(self.settings, self.apply_settings).present(self))
        header.pack_end(self.settings_button)
        view = Adw.ToolbarView(content=self.toasts)
        view.add_top_bar(header)
        self.set_content(view)

        self._poll()
        GLib.timeout_add_seconds(2, self._poll)

    # --- estado -----------------------------------------------------------

    def reload_settings(self) -> None:
        self.settings = load_settings(self.paths)
        self.controller = Controller(self.paths, self.settings, Systemd())

    def _ports_text(self, svc: Service) -> str:
        if svc.id == "php":
            return "socket"
        s = self.settings
        if svc.id == "apache":
            return ", ".join(map(str, [s.http_port] + ([s.https_port] if https_effective(self.paths, s) else [])))
        return ", ".join(map(str, svc.ports(s)))

    def _poll(self) -> bool:
        if not self._polling:
            self._polling = True
            in_thread(lambda: {id: self.controller.state(id) for id in self.rows}, self._apply_states,
                      on_error=self._poll_failed)
        return True

    def _poll_failed(self, e: Exception) -> None:
        self._polling = False
        self.log(f"No se pudo leer el estado: {error_result(e).output}")

    def _apply_states(self, states: dict) -> None:
        self._polling = False
        for id, state in states.items():
            self.rows[id].set_state(state, self._ports_text(self.rows[id].svc))

    # --- registro y avisos ------------------------------------------------

    def log(self, text: str) -> None:
        buf = self.log_view.get_buffer()
        for line in text.splitlines() or [""]:
            buf.insert(buf.get_end_iter(), f"{time.strftime('%H:%M')} {line}\n")
        self.log_view.scroll_to_iter(buf.get_end_iter(), 0, False, 0, 0)

    def toast(self, text: str, button: str | None = None, on_click=None) -> None:
        t = Adw.Toast(title=GLib.markup_escape_text(text.splitlines()[0]), timeout=5)
        if button:
            t.set_button_label(button)
            t.connect("button-clicked", lambda *_: on_click())
        self.toasts.add_toast(t)

    def report(self, what: str, result) -> None:
        if result.ok:
            self.log(f"{what}: hecho")
        else:
            self.log(f"{what}: error\n{result.output}")
            self.toast(f"{what}: {result.output}")
        self._poll()

    # --- acciones -----------------------------------------------------------

    def toggle(self, row: ServiceRow) -> None:
        svc = row.svc
        row.toggle.set_sensitive(False)

        def done(result, what):
            row.toggle.set_sensitive(True)
            self.report(what, result)

        if row.state == "active":
            in_thread(lambda: self.controller.stop(svc.id), lambda r: done(r, f"Parar {svc.name}"))
            return

        def check():
            taken = self.controller.check_ports(svc.id)
            return taken, (None if taken else self.controller.start(svc.id))

        def checked(res):
            taken, result = res
            if result is not None:
                done(result, f"Iniciar {svc.name}")
                return
            row.toggle.set_sensitive(True)
            self._port_conflict(svc, taken)

        in_thread(check, checked, on_error=lambda e: done(error_result(e), f"Iniciar {svc.name}"))

    def _port_conflict(self, svc: Service, taken: dict) -> None:
        msg = "\n".join(ports.describe(p, o) for p, o in taken.items())
        self.log(f"Iniciar {svc.name}: error\n{msg}")
        pids = {o.pid for o in taken.values() if o.pid}
        if not pids:
            self.toast(msg)
            return

        def kill():
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                except PermissionError as e:
                    self.log(f"No se pudo terminar el PID {pid}: {e}")
            self.log(f"Procesos terminados: {', '.join(map(str, sorted(pids)))}")
            GLib.timeout_add(800, lambda: (self.toggle(self.rows[svc.id]), False)[1])

        self.toast(msg, "Terminar proceso", kill)

    def _run_all(self, fn, what: str) -> None:
        self.log(f"{what}…")
        in_thread(fn, lambda r: self.report(what, r))

    # --- configuración ------------------------------------------------------

    def _config_path(self, svc: Service):
        return self.paths.etc / svc.config

    def edit_config(self, svc: Service) -> None:
        path = self._config_path(svc)
        self._edited[svc.id] = path.stat().st_mtime if path.exists() else 0
        Gtk.FileLauncher(file=Gio.File.new_for_path(str(path))).launch(self, None, None)

    def _check_edited(self, *_):
        if not self.is_active():
            return
        for id, mtime in list(self._edited.items()):
            svc = self.rows[id].svc
            path = self._config_path(svc)
            if path.exists() and path.stat().st_mtime != mtime:
                del self._edited[id]
                self.log(f"Configuración de {svc.name} modificada")
                self.toast(f"Configuración de {svc.name} modificada", "Reiniciar",
                           lambda svc=svc: self._restart(svc))

    def _restart(self, svc: Service) -> None:
        in_thread(lambda: self.controller.restart(svc.id),
                  lambda r: self.report(f"Reiniciar {svc.name}", r))

    def apply_settings(self, new: Settings) -> None:
        old = self.settings

        def work():
            notes = []
            if new.mariadb_root_password != old.mariadb_root_password:
                r = self.controller.change_root_password(old.mariadb_root_password,
                                                         new.mariadb_root_password)
                if r.ok:
                    notes.append("Contraseña de root de MariaDB cambiada")
                else:
                    notes.append(f"No se cambió la contraseña de root: {r.output}")
                    new.mariadb_root_password = old.mariadb_root_password
            save_settings(self.paths, new)
            notes += render_all(self.paths, new)
            reload = self.controller.systemd.daemon_reload()
            if not reload.ok:
                notes.append(reload.output)
            return notes

        def done(notes):
            self.reload_settings()
            for n in notes:
                self.log(n)
            self.log("Configuraciones regeneradas")
            self.toast("Reinicia los servicios para aplicar los cambios")
            self._poll()

        in_thread(work, done, on_error=lambda e: self.report("Guardar ajustes", error_result(e)))

    # --- accesos ------------------------------------------------------------

    def _base(self) -> str:
        s = self.settings
        if https_effective(self.paths, s):
            return "https://localhost" + ("" if s.https_port == 443 else f":{s.https_port}")
        return "http://localhost" + ("" if s.http_port == 80 else f":{s.http_port}")

    def _open_site(self, *_):
        self._open_uri(self._base() + "/")

    def _open_uri(self, uri: str) -> None:
        Gtk.UriLauncher(uri=uri).launch(self, None, None)

    def _open_htdocs(self, *_):
        self.paths.htdocs.mkdir(parents=True, exist_ok=True)
        show_folder(self.paths.htdocs, lambda: Gtk.FileLauncher(
            file=Gio.File.new_for_path(str(self.paths.htdocs))).launch(self, None, None))
