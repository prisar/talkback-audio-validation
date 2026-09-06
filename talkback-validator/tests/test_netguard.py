import socket
import urllib.error
import urllib.request

import pytest

from talkback_validator.netguard import EgressBlocked, loopback_only


def test_public_address_is_refused():
    with loopback_only():
        with pytest.raises(EgressBlocked):
            socket.socket().connect(("142.250.0.1", 443))


def test_hostname_resolution_is_refused():
    """Resolving a public name is already a query leaving the machine."""
    with loopback_only():
        with pytest.raises(EgressBlocked):
            socket.getaddrinfo("generativelanguage.googleapis.com", 443)


def test_an_http_client_cannot_slip_past_the_guard():
    with loopback_only():
        with pytest.raises((EgressBlocked, urllib.error.URLError)):
            urllib.request.urlopen("https://example.com", timeout=5)


def test_loopback_still_works():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        with loopback_only():
            client = socket.socket()
            client.connect(("127.0.0.1", port))
            client.close()
    finally:
        server.close()


def test_the_guard_is_removed_afterwards():
    original = socket.socket.connect
    with loopback_only():
        assert socket.socket.connect is not original
    assert socket.socket.connect is original
