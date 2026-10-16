"""Pruebas de la descarga y lectura de Open-Meteo.

`datos/openmeteo/zaragoza_20241026_20241027.json` es una respuesta real de la
Previous Runs API (fuente: Open-Meteo, open-meteo.com, CC BY 4.0), sin modificar:
dos días de Zaragoza en GMT, con el paso a la hora de invierno del 27-10-2024.
Las demás respuestas son sintéticas, con la misma estructura.
"""

import copy
import io
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from prediccion_luz import almacen
from prediccion_luz.fuentes import openmeteo

EJEMPLO = json.loads(
    (
        Path(__file__).parent
        / "datos"
        / "openmeteo"
        / "zaragoza_20241026_20241027.json"
    ).read_text(encoding="utf-8")
)
DESDE_EJEMPLO, HASTA_EJEMPLO = date(2024, 10, 26), date(2024, 10, 27)
N_COLUMNAS = len(openmeteo.VARIABLES) * len(openmeteo.DIAS_PREVIOS)


def utc(*args) -> pd.Timestamp:
    return pd.Timestamp(datetime(*args, tzinfo=UTC))


def respuesta_sintetica(desde: date, hasta: date, valor: float = 1.0) -> dict:
    n_horas = 24 * ((hasta - desde).days + 1)
    inicio = datetime(desde.year, desde.month, desde.day, tzinfo=UTC)
    horas = {
        "time": [
            f"{inicio + timedelta(hours=i):%Y-%m-%dT%H:%M}" for i in range(n_horas)
        ]
    }
    unidades = {"time": "iso8601"}
    for variable, unidad in openmeteo.VARIABLES.items():
        for k in openmeteo.DIAS_PREVIOS:
            columna = openmeteo.nombre_columna(variable, k)
            horas[columna] = [valor] * n_horas
            unidades[columna] = unidad
    return {
        "utc_offset_seconds": 0,
        "timezone": "GMT",
        "hourly_units": unidades,
        "hourly": horas,
    }


class DescargaFalsa:
    """Responde a cada URL con una respuesta sintética válida para su rango."""

    def __init__(self, contenido: bytes | None = None):
        self.contenido = contenido
        self.urls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        if self.contenido is not None:
            return self.contenido
        desde, hasta = rango_de_url(url)
        return json.dumps(respuesta_sintetica(desde, hasta)).encode()

    def rangos(self) -> list[tuple[date, date]]:
        return [rango_de_url(url) for url in self.urls]


def rango_de_url(url: str) -> tuple[date, date]:
    parametros = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    return (
        date.fromisoformat(parametros["start_date"][0]),
        date.fromisoformat(parametros["end_date"][0]),
    )


class Dormir:
    def __init__(self):
        self.segundos: list[float] = []

    def __call__(self, segundos: float) -> None:
        self.segundos.append(segundos)


def ejecutar(carpeta, descarga, hoy=date(2024, 2, 3), *opciones, dormir=None):
    """`main` desde el 25-01-2024 como si fuese `hoy` a mediodía UTC: con el
    margen de 2 días, se pide hasta el 01-02-2024."""
    momento = datetime(hoy.year, hoy.month, hoy.day, 12, tzinfo=UTC)
    return openmeteo.main(
        [str(carpeta), "--desde", "2024-01-25", *opciones],
        descarga=descarga,
        ahora=lambda: momento,
        dormir=dormir or Dormir(),
    )


def leer_tabla(carpeta: Path) -> pd.DataFrame:
    return almacen.leer_parquet(carpeta / "meteo" / "meteo_prevista.parquet")


# Lectura


def test_lee_el_ejemplo_real():
    openmeteo.validar(EJEMPLO, DESDE_EJEMPLO, HASTA_EJEMPLO)
    tabla = openmeteo.leer_respuesta(EJEMPLO, "zaragoza")
    assert list(tabla.columns) == openmeteo.COLUMNAS
    assert len(tabla) == 48 * N_COLUMNAS  # El ejemplo no tiene nulos.
    horas = tabla["prevista_utc"].drop_duplicates().sort_values()
    assert horas.iloc[0] == utc(2024, 10, 26, 0)
    assert horas.iloc[-1] == utc(2024, 10, 27, 23)
    # En GMT, el cambio de hora no deja huecos ni horas repetidas.
    assert horas.diff().dropna().eq(pd.Timedelta(hours=1)).all()
    assert sorted(tabla["dias_previos"].unique()) == list(range(1, 8))
    assert set(tabla["variable"]) == set(openmeteo.VARIABLES)
    assert (tabla["proveedor"] == "open-meteo").all()
    assert (tabla["modelo"] == "best_match").all()


def test_lee_el_valor_de_cada_columna():
    tabla = openmeteo.leer_respuesta(EJEMPLO, "zaragoza")
    fila = tabla[
        (tabla["variable"] == "temperature_2m")
        & (tabla["dias_previos"] == 2)
        & (tabla["prevista_utc"] == utc(2024, 10, 26, 0))
    ]
    assert fila["valor"].tolist() == [
        EJEMPLO["hourly"]["temperature_2m_previous_day2"][0]
    ]


def test_emision_provisional_k_dias_antes():
    tabla = openmeteo.leer_respuesta(EJEMPLO, "zaragoza")
    antelacion = tabla["prevista_utc"] - tabla["emision_utc"]
    assert (antelacion == pd.to_timedelta(tabla["dias_previos"], unit="D")).all()


def test_descarta_los_nulos():
    respuesta = copy.deepcopy(EJEMPLO)
    respuesta["hourly"]["wind_speed_100m_previous_day7"][:5] = [None] * 5
    openmeteo.validar(respuesta, DESDE_EJEMPLO, HASTA_EJEMPLO)
    tabla = openmeteo.leer_respuesta(respuesta, "zaragoza")
    assert len(tabla) == 48 * N_COLUMNAS - 5
    assert tabla["valor"].notna().all()


def estropear(cambio):
    respuesta = copy.deepcopy(EJEMPLO)
    cambio(respuesta)
    return respuesta


@pytest.mark.parametrize(
    ("respuesta", "mensaje"),
    [
        ({"error": True, "reason": "Parameter 'x' invalid"}, "Parameter 'x'"),
        ([], "objeto JSON"),
        (estropear(lambda r: r.update(utc_offset_seconds=7200)), "desfase"),
        (estropear(lambda r: r["hourly"]["time"].pop(30)), "seguidas"),
        (estropear(lambda r: r["hourly"].pop("temperature_2m_previous_day3")), "falta"),
        (
            estropear(
                lambda r: r["hourly_units"].update(wind_speed_100m_previous_day1="m/s")
            ),
            "unidad",
        ),
        (
            estropear(
                lambda r: r["hourly"]["temperature_2m_previous_day1"].__setitem__(
                    0, "x"
                )
            ),
            "no numérico",
        ),
        (estropear(lambda r: r.pop("hourly_units")), "hourly_units"),
    ],
)
def test_validar_rechaza(respuesta, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        openmeteo.validar(respuesta, DESDE_EJEMPLO, HASTA_EJEMPLO)


def test_validar_rechaza_otro_rango():
    with pytest.raises(ValueError, match="seguidas"):
        openmeteo.validar(EJEMPLO, DESDE_EJEMPLO, date(2024, 10, 28))


# Peso, URL y planificación


@pytest.mark.parametrize(
    ("variables", "dias", "esperado"),
    [
        (10, 14, 1.0),
        (3, 1, 1.0),
        (15, 14, 1.5),  # El ejemplo de la página de precios de Open-Meteo.
        (21, 31, 2.1 * 31 / 14),
        (21, 2, 2.1),
    ],
)
def test_peso(variables, dias, esperado):
    assert openmeteo.peso(variables, dias) == pytest.approx(esperado)


def test_url_en_gmt_y_con_modelo():
    url = openmeteo.url_peticion("zaragoza", date(2024, 1, 1), date(2024, 1, 31))
    parametros = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert "timezone" not in parametros
    assert parametros["models"] == ["best_match"]
    assert parametros["latitude"] == ["41.65"]
    assert parametros["start_date"] == ["2024-01-01"]
    assert parametros["end_date"] == ["2024-01-31"]
    assert parametros["hourly"][0].split(",") == openmeteo.columnas_api()
    assert len(openmeteo.columnas_api()) == N_COLUMNAS == 21


def test_tramos_por_mes_natural():
    fechas = [
        *openmeteo.dias(date(2024, 1, 30), date(2024, 2, 2)),
        date(2024, 2, 5),
        date(2024, 2, 6),
    ]
    assert openmeteo.tramos(fechas) == [
        (date(2024, 1, 30), date(2024, 1, 31)),
        (date(2024, 2, 1), date(2024, 2, 2)),
        (date(2024, 2, 5), date(2024, 2, 6)),
    ]


def test_ruta_cruda(tmp_path):
    ruta = openmeteo.ruta_cruda(tmp_path, "lugo", date(2024, 2, 1), date(2024, 2, 29))
    assert ruta == tmp_path / "meteo" / "openmeteo" / "lugo" / "20240201_20240229.json"
    assert openmeteo.leer_nombre(ruta.name) == (date(2024, 2, 1), date(2024, 2, 29))
    assert openmeteo.leer_nombre("otro.json") is None


# Descarga incremental, con una descarga falsa


def test_main_descarga_y_no_repite(tmp_path):
    descarga = DescargaFalsa()
    assert ejecutar(tmp_path, descarga) == 0
    # Por punto: el resto de enero y, por el margen de 2 días, solo el 1 de febrero.
    assert descarga.rangos() == [
        (date(2024, 1, 25), date(2024, 1, 31)),
        (date(2024, 2, 1), date(2024, 2, 1)),
    ] * len(openmeteo.PUNTOS)

    tabla = leer_tabla(tmp_path)
    assert len(tabla) == len(openmeteo.PUNTOS) * 8 * 24 * N_COLUMNAS
    assert set(tabla["punto"]) == set(openmeteo.PUNTOS)
    assert not tabla.duplicated(subset=openmeteo.CLAVE).any()

    # Segunda ejecución el mismo día: ninguna petición y la misma tabla.
    descarga.urls.clear()
    assert ejecutar(tmp_path, descarga) == 0
    assert descarga.urls == []
    pd.testing.assert_frame_equal(leer_tabla(tmp_path), tabla)


def test_dias_nuevos_solo_piden_lo_que_falta(tmp_path):
    ejecutar(tmp_path, DescargaFalsa())
    descarga = DescargaFalsa()
    assert ejecutar(tmp_path, descarga, date(2024, 2, 6)) == 0
    assert descarga.rangos() == [(date(2024, 2, 2), date(2024, 2, 4))] * len(
        openmeteo.PUNTOS
    )
    assert openmeteo.dias_cubiertos(tmp_path, "madrid") == set(
        openmeteo.dias(date(2024, 1, 25), date(2024, 2, 4))
    )


def test_presupuesto_se_reparte_en_varios_dias(tmp_path, monkeypatch, capsys):
    # Cada petición pesa 2,1 (21 variables y 7 días o menos): caben 4 al día.
    monkeypatch.setattr(openmeteo, "PRESUPUESTO_DIARIO", 10.0)
    descarga = DescargaFalsa()
    assert ejecutar(tmp_path, descarga) == 0
    assert len(descarga.urls) == 4
    assert "Quedan 10 peticiones" in capsys.readouterr().out
    assert openmeteo.gastado_hoy(tmp_path, date(2024, 2, 3)) == pytest.approx(8.4)

    # El mismo día no queda presupuesto: lo gastado sale del crudo.
    descarga.urls.clear()
    assert ejecutar(tmp_path, descarga) == 0
    assert descarga.urls == []

    # Al día siguiente sigue donde lo dejó.
    assert ejecutar(tmp_path, descarga, date(2024, 2, 4)) == 0
    assert len(descarga.urls) == 4
    assert openmeteo.gastado_hoy(tmp_path, date(2024, 2, 3)) == pytest.approx(8.4)


def test_ritmo_por_minuto(tmp_path):
    dormir = Dormir()
    ejecutar(tmp_path, DescargaFalsa(), dormir=dormir)
    peso_total = 14 * 2.1
    assert sum(dormir.segundos) == pytest.approx(
        60 * peso_total / openmeteo.RITMO_POR_MINUTO
    )


def test_respuesta_no_valida_no_se_guarda_y_para(tmp_path, capsys):
    descarga = DescargaFalsa(b'{"error": true, "reason": "Cannot initialize"}')
    assert ejecutar(tmp_path, descarga) == 1
    # Tras 3 fallos seguidos no insiste.
    assert len(descarga.urls) == openmeteo.ERRORES_SEGUIDOS
    assert not (tmp_path / "meteo" / "openmeteo").exists()
    salida = capsys.readouterr()
    assert "Cannot initialize" in salida.err
    assert "Quedan 11 peticiones" in salida.out


def test_sin_descarga_no_usa_la_red(tmp_path):
    ejecutar(tmp_path, DescargaFalsa())
    descarga = DescargaFalsa()
    assert ejecutar(tmp_path, descarga, date(2024, 3, 1), "--sin-descarga") == 0
    assert descarga.urls == []


def test_ficheros_solapados_dan_error(tmp_path):
    momento = datetime(2024, 2, 3, tzinfo=UTC)
    for desde, hasta in [
        (date(2024, 1, 1), date(2024, 1, 10)),
        (date(2024, 1, 10), date(2024, 1, 12)),
    ]:
        contenido = json.dumps(respuesta_sintetica(desde, hasta)).encode()
        openmeteo.guardar(tmp_path, "lugo", desde, hasta, "url", contenido, momento)
    with pytest.raises(ValueError, match="repetidas"):
        openmeteo.tabla_meteo(tmp_path)


def test_guardar_no_sobrescribe(tmp_path):
    momento = datetime(2024, 2, 3, tzinfo=UTC)
    dia = date(2024, 1, 1)
    contenido = json.dumps(respuesta_sintetica(dia, dia)).encode()
    openmeteo.guardar(tmp_path, "lugo", dia, dia, "url", contenido, momento)
    with pytest.raises(FileExistsError):
        openmeteo.guardar(tmp_path, "lugo", dia, dia, "url", contenido, momento)


def test_nulos_por_variable(tmp_path):
    respuesta = respuesta_sintetica(date(2024, 1, 1), date(2024, 1, 1))
    respuesta["hourly"]["wind_speed_100m_previous_day3"][:4] = [None] * 4
    contenido = json.dumps(respuesta).encode()
    momento = datetime(2024, 2, 3, tzinfo=UTC)
    dia = date(2024, 1, 1)
    openmeteo.guardar(tmp_path, "lugo", dia, dia, "url", contenido, momento)
    tabla = openmeteo.tabla_meteo(tmp_path)
    assert openmeteo.nulos_por_variable(tabla, tmp_path) == {
        "wind_speed_100m": 4,
        "shortwave_radiation": 0,
        "temperature_2m": 0,
    }


# descargar


def test_descargar_no_reintenta_un_400(monkeypatch):
    llamadas = []

    def urlopen(url, timeout):
        llamadas.append(url)
        cuerpo = io.BytesIO(b'{"error":true,"reason":"Variable desconocida"}')
        raise urllib.error.HTTPError(url, 400, "Bad Request", None, cuerpo)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(RuntimeError, match="Variable desconocida"):
        openmeteo.descargar("https://ejemplo", espera=0)
    assert len(llamadas) == 1


def test_descargar_reintenta_un_429(monkeypatch):
    llamadas = []

    def urlopen(url, timeout):
        llamadas.append(url)
        if len(llamadas) < 3:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", None, None)
        return io.BytesIO(b"{}")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert openmeteo.descargar("https://ejemplo", espera=0) == b"{}"
    assert len(llamadas) == 3


def test_descargar_falla_tras_los_intentos(monkeypatch):
    def urlopen(url, timeout):
        raise urllib.error.URLError("caída")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(RuntimeError, match="3 intentos"):
        openmeteo.descargar("https://ejemplo", espera=0)


# Parquet


def test_parquet_conserva_tipos_y_zona(tmp_path):
    ejecutar(tmp_path, DescargaFalsa())
    tabla = leer_tabla(tmp_path)
    assert str(tabla["prevista_utc"].dt.tz) == "UTC"
    assert str(tabla["emision_utc"].dt.tz) == "UTC"
    assert isinstance(tabla["punto"].dtype, pd.CategoricalDtype)
    assert tabla["dias_previos"].dtype == "int8"
    assert not (tmp_path / "meteo" / "meteo_prevista.parquet.tmp").exists()
