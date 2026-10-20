# xampp-linux — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Panel GTK4 tipo XAMPP que controla Apache, PHP-FPM, MariaDB y Mailpit como servicios systemd de usuario, con `~/xampp/htdocs`, HTTPS local y phpMyAdmin.

**Architecture:** Núcleo Python sin GUI (rutas/ajustes, plantillas, servicios, systemd, puertos, acciones, instalación) totalmente testeable con pytest y `subprocess` simulado; encima, una capa GTK4/libadwaita delgada que solo llama al núcleo. Los servicios son units en `~/.config/systemd/user/` que ejecutan los binarios de Arch con configuraciones generadas en `~/xampp/etc/`.

**Tech Stack:** Python 3.14, PyGObject (GTK 4.24, libadwaita 1.10), `string.Template`, pytest, systemd 262 (`--user`), Apache 2.4, PHP-FPM 8.5, MariaDB, Mailpit, mkcert.

**Spec:** `docs/superpowers/specs/2026-10-20-xampp-linux-design.md`

## Global Constraints

- Paquetes requeridos (repos): `apache php php-fpm php-gd mariadb phpmyadmin mkcert nss`; AUR: `mailpit-bin`.
- Binarios siempre por **ruta absoluta** (`/usr/bin/httpd`, `/usr/bin/php-fpm`, `/usr/bin/mariadbd`, `/usr/bin/mariadb-install-db`, `/usr/bin/mailpit`): Linuxbrew tiene otro `httpd` y `mysqld` en el PATH.
- Puertos por defecto: HTTP 80, HTTPS 443, MariaDB 3306, Mailpit SMTP 1025, Mailpit web 8025.
- Todo corre como el usuario; el único paso con root es un solo `pkexec` en la instalación.
- Raíz de datos `~/xampp/`, sobreescribible con la variable de entorno `XAMPP_HOME` (tests). Units en `~/.config/systemd/user/`, sobreescribible con `XAMPP_UNITS_DIR`.
- Nombres de units: `xampp-apache.service`, `xampp-php.service`, `xampp-mariadb.service`, `xampp-mail.service`.
- Textos de la interfaz en español.
- Root de MariaDB sin contraseña por defecto.
- Tests: `python -m pytest -q` desde la raíz del repo; ningún test unitario lanza procesos reales ni toca `~`.

## Review Focus

1. **Regenerar configuraciones con ediciones manuales**: guardar Ajustes sobreescribe `etc/`; el usuario debe confirmar antes y nunca se tocan `htdocs/` ni `data/`. → test `test_render_all_never_touches_htdocs_or_data` (Task 3) y diálogo de confirmación (Task 9).
2. **Puertos 80/443 ocupados por el httpd huérfano de FlyEnv** (u otro proceso de root sin PID visible): iniciar debe fallar con mensaje que nombre el puerto y el proceso si se conoce, sin llamar a systemctl. → `test_start_refuses_when_port_busy` y `test_parse_ss_without_process_info` (Tasks 4, 6).
3. **`htdocs/` con archivos del usuario al re-ejecutar la instalación**: la página de bienvenida solo se crea si `htdocs/` está vacío. → `test_welcome_page_only_when_htdocs_empty` (Task 3).
4. **`httpd.conf` editado a mano con un error**: no reiniciar; mostrar la salida de `httpd -t`. → `test_restart_apache_validates_first` (Task 6).
5. **HTTPS desactivado o certificado ausente**: con `https=False` no debe haber `Listen 443` ni `mod_ssl`; con `https=True` pero sin `ssl/localhost.pem`, renderizar sin HTTPS y avisar. → `test_httpd_conf_without_https`, `test_httpd_conf_https_requires_cert` (Task 3).

---

### Task 1: Esqueleto, rutas y ajustes

**Files:**
- Create: `xampp/__init__.py`, `xampp/config.py`, `tests/conftest.py`, `tests/test_config.py`, `.gitignore` (`__pycache__/`, `.pytest_cache/`)

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Paths: root, etc, logs, data, mysql, ssl, run, htdocs, units: Path` con `Paths.default() -> Paths` (lee `XAMPP_HOME` / `XAMPP_UNITS_DIR`) y `Paths.at(root: Path, units: Path) -> Paths`; `paths.ensure_dirs() -> None` crea todas salvo `units`.
  - `@dataclass class Settings: http_port=80, https_port=443, mariadb_port=3306, smtp_port=1025, mail_web_port=8025, https=True, mariadb_root_password=""`
  - `load_settings(paths) -> Settings` (defaults si no existe `etc/settings.json`; claves desconocidas ignoradas), `save_settings(paths, s) -> None`, `is_installed(paths) -> bool` (existe `settings.json`).
  - fixture pytest `paths` → `Paths.at(tmp_path/"xampp", tmp_path/"units")`.

- [ ] **Step 1:** Instalar pytest (lo ejecuta el usuario): `! sudo pacman -S --needed python-pytest`
- [ ] **Step 2: Tests que fallan** en `tests/test_config.py`:
  - `test_default_settings`: `load_settings(paths) == Settings()` y `Settings().http_port == 80`, `.https_port == 443`, `.mariadb_port == 3306`, `.smtp_port == 1025`, `.mail_web_port == 8025`.
  - `test_settings_roundtrip`: guardar `Settings(http_port=8080, https=False)` y recargar da lo mismo; `is_installed(paths)` pasa de False a True.
  - `test_unknown_keys_ignored`: un `settings.json` con `{"http_port": 81, "ftp": 1}` carga con `http_port == 81`.
  - `test_paths_from_env`: con `monkeypatch.setenv("XAMPP_HOME", str(tmp_path))`, `Paths.default().htdocs == tmp_path/"htdocs"` y `.mysql == tmp_path/"data"/"mysql"`.
- [ ] **Step 3:** `python -m pytest -q tests/test_config.py` → FAIL (ImportError).
- [ ] **Step 4:** Implementar `xampp/config.py` (JSON con `dataclasses.asdict`).
- [ ] **Step 5:** `python -m pytest -q` → PASS.
- [ ] **Step 6:** `git add -A && git commit -m "feat: rutas y ajustes"`

### Task 2: Definición de servicios

**Files:**
- Create: `xampp/services.py`, `tests/test_services.py`

**Interfaces:**
- Consumes: `Settings`.
- Produces:
  - `@dataclass(frozen=True) class Service: id: str; name: str; unit: str; logs: tuple[str, ...]  # relativos a paths.logs; config: str | None  # relativo a paths.etc; requires: tuple[str, ...]; def ports(self, s: Settings) -> list[int]`
  - `SERVICES: tuple[Service, ...]` en orden `apache, php, mariadb, mail`; `get(id: str) -> Service` (KeyError si no existe); `start_order(ids) -> list[str]` (dependencias primero, sin duplicados).

Valores: apache → name "Apache", logs `("apache-error.log","apache-access.log")`, config `"httpd.conf"`, requires `("php",)`, puertos `[http_port] + ([https_port] if s.https else [])`. php → "PHP-FPM", logs `("php-fpm.log","php-error.log")`, config `"php.ini"`, sin puertos. mariadb → "MariaDB", `("mariadb.log",)`, `"my.cnf"`, `[mariadb_port]`. mail → "Mailpit", `("mailpit.log",)`, config `None`, `[smtp_port, mail_web_port]`.

- [ ] **Step 1: Tests que fallan:** `test_apache_ports_with_and_without_https` (`[80,443]` / `[80]`), `test_units_named` (`get("mariadb").unit == "xampp-mariadb.service"`), `test_start_order` (`start_order(["apache","mariadb"]) == ["php","apache","mariadb"]`), `test_get_unknown_raises`.
- [ ] **Step 2:** `python -m pytest -q tests/test_services.py` → FAIL.
- [ ] **Step 3:** Implementar `xampp/services.py`.
- [ ] **Step 4:** `python -m pytest -q` → PASS.
- [ ] **Step 5:** `git commit -am "feat: definición de servicios"` (añadir archivos nuevos con `git add`).

### Task 3: Plantillas y render de configuraciones

**Files:**
- Create: `xampp/templates/{httpd.conf,httpd-ssl.conf,php-fpm.conf,php.ini,my.cnf,index.php}`, `xampp/templates/units/{xampp-apache,xampp-php,xampp-mariadb,xampp-mail}.service`, `tests/test_render.py`
- Modify: `xampp/config.py`

**Interfaces:**
- Consumes: `Paths`, `Settings`.
- Produces: `render_all(paths, s) -> list[str]` — escribe `etc/httpd.conf`, `etc/php-fpm.conf`, `etc/php.ini`, `etc/my.cnf` y las 4 units en `paths.units`; crea dirs; copia `index.php` a `htdocs/` solo si `htdocs/` está vacío; devuelve lista de avisos (p. ej. HTTPS pedido sin certificado). `https_effective(paths, s) -> bool` = `s.https` y existen `ssl/localhost.pem` y `ssl/localhost-key.pem`.

Plantillas con `string.Template` (`$root`, `$etc`, `$logs`, `$run`, `$htdocs`, `$mysql`, `$http_port`, `$https_port`, `$mariadb_port`, `$smtp_port`, `$mail_web_port`, `$ssl_block`). `$ssl_block` = contenido de `httpd-ssl.conf` (LoadModule `ssl_module` y `socache_shmcb_module`, `Listen $https_port`, `<VirtualHost *:$https_port>` con `SSLEngine on` y los pem) o cadena vacía.

Contenido que debe fijarse:
- `httpd.conf`: `ServerRoot "/etc/httpd"`, módulos de `/usr/lib/httpd/modules/` (`mpm_event authz_core unixd dir mime log_config alias rewrite setenvif headers proxy proxy_fcgi`), `Listen $http_port`, `ServerName localhost`, `PidFile $run/httpd.pid`, `DocumentRoot "$htdocs"` con `AllowOverride All` y `Require all granted`, `DirectoryIndex index.php index.html`, `<FilesMatch \.php$> SetHandler "proxy:unix:$run/php-fpm.sock|fcgi://localhost" </FilesMatch>`, `Alias /phpmyadmin "/usr/share/webapps/phpMyAdmin"` con su `<Directory>` (`Require all granted`), `ErrorLog $logs/apache-error.log`, `CustomLog $logs/apache-access.log combined`, `TypesConfig /etc/httpd/conf/mime.types`, `$ssl_block`.
- `php-fpm.conf`: `[global] error_log=$logs/php-fpm.log`, `pid=$run/php-fpm.pid`; pool `[www]` con `listen=$run/php-fpm.sock`, `pm=ondemand`, `pm.max_children=10`.
- `php.ini`: `extension=mysqli`, `pdo_mysql`, `intl`, `gd`, `iconv`; `display_errors=On`; `error_log=$logs/php-error.log`; `mysqli.default_socket=$run/mariadb.sock`; `pdo_mysql.default_socket=$run/mariadb.sock`; `mysqli.default_port=$mariadb_port`; `sendmail_path="/usr/bin/mailpit sendmail -S 127.0.0.1:$smtp_port"`; `upload_max_filesize=64M`, `post_max_size=64M`; `session.save_path=$run`.
- `my.cnf`: `[mysqld] datadir=$mysql`, `socket=$run/mariadb.sock`, `port=$mariadb_port`, `bind-address=127.0.0.1`, `log-error=$logs/mariadb.log`, `pid-file=$run/mariadb.pid`; `[client] socket=$run/mariadb.sock`.
- Units: `[Service] Type=simple`, `ExecStart` absoluto (ver spec, con `-c $etc/php.ini` para php-fpm y `mailpit --smtp 127.0.0.1:$smtp_port --listen 127.0.0.1:$mail_web_port`), `StandardOutput=append:$logs/<log>` y `StandardError=` igual para mailpit; apache con `Requires=xampp-php.service` y `After=xampp-php.service`; `[Install] WantedBy=default.target`.
- `index.php`: página de bienvenida con enlaces a `/phpmyadmin`, a `http://localhost:<mail_web_port>` y `phpinfo` en `?info`.

- [ ] **Step 1: Tests que fallan** (`tests/test_render.py`):
  - `test_render_all_writes_files`: tras `render_all`, existen los 4 archivos de `etc/` y las 4 units; ningún archivo contiene `$` seguido de un nombre de variable sin sustituir (`re.search(r"\$[a-z_]+", txt)` es None salvo en `php.ini`/`index.php` donde se excluye `$_`/código PHP — comprobar solo `etc/*.conf`, `my.cnf` y units).
  - `test_httpd_conf_paths`: contiene `DocumentRoot "<paths.htdocs>"`, `proxy:unix:<paths.run>/php-fpm.sock`, `Listen 80`, `Alias /phpmyadmin`.
  - `test_httpd_conf_without_https`: `Settings(https=False)` → sin `Listen 443` ni `ssl_module`.
  - `test_httpd_conf_https_requires_cert`: `https=True` sin pem → sin `Listen 443` y `render_all` devuelve un aviso que contiene "certificado"; con ambos pem creados → `Listen 443` y `SSLCertificateFile <paths.ssl>/localhost.pem`.
  - `test_custom_ports`: `Settings(http_port=8080, mariadb_port=3307, smtp_port=2025)` → `Listen 8080`, `port=3307`, `-S 127.0.0.1:2025`.
  - `test_apache_unit_requires_php`: unit apache contiene `Requires=xampp-php.service` y `ExecStart=/usr/bin/httpd -f <paths.etc>/httpd.conf -D FOREGROUND`.
  - `test_welcome_page_only_when_htdocs_empty`: htdocs vacío → aparece `index.php`; con `htdocs/mio.html` previo → no aparece `index.php`.
  - `test_render_all_never_touches_htdocs_or_data`: archivos previos en `htdocs/a.php` y `data/mysql/x` conservan contenido y mtime.
- [ ] **Step 2:** `python -m pytest -q tests/test_render.py` → FAIL.
- [ ] **Step 3:** Crear plantillas e implementar `render_all` / `https_effective` (plantillas leídas con `importlib.resources`).
- [ ] **Step 4:** `python -m pytest -q` → PASS.
- [ ] **Step 5:** Validación real de sintaxis (solo si `apache` ya está instalado; si no, se hace en Task 10): render a un tmp y `/usr/bin/httpd -t -f <tmp>/etc/httpd.conf` → `Syntax OK`.
- [ ] **Step 6:** Commit `feat: plantillas y render de configuraciones`.

### Task 4: Detección de puertos

**Files:**
- Create: `xampp/ports.py`, `tests/test_ports.py`, `tests/fixtures/ss.txt`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class Owner: pid: int | None; process: str | None`; `parse_ss(text: str) -> dict[int, Owner]`; `busy(ports: list[int], run=subprocess.run) -> dict[int, Owner]` (ejecuta `ss -ltnpH`, devuelve solo los pedidos que estén ocupados); `describe(port: int, owner: Owner) -> str` (p. ej. `"El puerto 80 está ocupado por httpd (PID 10026)"` o `"El puerto 80 está ocupado por otro usuario o por root"`).

- [ ] **Step 1: Fixture** `tests/fixtures/ss.txt` con salida `ss -ltnpH` real: una línea `*:80` con `users:(("httpd",pid=10026,fd=4),("httpd",pid=10050,fd=4))`, una `127.0.0.1:3306` sin columna de proceso, una `[::]:443`.
- [ ] **Step 2: Tests que fallan:** `test_parse_ss_with_process` (`80 → Owner(10026, "httpd")`, primer pid), `test_parse_ss_without_process_info` (`3306 → Owner(None, None)`), `test_parse_ipv6` (443 presente), `test_busy_filters` (run simulado devuelve el fixture; `busy([80, 8025]) == {80: Owner(10026,"httpd")}`), `test_describe_unknown_owner` (contiene "otro usuario o por root").
- [ ] **Step 3:** FAIL → implementar (regex `:(\d+)\s` sobre la columna local, `users:\(\("([^"]+)",pid=(\d+)`) → PASS.
- [ ] **Step 4:** Commit `feat: detección de puertos ocupados`.

### Task 5: Envoltorio de systemd

**Files:**
- Create: `xampp/systemd.py`, `tests/test_systemd.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class Result: ok: bool; output: str`; `class Systemd: __init__(self, run=subprocess.run)`; métodos `start(unit) -> Result`, `stop(unit) -> Result`, `restart(unit) -> Result`, `daemon_reload() -> Result`, `state(unit) -> str` (`"active" | "inactive" | "failed" | "activating" | "deactivating"`, cualquier otra salida → `"inactive"`), `journal(unit, lines=20) -> str`. Todas las llamadas usan `["systemctl", "--user", ...]` / `["journalctl", "--user", "-u", unit, "-n", str(lines), "--no-pager"]` con `capture_output=True, text=True`; `ok = returncode == 0`; `output = stdout + stderr` sin espacios finales.

- [ ] **Step 1: Tests que fallan** con un `run` falso que registra argumentos: `test_start_calls_systemctl_user` (args exactos `["systemctl","--user","start","xampp-apache.service"]`), `test_failed_result` (returncode 1 y stderr "boom" → `Result(False, "boom")`), `test_state_values` (stdout `"failed\n"` → `"failed"`; `"unknown\n"` → `"inactive"`), `test_journal_args`.
- [ ] **Step 2:** FAIL → implementar → PASS.
- [ ] **Step 3:** Commit `feat: envoltorio de systemctl --user`.

### Task 6: Acciones (iniciar, parar, reiniciar con validación)

**Files:**
- Create: `xampp/actions.py`, `tests/test_actions.py`

**Interfaces:**
- Consumes: `Service`, `get`, `start_order`, `Systemd`, `Result`, `busy`, `describe`, `Paths`, `Settings`.
- Produces: `class Controller: __init__(self, paths, settings, systemd: Systemd, busy_fn=ports.busy, run=subprocess.run)`; `check_ports(id) -> dict[int, Owner]` (puertos de `start_order([id])` no activos; los de Apache con `https=https_effective(paths, settings)`); `start(id) -> Result`, `stop(id) -> Result`, `restart(id) -> Result`, `start_all() -> Result`, `stop_all() -> Result`, `state(id) -> str`, `validate_apache() -> Result`.

Reglas:
- `start(id)`: `check_ports(id)`; si hay alguno → `Result(False, describe(...))` sin llamar a systemctl. Si `id == "apache"`, `validate_apache()` antes. Luego `systemd.start(svc.unit)`; si falla, `output` añade `systemd.journal(unit)`, y si el journal contiene `make_sock` y `Permission denied`, añade "Apache no tiene permiso para usar el puerto; ejecuta `xampp --setup` para volver a aplicarlo".
- `stop(id)`: `systemd.stop`. Parar `php` con Apache activo también para Apache (lo hace systemd por `Requires=`; no hace falta lógica extra).
- `restart("apache")`: `validate_apache()` primero; si falla, no reinicia.
- `validate_apache()`: `run(["/usr/bin/httpd", "-t", "-f", str(paths.etc/"httpd.conf")])` → `Result(returncode == 0, stderr)`.
- `start_all()` / `stop_all()`: todos en orden de `SERVICES` (stop en orden inverso); `ok` = todos ok; `output` = líneas `"<Nombre>: <output>"` de los que fallen.

- [ ] **Step 1: Tests que fallan** (Systemd y busy_fn falsos):
  - `test_start_refuses_when_port_busy`: busy_fn devuelve `{80: Owner(10026,"httpd")}` → `ok False`, output contiene `"80"` y `"httpd"`, y el falso de systemd no recibió `start`.
  - `test_start_apache_relies_on_systemd_deps`: apache y php inactivos, puertos libres, validación ok, HTTPS efectivo → llamadas a start == `["xampp-apache.service"]` (systemd arranca php por `Requires=`) y busy_fn consultado con `[80, 443]`.
  - `test_apache_ports_follow_effective_https`: `https=True` sin certificado → busy_fn consultado con `[80]`.
  - `test_missing_setcap_hint`: start falla y journal contiene `Permission denied: AH00072: make_sock` → output contiene `xampp --setup`.
  - `test_restart_apache_validates_first`: run falso para `httpd -t` devuelve returncode 1 y stderr `"Syntax error on line 3"` → `ok False`, output contiene `"line 3"`, sin `restart`.
  - `test_start_failure_includes_journal`: start devuelve `Result(False,"x")`, journal `"Address in use"` → output contiene ambos.
  - `test_start_all_reports_failures`: mariadb falla → `ok False` y output contiene `"MariaDB:"`.
- [ ] **Step 2:** FAIL → implementar → PASS (`python -m pytest -q`).
- [ ] **Step 3:** Commit `feat: controlador de servicios`.

### Task 7: Instalación (lógica sin GUI)

**Files:**
- Create: `xampp/setup.py`, `xampp/templates/xampp-setcap.hook`, `xampp/templates/root-setup.sh`, `tests/test_setup.py`

**Interfaces:**
- Consumes: `Paths`, `Settings`, `save_settings`, `render_all`, `Systemd`, `Result`.
- Produces:
  - `REPO_PACKAGES = ("apache","php","php-fpm","php-gd","mariadb","phpmyadmin","mkcert","nss")`, `AUR_PACKAGES = ("mailpit-bin",)`
  - `missing_packages(run=subprocess.run) -> list[str]` (usa `pacman -T <pkgs>`, que imprime los que faltan).
  - `@dataclass class Step: id: str; title: str; fn: Callable[[], Result]`; `steps(paths, settings, run=subprocess.run, systemd: Systemd) -> list[Step]` en este orden:
    1. `root` — "Paquetes y permisos (pide contraseña)": `pkexec /bin/sh <tmp>/root-setup.sh <paquetes faltantes de repo>`. `root-setup.sh`: `pacman -S --needed --noconfirm "$@"`; `setcap cap_net_bind_service=+ep /usr/bin/httpd`; instalar `/etc/pacman.d/hooks/xampp-setcap.hook`; en el `config.inc.php` de phpMyAdmin (ruta resuelta con `pacman -Ql phpmyadmin | grep config.inc.php`, normalmente `/etc/webapps/phpmyadmin/config.inc.php`) añadir, si no existe el marcador `// xampp-linux`, `$cfg['Servers'][1]['AllowNoPassword'] = true;` y `$cfg['blowfish_secret']` de 32 bytes (`sodium_hex2bin` de `openssl rand -hex 32`).
    2. `interactive` — "Mailpit y certificado raíz (terminal)": `kitty --title xampp-setup sh -c 'yay -S --needed mailpit-bin && mkcert -install; echo; read -p "Pulsa Enter para cerrar"'`; ok si después existe `/usr/bin/mailpit` y `mkcert -CAROOT`/`rootCA.pem`.
    3. `files` — "Carpetas y configuración": `paths.ensure_dirs()`, `save_settings` (solo si no existe), `render_all`.
    4. `cert` — "Certificado HTTPS": `mkcert -cert-file ssl/localhost.pem -key-file ssl/localhost-key.pem localhost 127.0.0.1 ::1`; después `render_all` de nuevo para activar HTTPS.
    5. `db` — "Base de datos": si `data/mysql/mysql` no existe, `/usr/bin/mariadb-install-db --datadir=<mysql> --auth-root-authentication-method=normal --skip-test-db`.
    6. `units` — "Servicios": `systemd.daemon_reload()`.
    7. `launcher` — "Acceso directo": copiar `bin/xampp` a `~/.local/bin/xampp` y `xampp.desktop` a `~/.local/share/applications/` (rutas base parametrizables para tests).
  - Cada paso es idempotente: ejecutarlo dos veces no falla ni duplica nada.

- [ ] **Step 1: Tests que fallan:**
  - `test_missing_packages_parses_pacman_T` (stdout `"mariadb\nmkcert\n"`, returncode 127 → `["mariadb","mkcert"]`; returncode 0 → `[]`).
  - `test_step_order` (ids `["root","interactive","files","cert","db","units","launcher"]`).
  - `test_files_step_idempotent` (dos ejecuciones ok; `settings.json` con `http_port=8080` previo no se sobreescribe).
  - `test_db_step_skips_when_initialized` (con `data/mysql/mysql/` existente no se llama a `mariadb-install-db`).
  - `test_hook_content`: la plantilla contiene `Target = apache`, `When = PostTransaction` y `Exec = /usr/bin/setcap cap_net_bind_service=+ep /usr/bin/httpd`.
  - `test_root_script_guarded`: `root-setup.sh` contiene `// xampp-linux` y `grep -q` antes de añadir (no duplica).
- [ ] **Step 2:** FAIL → implementar → PASS.
- [ ] **Step 3:** `sh -n xampp/templates/root-setup.sh` → sin salida.
- [ ] **Step 4:** Commit `feat: lógica de instalación`.

### Task 8: Ventana principal

**Files:**
- Create: `xampp/__main__.py`, `xampp/window.py`, `xampp/setup_window.py`

**Interfaces:**
- Consumes: `Controller`, `SERVICES`, `Paths.default`, `load_settings`, `is_installed`, `steps`.
- Produces: `class App(Adw.Application)` (id `io.github.pentabascal.Xampp`); `class MainWindow(Adw.ApplicationWindow)`; `class SetupWindow(Adw.ApplicationWindow)` con `on_done` callback; `main(argv) -> int`.

Comportamiento (spec, sección Interfaz):
- `__main__`: si `--setup` o `not is_installed(paths)` → `SetupWindow`; al terminar sin errores abre `MainWindow`.
- `SetupWindow`: lista de pasos (`Adw.ActionRow` con spinner → ✓/✗ y la salida en un expander); botón "Instalar" ejecuta los pasos en un hilo (`threading.Thread` + `GLib.idle_add` para actualizar la UI); se detiene en el primer fallo con botón "Reintentar".
- `MainWindow`: `Adw.ToolbarView` con header (botón ⚙), botones "Iniciar todo"/"Parar todo", un `Adw.PreferencesGroup` con una fila por servicio (punto de estado con clases CSS `success`/`dim-label`/`error`, puertos, botón Iniciar/Parar, Log, Cfg), botones rápidos (localhost con `https://` si `https_effective`, `/phpmyadmin`, `http://localhost:<mail_web_port>`, abrir `htdocs`) vía `Gtk.UriLauncher`/`Gtk.FileLauncher`, y un `Gtk.TextView` de solo lectura como registro con hora `HH:MM`.
- Las acciones del Controller se ejecutan en hilo; los fallos van al registro y a `Adw.Toast`.
- Antes de Iniciar, la ventana llama `check_ports(id)`; si un puerto tiene `Owner.pid` (proceso del usuario), el toast ofrece "Terminar proceso" → `os.kill(pid, SIGTERM)` y vuelve a intentar; si no hay PID, solo muestra `describe(...)`.
- Sondeo de estado cada 2 s con `GLib.timeout_add_seconds(2, ...)`.
- Log y Cfg quedan conectados en Task 9 (en esta tarea: botones presentes, deshabilitados).

- [ ] **Step 1:** Implementar los tres archivos.
- [ ] **Step 2:** `python -m pytest -q` sigue en PASS y `python -c "import xampp.window, xampp.setup_window"` sin errores.
- [ ] **Step 3: Verificación manual** con datos de prueba: `hyprctl dispatch exec "env XAMPP_HOME=/tmp/xampp-ui XAMPP_UNITS_DIR=/tmp/xampp-ui-units python -m xampp"` desde la raíz del repo (lanzar vía hyprctl, no desde Bash). Esperado: abre el asistente; con `settings.json` creado a mano abre el panel con 4 servicios en gris.
- [ ] **Step 4:** Commit `feat: ventana principal y asistente`.

### Task 9: Logs, editar configuración y Ajustes

**Files:**
- Create: `xampp/logview.py`, `xampp/settings_dialog.py`, `tests/test_tail.py`
- Modify: `xampp/window.py`

**Interfaces:**
- Produces: `tail(path: Path, lines: int = 500) -> str` y `class Follower: __init__(self, path); read_new() -> str` (devuelve lo añadido desde la última lectura; si el archivo se truncó, vuelve a empezar) en `logview.py`; `class LogWindow(Adw.Window)` (selector de archivo si el servicio tiene varios logs, sondeo 1 s, autoscroll, botón "Abrir archivo"); `class SettingsDialog(Adw.PreferencesDialog)`.

Comportamiento:
- **Cfg**: guarda `mtime`, abre con `Gtk.FileLauncher`; cuando la ventana vuelve a estar activa (`notify::is-active`) y el `mtime` cambió → toast "Configuración de X modificada" con botón "Reiniciar" → `Controller.restart(id)` (Apache valida antes).
- **Ajustes**: campos `Adw.SpinRow` para los 5 puertos (1–65535), `Adw.SwitchRow` HTTPS, `Adw.PasswordEntryRow` root de MariaDB; botón "Guardar" → `Adw.AlertDialog` "Se regenerarán las configuraciones de ~/xampp/etc y se perderán los cambios hechos a mano. ¿Continuar?" → `save_settings` + `render_all` + `daemon_reload` + avisos de `render_all` al registro + toast "Reinicia los servicios para aplicar los cambios". Si cambió la contraseña de root y MariaDB está activo: `mariadb -uroot [-p<anterior>] -S <run>/mariadb.sock -e "ALTER USER 'root'@'localhost' IDENTIFIED BY '<nueva>'"`; si MariaDB está parado, no guardar la contraseña y avisar "Inicia MariaDB para cambiar la contraseña".
- Botón "Regenerar configuraciones" en Ajustes: misma confirmación y mismo flujo sin cambiar ajustes.

- [ ] **Step 1: Tests que fallan** (`tests/test_tail.py`): `test_tail_last_lines` (archivo de 1000 líneas → 500 últimas), `test_tail_missing_file` (devuelve `""`), `test_follower_reads_appended`, `test_follower_handles_truncate`.
- [ ] **Step 2:** FAIL → implementar `tail`/`Follower` → PASS.
- [ ] **Step 3:** Implementar `LogWindow`, `SettingsDialog` y conectar Log/Cfg en `window.py`.
- [ ] **Step 4: Verificación manual** como en Task 8: Log abre y sigue un archivo al que se añaden líneas con `echo x >> /tmp/xampp-ui/logs/apache-error.log`; cambiar el puerto HTTP a 8081 y guardar regenera `etc/httpd.conf` con `Listen 8081` tras confirmar.
- [ ] **Step 5:** Commit `feat: logs, edición de configuración y ajustes`.

### Task 10: Lanzador, instalación real y prueba E2E

**Files:**
- Create: `bin/xampp`, `xampp.desktop`, `tests/e2e.sh`, `README.md` (breve, en español: instalar, abrir, dónde está htdocs)

**Interfaces:**
- `bin/xampp`: `#!/bin/sh` que hace `exec python3 -m xampp "$@"` con `PYTHONPATH` apuntando al repo (ruta absoluta resuelta al instalar: el paso `launcher` de Task 7 escribe la ruta real del repo).
- `xampp.desktop`: `Name=XAMPP`, `Exec=xampp`, `Icon=network-server`, `Categories=Development;`.
- `tests/e2e.sh` (bash, `set -euo pipefail`, sale ≠0 al primer fallo, imprime ✓/✗ por comprobación):
  1. `systemctl --user start xampp-apache xampp-mariadb xampp-mail`
  2. `curl -fsS http://localhost/` → 200
  3. escribe `~/xampp/htdocs/_e2e.php` con `<?php echo 6*7;` → `curl` devuelve `42`; lo borra al final (trap)
  4. `curl -fsS http://localhost/phpmyadmin/` contiene `phpMyAdmin`
  5. `curl -fsS https://localhost/` (sin `-k`) → 200
  6. `_e2e_mail.php` con `mail('a@b.c','e2e','x')` → `curl -s http://localhost:8025/api/v1/messages` contiene `e2e`
  7. `mariadb -uroot -S ~/xampp/run/mariadb.sock -e 'SELECT 1'` → `1`

- [ ] **Step 1:** Crear los archivos; `bash -n tests/e2e.sh`.
- [ ] **Step 2:** Antes de instalar: parar el httpd huérfano de FlyEnv. Comprobar con `ss -ltnp | grep -E ':(80|443) '`; si es de FlyEnv, `pkill -f FlyEnv/server/apache` (pedir confirmación al usuario antes).
- [ ] **Step 3:** El usuario ejecuta la instalación real: `hyprctl dispatch exec "python3 -m xampp --setup"` desde el repo (necesita la contraseña de pkexec y el terminal de yay). Esperado: los 7 pasos en ✓.
- [ ] **Step 4:** `/usr/bin/httpd -t -f ~/xampp/etc/httpd.conf` → `Syntax OK`; `getcap /usr/bin/httpd` → `cap_net_bind_service=ep`.
- [ ] **Step 5:** `bash tests/e2e.sh` → las 7 comprobaciones ✓. Si alguna falla, depurar con superpowers:systematic-debugging y corregir en la tarea correspondiente (plantillas casi siempre).
- [ ] **Step 6:** Prueba manual en el panel: Parar todo / Iniciar todo; ocupar el 3306 (`python3 -m http.server 3306`) e intentar iniciar MariaDB → mensaje con "3306" y "python3".
- [ ] **Step 7:** Commit `feat: lanzador y prueba e2e`.
