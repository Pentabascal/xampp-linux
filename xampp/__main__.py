"""Punto de entrada: `python -m xampp [--setup]`."""

import sys

from . import ui  # noqa: F401  (fija las versiones de GTK/Adw)
from gi.repository import Adw  # noqa: E402

from .config import Paths, is_installed  # noqa: E402


class App(Adw.Application):
    def __init__(self, force_setup: bool):
        super().__init__(application_id="io.github.pentabascal.Xampp")
        self.force_setup = force_setup
        self.paths = Paths.default()

    def do_activate(self):
        win = self.get_active_window()
        if win:
            win.present()
            return
        if self.force_setup or not is_installed(self.paths):
            from .setup_window import SetupWindow
            self.force_setup = False
            SetupWindow(self, self.paths, self._open_main).present()
        else:
            self._open_main()

    def _open_main(self):
        from .window import MainWindow
        MainWindow(self, self.paths).present()


def main(argv: list[str]) -> int:
    force = "--setup" in argv
    return App(force).run([a for a in argv if a != "--setup"][:1])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
