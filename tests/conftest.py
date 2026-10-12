import socket

import pytest


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    """Las pruebas nunca llaman a APIs reales: usan ficheros de ejemplo de tests/."""

    def bloqueada(*args, **kwargs):
        raise RuntimeError("Las pruebas no pueden conectarse a la red")

    monkeypatch.setattr(socket.socket, "connect", bloqueada)
    monkeypatch.setattr(socket.socket, "connect_ex", bloqueada)
