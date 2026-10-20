# xampp-linux — Diseño

Fecha: 2026-10-20

## Objetivo

Un panel de control tipo XAMPP para Arch Linux + Hyprland, para uso personal en
desarrollo local. Debe ser **simple**: botones Start/Stop, una carpeta `htdocs`
donde los `.php` funcionan sin crear hosts, y acceso directo a phpMyAdmin, logs
y configuración.

Motivo: FlyEnv resultó demasiado complejo; el XAMPP oficial se actualiza poco.

## Decisiones tomadas

| Tema | Decisión |
|---|---|
| Origen de los binarios | Paquetes de Arch (pacman), no binarios propios ni FlyEnv |
| Puertos | Estándar: Apache 80/443, MariaDB 3306, FTP 21, Mailpit SMTP 1025 / web 8025 |
| Privilegios | Todo corre como el usuario; `setcap cap_net_bind_service` en `httpd` y `vsftpd`, re-aplicado por un hook de pacman |
| Arquitectura | Servicios **systemd de usuario**; la GUI solo los controla con `systemctl --user` |
| GUI | Python 3 + GTK4 + libadwaita (PyGObject) |
| Extras | HTTPS local (mkcert), FTP (vsftpd), captura de correo (Mailpit) |
| Fuera de alcance | Icono en waybar, arranque al iniciar sesión, Tomcat, Perl/ProFTPD |

## Paquetes

- Repos oficiales: `apache`, `php`, `php-fpm`, `mariadb`, `phpmyadmin`, `mkcert`, `vsftpd`
- AUR: `mailpit-bin`

## Estructura

### Código — `~/Proyectos/xampp-linux/`

```
xampp/
  __main__.py     arranque (`python -m xampp`, `xampp --setup`)
  window.py       ventana principal
  services.py     definición declarativa de cada servicio
  systemd.py      envoltorio de `systemctl --user` y `journalctl --user`
  ports.py        detección de puertos ocupados y su proceso (vía `ss -ltnp`)
  config.py       render de plantillas → ~/xampp/etc, ajustes del usuario
  setup.py        asistente de primera instalación
  templates/      httpd.conf, php-fpm.conf, php.ini, my.cnf, vsftpd.conf,
                  units systemd, index.php de bienvenida
tests/
bin/xampp         lanzador
xampp.desktop
```

### Datos del usuario — `~/xampp/`

```
htdocs/       DocumentRoot (índice de bienvenida con enlaces)
etc/          configuraciones generadas; el usuario puede editarlas
etc/settings.json  puertos, HTTPS on/off, credenciales FTP, contraseña root MariaDB
logs/         apache-access.log, apache-error.log, php-fpm.log,
              php-error.log, mariadb.log, vsftpd.log, mailpit.log
data/mysql/   datadir de MariaDB
ssl/          localhost.pem / localhost-key.pem (mkcert)
run/          php-fpm.sock, mariadb.sock, PID files
```

## Servicios

Cada servicio se describe en `services.py` con: id, nombre visible, unit
systemd, puertos, archivo(s) de log, archivo de configuración editable,
dependencias, y comando de validación opcional.

| id | Unit | Comando | Puertos | Depende de |
|---|---|---|---|---|
| apache | `xampp-apache.service` | `httpd -f ~/xampp/etc/httpd.conf -D FOREGROUND` | 80, 443 | php |
| php | `xampp-php.service` | `php-fpm -F -y ~/xampp/etc/php-fpm.conf -c ~/xampp/etc/php.ini` | socket | — |
| mariadb | `xampp-mariadb.service` | `mariadbd --defaults-file=~/xampp/etc/my.cnf` | 3306 | — |
| ftp | `xampp-ftp.service` | `vsftpd ~/xampp/etc/vsftpd.conf` | 21 | — |
| mail | `xampp-mail.service` | `mailpit --smtp :1025 --listen :8025` | 1025, 8025 | — |

- Las units van en `~/.config/systemd/user/`, con `Requires=`/`After=` según
  dependencias (apache → php).
- Apache: `mod_proxy_fcgi` hacia `run/php-fpm.sock` para `*.php`;
  `DirectoryIndex index.php index.html`; `Alias /phpmyadmin
  /usr/share/webapps/phpMyAdmin`; vhost 443 con el certificado de mkcert
  cuando HTTPS está activo.
- PHP: `sendmail_path = "/usr/bin/mailpit sendmail -S 127.0.0.1:1025"`;
  extensiones `mysqli`, `pdo_mysql`, `intl`, `gd` habilitadas.
- MariaDB: escucha en 127.0.0.1:3306 y socket en `run/`; root sin contraseña
  por defecto (como XAMPP), cambiable desde Ajustes.
- vsftpd: modo usuario (`run_as_launching_user=YES`), raíz en `htdocs/`,
  solo escucha en 127.0.0.1. **Riesgo a verificar primero en el plan:** en este
  modo vsftpd no autentica usuarios locales con contraseña. Si se confirma,
  el FTP será login anónimo con escritura, limitado a 127.0.0.1, y los
  ajustes no ofrecerán usuario/contraseña FTP.

## Interfaz

Ventana única (libadwaita, respeta tema oscuro):

```
┌─ XAMPP ───────────────────────────────── [⚙] ─┐
│  [▶ Iniciar todo]  [■ Parar todo]             │
│  ● Apache     80, 443    [Parar]  [Log] [Cfg] │
│  ● PHP-FPM    socket     [Parar]  [Log] [Cfg] │
│  ○ MariaDB    3306       [Iniciar][Log] [Cfg] │
│  ○ FTP        21         [Iniciar][Log] [Cfg] │
│  ● Mailpit    1025/8025  [Parar]  [Log]       │
│  [🌐 localhost] [🗄 phpMyAdmin] [✉ Correo] [📁 htdocs] │
├───────────────────────────────────────────────┤
│  registro de eventos                          │
└───────────────────────────────────────────────┘
```

- Estado por servicio (verde activo / gris parado / rojo fallido), sondeo cada 2 s
  con `systemctl --user is-active`.
- **Iniciar/Parar**: `systemctl --user start|stop`; resultado al registro.
  Iniciar Apache arranca PHP-FPM (dependencia de systemd).
- **Log**: ventana con las últimas ~500 líneas, seguimiento en vivo, botón
  "Abrir archivo".
- **Cfg**: `xdg-open` del archivo de configuración; al volver a la ventana se
  ofrece reiniciar el servicio.
- Botones rápidos: `http(s)://localhost`, `/phpmyadmin`, `http://localhost:8025`,
  carpeta `htdocs`.
- **Ajustes (⚙)**: puertos, HTTPS on/off, contraseña root MariaDB, usuario y
  contraseña FTP (si vsftpd lo permite, ver Servicios), "Regenerar configuraciones" (sobrescribe `etc/` desde
  plantillas tras confirmar).

## Asistente de primera instalación

Se ejecuta si falta `~/xampp/etc/settings.json` o con `xampp --setup`.
Cada paso es idempotente y muestra su resultado.

1. Detectar paquetes faltantes; instalar los oficiales con
   `pkexec pacman -S --needed ...` y `mailpit-bin` abriendo
   `kitty yay -S mailpit-bin`.
2. Privilegios de puertos (una sola vez, vía `pkexec`):
   `setcap cap_net_bind_service=+ep` en `/usr/bin/httpd` y `/usr/bin/vsftpd`,
   e instalar `/etc/pacman.d/hooks/xampp-setcap.hook` (PostTransaction sobre
   `apache` y `vsftpd`).
3. Crear `~/xampp/`, renderizar plantillas, `mariadb-install-db
   --datadir=~/xampp/data/mysql --auth-root-authentication-method=normal`.
4. HTTPS: `mkcert -install` y `mkcert -cert-file ... -key-file ... localhost 127.0.0.1 ::1`.
5. Escribir units en `~/.config/systemd/user/`, `systemctl --user daemon-reload`.
6. Instalar `bin/xampp` en `~/.local/bin` y `xampp.desktop` en
   `~/.local/share/applications`.

## Manejo de errores

Todos los errores van al registro de la ventana y a un `Adw.Toast`.

- **Puerto ocupado** (comprobado antes de iniciar): mostrar proceso y PID; si
  pertenece al usuario, ofrecer terminarlo.
- **Servicio falla**: mostrar las últimas 20 líneas de
  `journalctl --user -u <unit>`.
- **Paquete o binario faltante**: proponer el asistente.
- **Config inválida**: antes de reiniciar Apache se ejecuta `httpd -t -f ...`;
  si falla no se reinicia y se muestra el error.
- **setcap perdido** (Apache no puede abrir 80): explicar y ofrecer re-aplicar.

## Pruebas

- **pytest** (sin GUI): render de plantillas con distintos ajustes, parseo de
  `ss -ltnp`, envoltorio de systemd con `subprocess` simulado, lógica de
  dependencias.
- **E2E** (`tests/e2e.sh`, requiere instalación real): iniciar todo y verificar
  `http://localhost` 200, ejecución de un `.php`, phpMyAdmin carga,
  `https://localhost` con certificado válido, `mail()` llega a Mailpit
  (API `/api/v1/messages`), login FTP con `curl ftp://`.
