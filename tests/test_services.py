import pytest

from xampp.config import Settings
from xampp.services import SERVICES, get, start_order


def test_service_order():
    assert [s.id for s in SERVICES] == ["apache", "php", "mariadb", "mail"]


def test_apache_ports_with_and_without_https():
    apache = get("apache")
    assert apache.ports(Settings()) == [80, 443]
    assert apache.ports(Settings(https=False)) == [80]


def test_other_ports():
    s = Settings()
    assert get("php").ports(s) == []
    assert get("mariadb").ports(s) == [3306]
    assert get("mail").ports(s) == [1025, 8025]


def test_units_named():
    assert get("mariadb").unit == "xampp-mariadb.service"
    assert get("mail").config is None


def test_start_order():
    assert start_order(["apache", "mariadb"]) == ["php", "apache", "mariadb"]
    assert start_order(["php", "apache"]) == ["php", "apache"]


def test_get_unknown_raises():
    with pytest.raises(KeyError):
        get("ftp")
