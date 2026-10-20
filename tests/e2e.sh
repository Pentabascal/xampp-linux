#!/usr/bin/env bash
# Prueba de extremo a extremo sobre la instalación real (~/xampp).
set -euo pipefail

H="${XAMPP_HOME:-$HOME/xampp}"
MAIL_WEB="${MAIL_WEB:-8025}"
ok() { printf '✓ %s\n' "$1"; }
fail() { printf '✗ %s\n' "$1"; exit 1; }
cleanup() { rm -f "$H/htdocs/_e2e.php" "$H/htdocs/_e2e_mail.php"; }
trap cleanup EXIT

systemctl --user start xampp-apache xampp-mariadb xampp-mail
sleep 2

curl -fsS -o /dev/null http://localhost/ && ok "http://localhost responde" || fail "http://localhost no responde"

echo '<?php echo 6*7;' > "$H/htdocs/_e2e.php"
[ "$(curl -fsS http://localhost/_e2e.php)" = "42" ] && ok "PHP se ejecuta" || fail "PHP no se ejecuta"

curl -fsS http://localhost/phpmyadmin/ | grep -q phpMyAdmin && ok "phpMyAdmin carga" || fail "phpMyAdmin no carga"

curl -fsS -o /dev/null https://localhost/ && ok "https://localhost con certificado válido" || fail "HTTPS falla"

echo "<?php var_dump(mail('a@b.c', 'e2e-$$', 'x'));" > "$H/htdocs/_e2e_mail.php"
curl -fsS http://localhost/_e2e_mail.php >/dev/null
sleep 1
curl -fsS "http://localhost:$MAIL_WEB/api/v1/messages" | grep -q "e2e-$$" && ok "mail() llega a Mailpit" || fail "el correo no llegó a Mailpit"

[ "$(mariadb -uroot -S "$H/run/mariadb.sock" -N -e 'SELECT 1')" = "1" ] && ok "MariaDB responde" || fail "MariaDB no responde"

echo "Todo correcto"
