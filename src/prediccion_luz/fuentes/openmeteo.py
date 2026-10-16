"""Meteorología prevista de Open-Meteo (Previous Runs API) en los puntos del modelo.

Descarga solo los días que faltan y reconstruye la tabla `meteo_prevista` en
Parquet. `<variable>_previous_dayK` es, según Open-Meteo, "the value predicted
24 hours before valid time" (K × 24 h): la antelación con la que se conocía.

Se pide sin `timezone` (GMT): con `Europe/Madrid`, Open-Meteo aplica el desfase
del momento de la petición a todas las horas y no sigue los cambios de hora.

Una petición con más de 10 variables o más de 2 semanas cuenta como varias
llamadas del límite gratuito (10.000 al día). Si el presupuesto del día se
acaba, se para y lo que falta se baja en la siguiente ejecución.

Uso:
    python -m prediccion_luz.fuentes.openmeteo <carpeta_datos> [--desde AAAA-MM-DD]
Crea `<carpeta_datos>/meteo/`.
"""

import argparse
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, timedelta
from datetime import time as hora_del_dia
from pathlib import Path

import pandas as pd

from prediccion_luz.almacen import escribir_parquet

PROVEEDOR = "open-meteo"
MODELO = "best_match"
URL_BASE = "https://previous-runs-api.open-meteo.com/v1/forecast"
# Los mismos 7 puntos del baseline: viento (norte y meseta), sol (sur) y Madrid.
PUNTOS = {
    "zaragoza": (41.65, -0.88),
    "burgos": (42.34, -3.70),
    "lugo": (43.01, -7.56),
    "albacete": (38.99, -1.86),
    "sevilla": (37.39, -5.98),
    "badajoz": (38.88, -6.97),
    "madrid": (40.42, -3.70),
}
# Variable y unidad con la que la devuelve Open-Meteo.
VARIABLES = {
    "wind_speed_100m": "km/h",
    "shortwave_radiation": "W/m²",
    "temperature_2m": "°C",
}
DIAS_PREVIOS = range(1, 8)
# Los primeros valores son del 19-01-2024 (radiación y temperatura) y del
# 16-02-2024 (viento): pedir antes gasta cuota en nulos.
DESDE = date(2024, 1, 1)
# Se pide hasta hoy (UTC) menos 2 días, para no guardar nunca un día al que aún
# le falte alguna ejecución del modelo.
MARGEN_DIAS = 2
# Llamadas ponderadas. La mitad del límite gratuito de 10.000 al día, que deja
# sitio a producción y a otras pruebas y no pasa del límite de 5.000 por hora.
PRESUPUESTO_DIARIO = 5000.0
RITMO_POR_MINUTO = 500.0  # El límite gratuito es de 600.
ERRORES_SEGUIDOS = 3  # Tras tantos fallos seguidos, se deja para otro día.
PATRON_NOMBRE = re.compile(r"^(\d{8})_(\d{8})\.json$")

COLUMNAS = [
    "proveedor",
    "modelo",
    "punto",
    "variable",
    "dias_previos",
    "emision_utc",
    "prevista_utc",
    "valor",
]
CLAVE = ["proveedor", "modelo", "punto", "variable", "dias_previos", "prevista_utc"]


# Variables, peso y URL


def nombre_columna(variable: str, dias_previos: int) -> str:
    return f"{variable}_previous_day{dias_previos}"


def columnas_api() -> list[str]:
    return [nombre_columna(v, k) for v in VARIABLES for k in DIAS_PREVIOS]


def peso(n_variables: int, n_dias: int) -> float:
    """Llamadas que cuenta Open-Meteo: más de 10 variables o de 14 días pesan
    proporcionalmente más."""
    return max(1.0, n_variables / 10) * max(1.0, n_dias / 14)


def peso_peticion(desde: date, hasta: date) -> float:
    return peso(len(columnas_api()), (hasta - desde).days + 1)


def url_peticion(punto: str, desde: date, hasta: date) -> str:
    latitud, longitud = PUNTOS[punto]
    parametros = {
        "latitude": latitud,
        "longitude": longitud,
        "hourly": ",".join(columnas_api()),
        "models": MODELO,
        "start_date": desde.isoformat(),
        "end_date": hasta.isoformat(),
    }
    return f"{URL_BASE}?{urllib.parse.urlencode(parametros, safe=',')}"


# Nombres y rutas


def carpeta_cruda(carpeta: Path) -> Path:
    return carpeta / "meteo" / "openmeteo"


def ruta_cruda(carpeta: Path, punto: str, desde: date, hasta: date) -> Path:
    return carpeta_cruda(carpeta) / punto / f"{desde:%Y%m%d}_{hasta:%Y%m%d}.json"


def leer_nombre(nombre: str) -> tuple[date, date] | None:
    """(desde, hasta) de un fichero crudo; None si el nombre no es de uno."""
    encontrado = PATRON_NOMBRE.match(nombre)
    if not encontrado:
        return None
    desde, hasta = (
        datetime.strptime(texto, "%Y%m%d").date()  # noqa: DTZ007
        for texto in encontrado.groups()
    )
    return desde, hasta


def ficheros_locales(carpeta: Path, punto: str) -> list[tuple[date, date]]:
    """(desde, hasta) de cada fichero crudo del punto."""
    raiz = carpeta_cruda(carpeta) / punto
    if not raiz.exists():
        return []
    rangos = (leer_nombre(ruta.name) for ruta in raiz.iterdir())
    return sorted(rango for rango in rangos if rango)


def dias(desde: date, hasta: date) -> list[date]:
    return [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]


def dias_cubiertos(carpeta: Path, punto: str) -> set[date]:
    return {
        d
        for desde, hasta in ficheros_locales(carpeta, punto)
        for d in dias(desde, hasta)
    }


# Planificación


def tramos(fechas: Iterable[date]) -> list[tuple[date, date]]:
    """Agrupa los días en tramos seguidos, sin cruzar de un mes natural a otro."""
    resultado: list[tuple[date, date]] = []
    for dia in sorted(fechas):
        if resultado:
            inicio, fin = resultado[-1]
            mismo_mes = (dia.year, dia.month) == (inicio.year, inicio.month)
            if mismo_mes and dia == fin + timedelta(days=1):
                resultado[-1] = (inicio, dia)
                continue
        resultado.append((dia, dia))
    return resultado


def peticiones_pendientes(
    carpeta: Path, desde: date, hasta: date
) -> list[tuple[str, date, date]]:
    """(punto, desde, hasta) de cada petición necesaria para cubrir los huecos."""
    pendientes = []
    for punto in PUNTOS:
        hay = dias_cubiertos(carpeta, punto)
        faltan = [d for d in dias(desde, hasta) if d not in hay]
        pendientes += [(punto, inicio, fin) for inicio, fin in tramos(faltan)]
    return pendientes


def gastado_hoy(carpeta: Path, hoy: date) -> float:
    """Peso de lo descargado hoy (UTC). El propio crudo hace de registro."""
    inicio = datetime.combine(hoy, hora_del_dia(0), tzinfo=UTC).timestamp()
    total = 0.0
    for ruta in carpeta_cruda(carpeta).glob("*/*.json"):
        # La fecha de modificación solo descarta lo antiguo sin abrirlo; manda
        # `descargado_utc` (una copia restaurada hoy tiene la fecha de hoy).
        if ruta.stat().st_mtime < inicio:
            continue
        sobre = json.loads(ruta.read_text(encoding="utf-8"))
        if datetime.fromisoformat(sobre["descargado_utc"]).date() == hoy:
            total += sobre["peso"]
    return total


# Validación y lectura


def _es_numero(valor: object) -> bool:
    return (
        isinstance(valor, int | float)
        and not isinstance(valor, bool)
        and math.isfinite(valor)
    )


def validar(respuesta: object, desde: date, hasta: date) -> None:
    """Lanza ValueError si la respuesta no es la que se pidió."""
    if not isinstance(respuesta, dict):
        raise ValueError("la respuesta no es un objeto JSON")
    if respuesta.get("error"):
        raise ValueError(f"Open-Meteo: {respuesta.get('reason')}")
    if respuesta.get("utc_offset_seconds") != 0:
        raise ValueError(
            f"desfase horario {respuesta.get('utc_offset_seconds')}, se esperaba 0"
        )
    horas = respuesta.get("hourly")
    unidades = respuesta.get("hourly_units")
    if not isinstance(horas, dict) or not isinstance(unidades, dict):
        raise ValueError("falta 'hourly' o 'hourly_units'")

    inicio = datetime.combine(desde, hora_del_dia(0))
    n_horas = 24 * ((hasta - desde).days + 1)
    esperadas = [
        f"{inicio + timedelta(hours=i):%Y-%m-%dT%H:%M}" for i in range(n_horas)
    ]
    if horas.get("time") != esperadas:
        raise ValueError(f"las horas no van seguidas de {desde} 00:00 a {hasta} 23:00")

    for variable, unidad in VARIABLES.items():
        for k in DIAS_PREVIOS:
            columna = nombre_columna(variable, k)
            valores = horas.get(columna)
            if not isinstance(valores, list) or len(valores) != n_horas:
                raise ValueError(f"{columna}: falta o no tiene {n_horas} valores")
            recibida = unidades.get(columna)
            if recibida != unidad:
                raise ValueError(
                    f"{columna}: unidad {recibida!r}, se esperaba {unidad!r}"
                )
            if not all(v is None or _es_numero(v) for v in valores):
                raise ValueError(f"{columna}: valor no numérico")


def hora_emision(prevista: pd.Series, dias_previos: pd.Series) -> pd.Series:
    """PROVISIONAL hasta la tarea 1.5: la hora nominal, K × 24 h antes de la
    prevista, que es como define Open-Meteo `previous_dayK`. La 1.5 la cambia
    por la hora de la ejecución del modelo que hay detrás."""
    return prevista - pd.to_timedelta(dias_previos, unit="D")


def leer_respuesta(respuesta: dict, punto: str) -> pd.DataFrame:
    """Respuesta (ya validada) a la tabla larga, sin los valores nulos."""
    horas = respuesta["hourly"]
    ancha = pd.DataFrame(
        {columna: horas[columna] for columna in columnas_api()}, dtype="float64"
    )
    ancha["prevista_utc"] = pd.to_datetime(horas["time"]).tz_localize(UTC)
    larga = ancha.melt(
        id_vars="prevista_utc", var_name="columna", value_name="valor"
    ).dropna(subset=["valor"])
    partes = larga["columna"].str.rsplit("_previous_day", n=1, expand=True)
    larga["variable"] = partes[0]
    larga["dias_previos"] = partes[1].astype("int8")
    larga["emision_utc"] = hora_emision(larga["prevista_utc"], larga["dias_previos"])
    larga["proveedor"] = PROVEEDOR
    larga["modelo"] = MODELO
    larga["punto"] = punto
    return larga[COLUMNAS].reset_index(drop=True)


# Tabla


def tabla_meteo(carpeta: Path) -> pd.DataFrame:
    """Une todo el crudo. Lanza ValueError si dos ficheros se solapan."""
    partes = []
    for punto in PUNTOS:
        for desde, hasta in ficheros_locales(carpeta, punto):
            ruta = ruta_cruda(carpeta, punto, desde, hasta)
            sobre = json.loads(ruta.read_text(encoding="utf-8"))
            partes.append(leer_respuesta(sobre["respuesta"], punto))
    if not partes:
        return pd.DataFrame(columns=COLUMNAS)
    tabla = pd.concat(partes, ignore_index=True)
    if tabla.duplicated(subset=CLAVE).any():
        raise ValueError("Horas repetidas entre ficheros del crudo")
    for columna in ("proveedor", "modelo", "punto", "variable"):
        tabla[columna] = tabla[columna].astype("category")
    return tabla.sort_values(CLAVE, ignore_index=True)


def nulos_por_variable(tabla: pd.DataFrame, carpeta: Path) -> dict[str, int]:
    """Horas cubiertas por el crudo sin valor, por variable (todas las K y puntos)."""
    horas = {p: 24 * len(dias_cubiertos(carpeta, p)) for p in PUNTOS}
    filas = tabla.groupby(["punto", "variable"], observed=True).size()
    return {
        variable: sum(
            horas[p] * len(DIAS_PREVIOS) - int(filas.get((p, variable), 0))
            for p in PUNTOS
        )
        for variable in VARIABLES
    }


# Descarga


def descargar(url: str, intentos: int = 3, espera: float = 10.0) -> bytes:
    """Reintenta errores de red, 429 y 5xx. Otro 4xx es un parámetro mal puesto:
    repetirlo solo gasta cuota. Lanza RuntimeError."""
    for intento in range(1, intentos + 1):
        try:
            with urllib.request.urlopen(url, timeout=120) as respuesta:
                return respuesta.read()
        except urllib.error.HTTPError as error:
            if error.code != 429 and error.code < 500:
                motivo = error.read()[:300].decode("utf-8", errors="replace")
                raise RuntimeError(f"{url}: HTTP {error.code} {motivo}") from error
            if intento == intentos:
                raise RuntimeError(
                    f"{url}: HTTP {error.code} tras {intentos} intentos"
                ) from error
        except OSError as error:
            if intento == intentos:
                raise RuntimeError(
                    f"{url}: sin respuesta tras {intentos} intentos"
                ) from error
        time.sleep(espera * intento)
    raise AssertionError("inalcanzable")


def guardar(
    carpeta: Path,
    punto: str,
    desde: date,
    hasta: date,
    url: str,
    contenido: bytes,
    momento: datetime,
) -> Path:
    """Valida y guarda la respuesta dentro de un sobre. Nunca sobrescribe."""
    respuesta = json.loads(contenido)
    validar(respuesta, desde, hasta)
    sobre = {
        "url": url,
        "descargado_utc": momento.isoformat(),
        "peso": peso_peticion(desde, hasta),
        "respuesta": respuesta,
    }
    ruta = ruta_cruda(carpeta, punto, desde, hasta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("x", encoding="utf-8") as destino:
        json.dump(sobre, destino, ensure_ascii=False)
    return ruta


def actualizar_crudo(
    carpeta: Path,
    desde: date,
    hasta: date,
    descarga: Callable[[str], bytes] = descargar,
    ahora: Callable[[], datetime] = lambda: datetime.now(UTC),
    dormir: Callable[[float], None] = time.sleep,
) -> tuple[list[Path], list[str], list[tuple[str, date, date]]]:
    """Descarga en serie lo que falta, dentro del presupuesto del día.

    Devuelve los guardados, los errores y las peticiones que quedan pendientes
    porque se acabó el presupuesto o porque Open-Meteo falla una y otra vez.
    """
    gastado = gastado_hoy(carpeta, ahora().date())
    peticiones = peticiones_pendientes(carpeta, desde, hasta)
    guardados: list[Path] = []
    errores: list[str] = []
    seguidos = 0
    for i, (punto, inicio, fin) in enumerate(peticiones):
        coste = peso_peticion(inicio, fin)
        if gastado + coste > PRESUPUESTO_DIARIO or seguidos >= ERRORES_SEGUIDOS:
            return guardados, errores, peticiones[i:]
        gastado += coste  # Una petición fallida también gasta cuota.
        url = url_peticion(punto, inicio, fin)
        try:
            guardados.append(
                guardar(carpeta, punto, inicio, fin, url, descarga(url), ahora())
            )
            seguidos = 0
        except (RuntimeError, ValueError, OSError) as error:
            errores.append(f"{punto} {inicio}–{fin}: {error}")
            seguidos += 1
        dormir(60 * coste / RITMO_POR_MINUTO)
    return guardados, errores, []


def main(
    argv: list[str] | None = None,
    descarga: Callable[[str], bytes] = descargar,
    ahora: Callable[[], datetime] = lambda: datetime.now(UTC),
    dormir: Callable[[float], None] = time.sleep,
) -> int:
    parser = argparse.ArgumentParser(
        description="Descarga lo que falta de Open-Meteo y reconstruye meteo_prevista."
    )
    parser.add_argument(
        "carpeta", type=Path, help="carpeta de datos (crea <carpeta>/meteo)"
    )
    parser.add_argument("--desde", type=date.fromisoformat, default=DESDE)
    parser.add_argument(
        "--sin-descarga", action="store_true", help="solo reconstruye la tabla"
    )
    args = parser.parse_args(argv)

    errores: list[str] = []
    if not args.sin_descarga:
        hasta = ahora().date() - timedelta(days=MARGEN_DIAS)
        guardados, errores, pendientes = actualizar_crudo(
            args.carpeta, args.desde, hasta, descarga, ahora, dormir
        )
        coste = sum(peso_peticion(*leer_nombre(r.name)) for r in guardados)
        print(f"Descargados {len(guardados)} ficheros nuevos (peso {coste:.1f})")
        if pendientes:
            restante = sum(peso_peticion(i, f) for _, i, f in pendientes)
            print(
                f"Quedan {len(pendientes)} peticiones (peso {restante:.1f}): "
                "se acabó el presupuesto del día o Open-Meteo falla. "
                "Vuelve a ejecutar mañana."
            )

    tabla = tabla_meteo(args.carpeta)
    escribir_parquet(tabla, args.carpeta / "meteo" / "meteo_prevista.parquet")
    print(f"Tabla: {len(tabla)} filas")
    for variable, nulos in nulos_por_variable(tabla, args.carpeta).items():
        if nulos:
            print(f"  {variable}: {nulos} horas sin valor")
    for error in errores:
        print(f"Error: {error}", file=sys.stderr)
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
