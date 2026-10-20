"""Definición declarativa de los servicios que controla el panel."""

from dataclasses import dataclass
from typing import Callable

from .config import Settings


@dataclass(frozen=True)
class Service:
    id: str
    name: str
    unit: str
    logs: tuple[str, ...]  # relativos a paths.logs
    config: str | None  # relativo a paths.etc
    requires: tuple[str, ...]
    _ports: Callable[[Settings], list[int]]

    def ports(self, s: Settings) -> list[int]:
        return self._ports(s)


SERVICES: tuple[Service, ...] = (
    Service(
        "apache", "Apache", "xampp-apache.service",
        ("apache-error.log", "apache-access.log"), "httpd.conf", ("php",),
        lambda s: [s.http_port] + ([s.https_port] if s.https else []),
    ),
    Service(
        "php", "PHP-FPM", "xampp-php.service",
        ("php-fpm.log", "php-error.log"), "php.ini", (),
        lambda s: [],
    ),
    Service(
        "mariadb", "MariaDB", "xampp-mariadb.service",
        ("mariadb.log",), "my.cnf", (),
        lambda s: [s.mariadb_port],
    ),
    Service(
        "mail", "Mailpit", "xampp-mail.service",
        ("mailpit.log",), None, (),
        lambda s: [s.smtp_port, s.mail_web_port],
    ),
)

_BY_ID = {s.id: s for s in SERVICES}


def get(id: str) -> Service:
    return _BY_ID[id]


def start_order(ids) -> list[str]:
    """Los servicios pedidos con sus dependencias delante, sin duplicados."""
    order: list[str] = []

    def visit(id: str) -> None:
        for dep in get(id).requires:
            visit(dep)
        if id not in order:
            order.append(id)

    for id in ids:
        visit(id)
    return order
