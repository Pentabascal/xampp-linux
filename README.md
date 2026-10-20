# xampp-linux

Panel tipo XAMPP para Arch Linux: Apache, PHP-FPM, MariaDB y Mailpit como
servicios systemd de usuario, con una ventana GTK4 para controlarlos.

## Instalar

```sh
python3 -m xampp --setup
```

El asistente instala los paquetes (pide la contraseña una vez), abre una
terminal para Mailpit (AUR) y el certificado de mkcert, y crea `~/xampp`.
Al terminar puedes abrirlo con `xampp` o desde el lanzador de aplicaciones.

## Uso

- Tus webs van en `~/xampp/htdocs` → <http://localhost> y <https://localhost>
- phpMyAdmin: <http://localhost/phpmyadmin> (usuario `root`, sin contraseña)
- Correos enviados con `mail()`: <http://localhost:8025>
- Configuración: `~/xampp/etc` (se regenera al guardar los Ajustes)
- Logs: `~/xampp/logs`

## Desarrollo

```sh
python -m venv --system-site-packages .venv && .venv/bin/pip install pytest
.venv/bin/python -m pytest -q   # tests unitarios
bash tests/e2e.sh               # prueba completa sobre la instalación real
```
