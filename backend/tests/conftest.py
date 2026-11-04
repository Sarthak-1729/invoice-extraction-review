"""Tests never touch the network: no real API calls, no keys needed.

Loopback stays allowed, because the event loop behind FastAPI's TestClient uses
a local socket pair on Windows.
"""

import socket

import pytest

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
_connect = socket.socket.connect


def _is_loopback(address) -> bool:
    return not isinstance(address, tuple) or address[0] in LOOPBACK


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    def guarded_connect(self, address):
        if not _is_loopback(address):
            raise RuntimeError(f"Network access to {address!r} is blocked in tests.")
        return _connect(self, address)

    def refuse_create_connection(address, *args, **kwargs):
        raise RuntimeError(f"Network access to {address!r} is blocked in tests.")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "create_connection", refuse_create_connection)
