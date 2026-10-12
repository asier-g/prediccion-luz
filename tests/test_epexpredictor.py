"""Pruebas del archivo de EpexPredictor.

El ejemplo de `datos/epexpredictor_ejemplo.json` es sintético (mismo esquema que
la API, valores inventados y pocas filas) para no publicar sus datos en el repo.
Simula una captura del miércoles 14-01-2026 a las 15:07 de Madrid (14:07 UTC):
D+1 conocido y la previsión llega hasta D+7, con un periodo al final de D+3.
"""

import io
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.fernet import Fernet, InvalidToken

from prediccion_luz.fuentes import epexpredictor as ep

EJEMPLO = Path(__file__).parent / "datos" / "epexpredictor_ejemplo.json"
CAPTURA = datetime(2026, 1, 14, 14, 7, tzinfo=UTC)


@pytest.fixture
def respuesta():
    return json.loads(EJEMPLO.read_text(encoding="utf-8"))


@pytest.fixture
def clave():
    return Fernet.generate_key()


# Ventana de captura y nombre del fichero


@pytest.mark.parametrize(
    ("momento", "esperado"),
    [
        # Invierno (UTC+1): 13:07 UTC son las 14:07 en Madrid, antes del corte.
        (datetime(2026, 1, 14, 13, 7, tzinfo=UTC), False),
        (datetime(2026, 1, 14, 14, 7, tzinfo=UTC), True),
        # Verano (UTC+2): 13:07 UTC ya son las 15:07 en Madrid.
        (datetime(2026, 7, 14, 12, 7, tzinfo=UTC), False),
        (datetime(2026, 7, 14, 13, 7, tzinfo=UTC), True),
        # Límites: las 15:00 entran, las 18:00 no.
        (datetime(2026, 1, 14, 14, 0, tzinfo=UTC), True),
        (datetime(2026, 1, 14, 17, 0, tzinfo=UTC), False),
        (datetime(2026, 1, 14, 18, 0, tzinfo=UTC), False),
    ],
)
def test_en_ventana(momento, esperado):
    assert ep.en_ventana(momento) is esperado


def test_fecha_sin_zona_falla(tmp_path):
    with pytest.raises(ValueError, match="zona"):
        ep.en_ventana(datetime(2026, 1, 14, 15, 7))  # noqa: DTZ001
    with pytest.raises(ValueError, match="zona"):
        ep.ruta_fichero(tmp_path, datetime(2026, 1, 14, 15, 7))  # noqa: DTZ001


def test_ruta_usa_la_fecha_de_madrid(tmp_path):
    # 23:30 UTC del 14 ya es día 15 en Madrid.
    ruta = ep.ruta_fichero(tmp_path, datetime(2026, 1, 14, 23, 30, tzinfo=UTC))
    assert ruta == tmp_path / "2026" / "2026-01-15.json.gz.cifrado"


def test_url_peticion():
    assert ep.url_peticion() == (
        "https://epexpredictor.batzill.com/prices"
        "?region=ES&unit=EUR_PER_MWH&timezone=UTC"
    )


# Validación de la respuesta


def test_validar_acepta_el_ejemplo(respuesta):
    ep.validar(respuesta, CAPTURA)


@pytest.mark.parametrize(
    ("cambio", "mensaje"),
    [
        (lambda r: r.pop("prices"), "prices"),
        (lambda r: r.pop("knownUntil"), "knownUntil"),
        (lambda r: r.update(prices=[]), "vacía"),
        (lambda r: r["prices"][0].update(startsAt="2026-01-14T14:00:00"), "UTC"),
        (lambda r: r["prices"][0].update(startsAt="2026-01-14T15:00:00+01:00"), "UTC"),
        (lambda r: r["prices"][0].update(total="85.12"), "numérico"),
        (lambda r: r["prices"][0].update(total=float("nan")), "finito"),
        (lambda r: r["prices"][0].pop("total"), "total"),
        # Sin los dos últimos periodos, la previsión acaba en D.
        (lambda r: r.update(prices=r["prices"][:4]), "D\\+3"),
    ],
)
def test_validar_rechaza(respuesta, cambio, mensaje):
    cambio(respuesta)
    with pytest.raises(ValueError, match=mensaje):
        ep.validar(respuesta, CAPTURA)


def test_validar_exige_d3_completo(respuesta):
    # El último periodo empieza a las 21:45 UTC (22:45 de Madrid) de D+3: falta
    # la última hora del día.
    respuesta["prices"] = respuesta["prices"][:4] + [
        {"startsAt": "2026-01-17T21:45:00Z", "total": 70.0}
    ]
    with pytest.raises(ValueError, match="D\\+3"):
        ep.validar(respuesta, CAPTURA)


# Cifrado y guardado


def test_cifrar_y_descifrar(respuesta, clave):
    cifrado = ep.cifrar(respuesta, clave)
    assert b"startsAt" not in cifrado
    assert ep.descifrar(cifrado, clave) == respuesta


def test_descifrar_con_otra_clave_falla(respuesta, clave):
    cifrado = ep.cifrar(respuesta, clave)
    with pytest.raises(InvalidToken):
        ep.descifrar(cifrado, Fernet.generate_key())


def test_guardar_no_sobrescribe(tmp_path, respuesta, clave):
    ruta = ep.guardar(tmp_path, CAPTURA, "https://ejemplo", respuesta, clave)
    assert ruta == tmp_path / "2026" / "2026-01-14.json.gz.cifrado"
    assert ep.descifrar(ruta.read_bytes(), clave) == {
        "fuente": "EpexPredictor",
        "url": "https://ejemplo",
        "capturado_utc": "2026-01-14T14:07:00+00:00",
        "respuesta": respuesta,
    }
    with pytest.raises(FileExistsError):
        ep.guardar(tmp_path, CAPTURA, "https://ejemplo", {}, clave)


# Ejecución completa, con una descarga falsa


class DescargaFalsa:
    def __init__(self, respuesta):
        self.respuesta = respuesta
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        return self.respuesta


def test_main_no_repite_la_descarga(tmp_path, monkeypatch, respuesta, clave, capsys):
    monkeypatch.setenv(ep.VARIABLE_CLAVE, clave.decode())
    descarga = DescargaFalsa(respuesta)

    assert ep.main([str(tmp_path)], ahora=lambda: CAPTURA, descarga=descarga) == 0
    assert descarga.urls == [ep.url_peticion()]
    ruta = tmp_path / "2026" / "2026-01-14.json.gz.cifrado"
    assert ep.descifrar(ruta.read_bytes(), clave)["respuesta"] == respuesta

    assert ep.main([str(tmp_path)], ahora=lambda: CAPTURA, descarga=descarga) == 0
    assert len(descarga.urls) == 1
    assert "Nada que hacer" in capsys.readouterr().out


def test_main_fuera_de_ventana(tmp_path, monkeypatch, respuesta, clave):
    monkeypatch.setenv(ep.VARIABLE_CLAVE, clave.decode())
    descarga = DescargaFalsa(respuesta)
    temprano = datetime(2026, 1, 14, 13, 7, tzinfo=UTC)

    assert ep.main([str(tmp_path)], ahora=lambda: temprano, descarga=descarga) == 0
    assert descarga.urls == []

    argv = [str(tmp_path), "--forzar"]
    assert ep.main(argv, ahora=lambda: temprano, descarga=descarga) == 0
    assert len(descarga.urls) == 1


def test_main_sin_clave_falla(tmp_path, monkeypatch, respuesta):
    monkeypatch.delenv(ep.VARIABLE_CLAVE, raising=False)
    descarga = DescargaFalsa(respuesta)
    assert ep.main([str(tmp_path)], ahora=lambda: CAPTURA, descarga=descarga) == 2
    assert descarga.urls == []


def test_main_no_guarda_si_no_valida(tmp_path, monkeypatch, clave):
    monkeypatch.setenv(ep.VARIABLE_CLAVE, clave.decode())
    descarga = DescargaFalsa({"prices": [], "knownUntil": "2026-01-15T22:45:00Z"})
    with pytest.raises(ValueError):
        ep.main([str(tmp_path)], ahora=lambda: CAPTURA, descarga=descarga)
    assert not any(tmp_path.rglob("*.cifrado"))


# Reintentos de la descarga, sin red


def test_descargar_reintenta(monkeypatch):
    llamadas = []

    def urlopen(url, timeout):
        llamadas.append(url)
        if len(llamadas) < 3:
            raise urllib.error.URLError("caída")
        return io.BytesIO(b'{"prices": []}')

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert ep.descargar("https://ejemplo", espera=0) == {"prices": []}
    assert len(llamadas) == 3


def test_descargar_falla_tras_los_intentos(monkeypatch):
    def urlopen(url, timeout):
        return io.BytesIO(b"<html>error</html>")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(RuntimeError, match="3 intentos"):
        ep.descargar("https://ejemplo", espera=0)
