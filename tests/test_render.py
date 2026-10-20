import os
import re

from xampp.config import Settings, https_effective, render_all

UNITS = ["xampp-apache.service", "xampp-php.service", "xampp-mariadb.service", "xampp-mail.service"]
ETC = ["httpd.conf", "php-fpm.conf", "php.ini", "my.cnf"]


def _cert(paths):
    paths.ssl.mkdir(parents=True, exist_ok=True)
    (paths.ssl / "localhost.pem").write_text("c")
    (paths.ssl / "localhost-key.pem").write_text("k")


def test_render_all_writes_files(paths):
    render_all(paths, Settings())
    for name in ETC:
        assert (paths.etc / name).exists(), name
    for unit in UNITS:
        assert (paths.units / unit).exists(), unit
    for f in [paths.etc / "httpd.conf", paths.etc / "php-fpm.conf", paths.etc / "my.cnf",
              *(paths.units / u for u in UNITS)]:
        assert re.search(r"\$[a-z_]+", f.read_text()) is None, f


def test_httpd_conf_paths(paths):
    render_all(paths, Settings())
    conf = (paths.etc / "httpd.conf").read_text()
    assert f'DocumentRoot "{paths.htdocs}"' in conf
    assert f"proxy:unix:{paths.run}/php-fpm.sock" in conf
    assert "Listen 80\n" in conf
    assert "Alias /phpmyadmin" in conf


def test_httpd_conf_without_https(paths):
    _cert(paths)
    render_all(paths, Settings(https=False))
    conf = (paths.etc / "httpd.conf").read_text()
    assert "Listen 443" not in conf
    assert "ssl_module" not in conf


def test_httpd_conf_https_requires_cert(paths):
    warnings = render_all(paths, Settings())
    assert not https_effective(paths, Settings())
    assert "Listen 443" not in (paths.etc / "httpd.conf").read_text()
    assert any("certificado" in w for w in warnings)

    _cert(paths)
    assert render_all(paths, Settings()) == []
    conf = (paths.etc / "httpd.conf").read_text()
    assert "Listen 443" in conf
    assert f"SSLCertificateFile {paths.ssl}/localhost.pem" in conf


def test_custom_ports(paths):
    render_all(paths, Settings(http_port=8080, mariadb_port=3307, smtp_port=2025))
    assert "Listen 8080\n" in (paths.etc / "httpd.conf").read_text()
    assert "port=3307" in (paths.etc / "my.cnf").read_text()
    assert "-S 127.0.0.1:2025" in (paths.etc / "php.ini").read_text()


def test_apache_unit_requires_php(paths):
    render_all(paths, Settings())
    unit = (paths.units / "xampp-apache.service").read_text()
    assert "Requires=xampp-php.service" in unit
    assert f"ExecStart=/usr/bin/httpd -f {paths.etc}/httpd.conf -D FOREGROUND" in unit


def test_welcome_page_only_when_htdocs_empty(paths, tmp_path):
    render_all(paths, Settings())
    assert (paths.htdocs / "index.php").exists()

    from xampp.config import Paths
    other = Paths.at(tmp_path / "other", tmp_path / "u2")
    other.htdocs.mkdir(parents=True)
    (other.htdocs / "mio.html").write_text("hola")
    render_all(other, Settings())
    assert not (other.htdocs / "index.php").exists()


def test_render_all_never_touches_htdocs_or_data(paths):
    paths.htdocs.mkdir(parents=True)
    paths.mysql.mkdir(parents=True)
    a, x = paths.htdocs / "a.php", paths.mysql / "x"
    a.write_text("<?php echo 1;")
    x.write_text("datos")
    os.utime(a, (1, 1))
    os.utime(x, (1, 1))
    render_all(paths, Settings())
    assert a.read_text() == "<?php echo 1;" and a.stat().st_mtime == 1
    assert x.read_text() == "datos" and x.stat().st_mtime == 1
