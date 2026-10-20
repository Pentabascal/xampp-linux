import json

from xampp.config import Paths, Settings, is_installed, load_settings, save_settings


def test_default_settings(paths):
    s = load_settings(paths)
    assert s == Settings()
    assert (s.http_port, s.https_port, s.mariadb_port) == (80, 443, 3306)
    assert (s.smtp_port, s.mail_web_port) == (1025, 8025)


def test_settings_roundtrip(paths):
    assert not is_installed(paths)
    s = Settings(http_port=8080, https=False)
    save_settings(paths, s)
    assert load_settings(paths) == s
    assert is_installed(paths)


def test_unknown_keys_ignored(paths):
    paths.etc.mkdir(parents=True)
    (paths.etc / "settings.json").write_text(json.dumps({"http_port": 81, "ftp": 1}))
    assert load_settings(paths).http_port == 81


def test_paths_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("XAMPP_HOME", str(tmp_path))
    p = Paths.default()
    assert p.htdocs == tmp_path / "htdocs"
    assert p.mysql == tmp_path / "data" / "mysql"
