"""Pruebas de la descarga y lectura de OMIE.

Los `marginalpdbc_*` de `datos/omie/` son ficheros reales de OMIE (fuente: OMIE,
www.omie.es), sin modificar: uno por cada número de periodos posible, con los
cambios de hora antes y después del paso a 15 min (1-10-2025). El listado es
sintético, con la estructura de la página real.
"""

import io
import urllib.error
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from prediccion_luz import almacen
from prediccion_luz.fuentes import omie

DATOS = Path(__file__).parent / "datos" / "omie"
LISTADO = (DATOS / "listado_ejemplo.html").read_bytes()


def leer_ejemplo(dia: str) -> pd.DataFrame:
    fecha = datetime.strptime(dia, "%Y%m%d").date()  # noqa: DTZ007
    return omie.leer_bytes((DATOS / f"marginalpdbc_{dia}.1").read_bytes(), fecha, 1)


def texto_sintetico(fecha: date, precio: float = 50.0) -> str:
    filas = [
        f"{fecha:%Y;%m;%d};{p};{precio};{precio};"
        for p in range(1, omie.periodos_esperados(fecha) + 1)
    ]
    return "\n".join(["MARGINALPDBC;", *filas, "*"]) + "\n"


def utc(*args) -> pd.Timestamp:
    return pd.Timestamp(datetime(*args, tzinfo=UTC))


# Lectura: un caso por cada número de periodos


@pytest.mark.parametrize(
    ("dia", "periodos", "duracion", "primero", "ultimo"),
    [
        # Hora de invierno, UTC+1.
        ("20250101", 24, 60, utc(2024, 12, 31, 23), utc(2025, 1, 1, 22)),
        # Paso a verano: la medianoche es UTC+1 y el día acaba en UTC+2.
        ("20230326", 23, 60, utc(2023, 3, 25, 23), utc(2023, 3, 26, 21)),
        # Paso a invierno: empieza en UTC+2 y acaba en UTC+1.
        ("20241027", 25, 60, utc(2024, 10, 26, 22), utc(2024, 10, 27, 22)),
        ("20251001", 96, 15, utc(2025, 9, 30, 22), utc(2025, 10, 1, 21, 45)),
        ("20251026", 100, 15, utc(2025, 10, 25, 22), utc(2025, 10, 26, 22, 45)),
        ("20260329", 92, 15, utc(2026, 3, 28, 23), utc(2026, 3, 29, 21, 45)),
    ],
)
def test_leer_cada_numero_de_periodos(dia, periodos, duracion, primero, ultimo):
    tabla = leer_ejemplo(dia)
    assert len(tabla) == periodos
    assert (tabla["duracion_min"] == duracion).all()
    assert tabla["inicio_utc"].iloc[0] == primero
    assert tabla["inicio_utc"].iloc[-1] == ultimo
    assert tabla["inicio_utc"].diff().dropna().eq(pd.Timedelta(minutes=duracion)).all()
    assert tabla["periodo"].tolist() == list(range(1, periodos + 1))


def test_lee_la_columna_de_espana():
    tabla = leer_ejemplo("20251001")
    assert tabla["precio_es"].iloc[:4].tolist() == [105.1, 104.24, 102.28, 102.0]


def test_disponible_la_vispera_a_las_13_de_madrid():
    # 13:00 del 31-12 en invierno son las 12:00 UTC; el 25-03 todavía es invierno.
    assert (leer_ejemplo("20250101")["disponible_utc"] == utc(2024, 12, 31, 12)).all()
    assert (leer_ejemplo("20230326")["disponible_utc"] == utc(2023, 3, 25, 12)).all()


def test_periodos_esperados():
    assert omie.periodos_esperados(date(2025, 9, 30)) == 24
    assert omie.periodos_esperados(date(2025, 3, 30)) == 23
    assert omie.periodos_esperados(date(2025, 10, 1)) == 96
    assert omie.periodos_esperados(date(2025, 10, 26)) == 100
    assert omie.periodos_esperados(date(2026, 3, 29)) == 92


# Lectura: rechazos


@pytest.mark.parametrize(
    ("fecha", "texto", "mensaje"),
    [
        # 24 periodos en un día de 23 horas.
        (
            date(2025, 3, 30),
            texto_sintetico(date(2025, 3, 29)).replace("29;", "30;"),
            "23",
        ),
        # 96 periodos antes del paso a 15 min.
        (
            date(2024, 5, 1),
            texto_sintetico(date(2025, 10, 2)).replace("2025;10;02", "2024;05;01"),
            "24",
        ),
        # Falta el periodo 5.
        (
            date(2025, 1, 1),
            texto_sintetico(date(2025, 1, 1)).replace(
                "2025;01;01;5;", "2025;01;01;6;", 1
            ),
            "orden",
        ),
        # Fila de otro día.
        (date(2025, 1, 2), texto_sintetico(date(2025, 1, 1)), "otro día"),
        (date(2025, 1, 1), texto_sintetico(date(2025, 1, 1)).replace("*", ""), "pie"),
        (date(2025, 1, 1), "<html><body>Error</body></html>", "cabecera"),
        (
            date(2025, 1, 1),
            texto_sintetico(date(2025, 1, 1)).replace(";50.0;\n", ";;\n", 1),
            "no válida",
        ),
        (date(2025, 1, 1), texto_sintetico(date(2025, 1, 1), float("nan")), "finito"),
    ],
)
def test_leer_rechaza(fecha, texto, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        omie.leer_marginalpdbc(texto, fecha, 1)


# Tabla horaria


def test_horaria_es_la_media_de_los_cuartos():
    horaria = omie.tabla_horaria(leer_ejemplo("20251001"))
    assert len(horaria) == 24
    assert (horaria["n_periodos"] == 4).all()
    assert horaria["precio_es"].iloc[0] == pytest.approx(
        (105.1 + 104.24 + 102.28 + 102) / 4
    )
    assert horaria["precio_es"].iloc[1] == pytest.approx(
        (106.63 + 105.68 + 105.19 + 105.01) / 4
    )
    assert horaria["hora_local"].tolist() == list(range(24))


@pytest.mark.parametrize("dia", ["20250101", "20230326", "20241027"])
def test_horaria_de_dias_horarios_no_cambia_el_precio(dia):
    nativa = leer_ejemplo(dia)
    horaria = omie.tabla_horaria(nativa)
    assert horaria["precio_es"].tolist() == nativa["precio_es"].tolist()
    assert (horaria["n_periodos"] == 1).all()


@pytest.mark.parametrize(
    ("dia", "horas"),
    [
        # Falta la hora local 2 (de 02:00 se pasa a 03:00).
        ("20230326", [0, 1, *range(3, 24)]),
        ("20260329", [0, 1, *range(3, 24)]),
        # La hora local 2 se repite (de 03:00 se vuelve a 02:00).
        ("20241027", [0, 1, 2, 2, *range(3, 24)]),
        ("20251026", [0, 1, 2, 2, *range(3, 24)]),
    ],
)
def test_horaria_en_cambios_de_hora(dia, horas):
    horaria = omie.tabla_horaria(leer_ejemplo(dia))
    assert horaria["hora_local"].tolist() == horas
    assert horaria["inicio_utc"].diff().dropna().eq(pd.Timedelta(hours=1)).all()


def test_horaria_rechaza_horas_incompletas():
    nativa = leer_ejemplo("20251001").drop(index=3)
    with pytest.raises(ValueError, match="incompletas"):
        omie.tabla_horaria(nativa)


# Listado y nombres


def test_leer_nombres_del_listado():
    assert omie.leer_nombres(LISTADO.decode()) == {
        (date(2025, 10, 2), 1),
        (date(2025, 10, 1), 2),
        (date(2025, 9, 30), 1),
    }


def test_ruta_cruda(tmp_path):
    assert omie.ruta_cruda(tmp_path, date(2025, 10, 1), 2) == (
        tmp_path / "omie" / "marginalpdbc" / "2025" / "marginalpdbc_20251001.2"
    )


def test_huecos():
    dias = [date(2025, 1, 1), date(2025, 1, 3)]
    assert omie.huecos(dias, date(2025, 1, 1), date(2025, 1, 4)) == [
        date(2025, 1, 2),
        date(2025, 1, 4),
    ]


# Descarga incremental, con una descarga falsa


class DescargaFalsa:
    """Sirve el listado y un fichero sintético válido para cada nombre."""

    def __init__(self, listado=LISTADO, precio=50.0, falla=()):
        self.listado = listado
        self.precio = precio
        self.falla = set(falla)
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        if url == omie.URL_LISTADO:
            return self.listado
        nombre = url.rsplit("=", 1)[1]
        if nombre in self.falla:
            raise RuntimeError("caída")
        ((fecha, _),) = omie.leer_nombres(nombre)
        return texto_sintetico(fecha, self.precio).encode("latin-1")

    def ficheros(self):
        return sorted(u.rsplit("=", 1)[1] for u in self.urls if u != omie.URL_LISTADO)


def ejecutar(carpeta, descarga, *opciones):
    """`main` desde el primer día del listado de ejemplo."""
    argv = [str(carpeta), "--desde", "2025-09-30", *opciones]
    return omie.main(argv, descarga=descarga)


def test_main_descarga_y_no_repite(tmp_path):
    descarga = DescargaFalsa()
    assert ejecutar(tmp_path, descarga=descarga) == 0
    assert descarga.ficheros() == [
        "marginalpdbc_20250930.1",
        "marginalpdbc_20251001.2",
        "marginalpdbc_20251002.1",
    ]

    horaria = almacen.leer_parquet(tmp_path / "omie" / "omie_precio_horario.parquet")
    assert len(horaria) == 72
    nativa = almacen.leer_parquet(tmp_path / "omie" / "omie_precio.parquet")
    assert len(nativa) == 24 + 96 + 96

    # Segunda ejecución: solo se pide el listado.
    descarga.urls.clear()
    assert ejecutar(tmp_path, descarga=descarga) == 0
    assert descarga.urls == [omie.URL_LISTADO]


def test_correccion_nueva_se_guarda_junto_a_la_anterior(tmp_path):
    ejecutar(tmp_path, descarga=DescargaFalsa(precio=50.0))
    listado = LISTADO.replace(b"20251002.1", b"20251002.3")
    descarga = DescargaFalsa(listado=listado, precio=70.0)
    assert ejecutar(tmp_path, descarga=descarga) == 0
    assert descarga.ficheros() == ["marginalpdbc_20251002.3"]

    assert omie.ruta_cruda(tmp_path, date(2025, 10, 2), 1).exists()
    nativa = omie.tabla_nativa(tmp_path)
    dia = nativa[nativa["fecha"] == date(2025, 10, 2)]
    assert len(dia) == 96
    assert (dia["version"] == 3).all()
    assert (dia["precio_es"] == 70.0).all()


def test_fallo_de_descarga_no_guarda_y_devuelve_error(tmp_path, capsys):
    descarga = DescargaFalsa(falla={"marginalpdbc_20251001.2"})
    assert ejecutar(tmp_path, descarga=descarga) == 1
    assert not omie.ruta_cruda(tmp_path, date(2025, 10, 1), 2).exists()
    error = capsys.readouterr().err
    assert "marginalpdbc_20251001.2" in error
    assert "2025-10-01" in error  # Aparece también como hueco.


def test_fichero_no_valido_no_se_guarda(tmp_path):
    def descarga(url):
        return LISTADO if url == omie.URL_LISTADO else b"<html>Error</html>"

    assert ejecutar(tmp_path, descarga=descarga) == 1
    assert omie.ficheros_locales(tmp_path) == set()


def test_desde_filtra_el_listado(tmp_path):
    descarga = DescargaFalsa()
    omie.main([str(tmp_path), "--desde", "2025-10-01"], descarga=descarga)
    assert descarga.ficheros() == ["marginalpdbc_20251001.2", "marginalpdbc_20251002.1"]


def test_sin_descarga_no_usa_la_red(tmp_path):
    ejecutar(tmp_path, descarga=DescargaFalsa())
    descarga = DescargaFalsa()
    assert ejecutar(tmp_path, descarga, "--sin-descarga") == 0
    assert descarga.urls == []


def test_huecos_dan_error(tmp_path, capsys):
    # Sin el 20251001 en el listado, queda un hueco entre el 30-09 y el 02-10.
    listado = LISTADO.replace(b"marginalpdbc_20251001.2", b"")
    assert ejecutar(tmp_path, DescargaFalsa(listado=listado)) == 1
    assert "1 días sin precio: 2025-10-01" in capsys.readouterr().err


def test_descargar_reintenta(monkeypatch):
    llamadas = []

    def urlopen(url, timeout):
        llamadas.append(url)
        if len(llamadas) < 3:
            raise urllib.error.HTTPError(url, 404, "No encontrado", None, None)
        return io.BytesIO(b"MARGINALPDBC;")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert omie.descargar("https://ejemplo", espera=0) == b"MARGINALPDBC;"
    assert len(llamadas) == 3


def test_descargar_falla_tras_los_intentos(monkeypatch):
    def urlopen(url, timeout):
        raise urllib.error.URLError("caída")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(RuntimeError, match="3 intentos"):
        omie.descargar("https://ejemplo", espera=0)


# Parquet


def test_parquet_conserva_tipos_y_zona(tmp_path):
    nativa = leer_ejemplo("20241027")
    ruta = tmp_path / "t.parquet"
    almacen.escribir_parquet(nativa, ruta)
    leida = almacen.leer_parquet(ruta)
    assert str(leida["inicio_utc"].dt.tz) == "UTC"
    assert leida["inicio_utc"].tolist() == nativa["inicio_utc"].tolist()
    assert leida["fecha"].tolist() == nativa["fecha"].tolist()
    assert not ruta.with_name("t.parquet.tmp").exists()


def test_fechas_de_la_tabla_en_utc():
    inicio = leer_ejemplo("20250101")["inicio_utc"].iloc[0]
    assert inicio.tzinfo is not None and inicio.utcoffset() == timedelta(0)
