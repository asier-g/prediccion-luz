import socket
import tomllib
from pathlib import Path

import pytest

import prediccion_luz


def test_version_coincide_con_pyproject():
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    with pyproject.open("rb") as f:
        version = tomllib.load(f)["project"]["version"]
    assert prediccion_luz.__version__ == version


def test_red_bloqueada():
    with pytest.raises(RuntimeError, match="red"):
        # IP de documentación (RFC 5737): no hace falta resolver DNS.
        socket.create_connection(("192.0.2.1", 443), timeout=1)
