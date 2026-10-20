<?php if (isset($$_GET['info'])) { phpinfo(); exit; } ?>
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>XAMPP</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 40rem; margin: 4rem auto; padding: 0 1rem; color: #222; }
  a { display: block; margin: .5rem 0; }
  @media (prefers-color-scheme: dark) { body { background: #1e1e1e; color: #ddd; } a { color: #8ab4f8; } }
</style>
</head>
<body>
<h1>XAMPP funciona</h1>
<p>PHP <?= PHP_VERSION ?>. Pon tus archivos en <code>$htdocs</code>.</p>
<a href="/phpmyadmin/">phpMyAdmin</a>
<a href="http://localhost:$mail_web_port/">Correo de prueba (Mailpit)</a>
<a href="?info">phpinfo()</a>
</body>
</html>
