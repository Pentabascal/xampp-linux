#!/bin/sh
# xampp-linux: pasos que necesitan root. Uso: root-setup.sh <hook> [paquetes...]
set -e
hook="$1"
shift

if [ "$#" -gt 0 ]; then
    pacman -S --needed --noconfirm "$@"
fi

setcap cap_net_bind_service=+ep /usr/bin/httpd
install -Dm644 "$hook" /etc/pacman.d/hooks/xampp-setcap.hook

conf=$(pacman -Qlq phpmyadmin | grep 'config\.inc\.php$' | head -n1)
conf=$(readlink -f "$conf")
if ! grep -q '// xampp-linux' "$conf"; then
    secret=$(openssl rand -hex 16)
    cat >> "$conf" <<PHP

// xampp-linux
\$cfg['blowfish_secret'] = '$secret';
\$cfg['Servers'][1]['AllowNoPassword'] = true;
\$cfg['TempDir'] = sys_get_temp_dir();
PHP
fi
