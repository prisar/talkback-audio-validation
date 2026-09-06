from __future__ import annotations

import ipaddress
import socket
from contextlib import contextmanager

LOOPBACK_NAMES = {"localhost", "localhost.localdomain", ""}


class EgressBlocked(RuntimeError):
    """Raised when code inside a local-only run tries to leave the machine."""


def _is_local(host) -> bool:
    if not isinstance(host, str):
        return False
    name = host.strip("[]").lower()
    if name in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def _check(address) -> None:
    if isinstance(address, (str, bytes)):
        return
    if not isinstance(address, tuple) or not address:
        return
    if _is_local(address[0]):
        return
    raise EgressBlocked(
        f"a local-only run tried to reach {address[0]!r}; only loopback is permitted"
    )


@contextmanager
def loopback_only():
    """Blocks every outbound connection except loopback for the duration.

    The offline claim is worth nothing if it is only a promise about which
    backend was selected. A model that quietly falls back to a hosted API, a
    telemetry ping inside a dependency, or a stray download would all break it
    silently. Here the attempt raises instead, so a local run that touches the
    network fails loudly rather than passing while leaking.

    Name resolution is blocked alongside connect: resolving a public hostname
    is itself a query sent off the machine.
    """
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def connect(self, address):
        _check(address)
        return real_connect(self, address)

    def connect_ex(self, address):
        _check(address)
        return real_connect_ex(self, address)

    def getaddrinfo(host, port, *args, **kwargs):
        if not _is_local(host):
            raise EgressBlocked(
                f"a local-only run tried to resolve {host!r}; only loopback is permitted"
            )
        return real_getaddrinfo(host, port, *args, **kwargs)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.getaddrinfo = getaddrinfo
    try:
        yield
    finally:
        socket.socket.connect = real_connect
        socket.socket.connect_ex = real_connect_ex
        socket.getaddrinfo = real_getaddrinfo
