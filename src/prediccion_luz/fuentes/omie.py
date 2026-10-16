"""Precio del mercado diario de OMIE para España (fichero `marginalpdbc`).

Descarga solo los ficheros que faltan y reconstruye dos tablas Parquet: una con
la resolución nativa (60 min hasta el 30-09-2025, 15 min desde el 1-10-2025) y
otra horaria, media de los periodos de cada hora. Todo en UTC.

El listado de OMIE dice qué versión de cada día está publicada. Algunos días
solo existen corregidos (`.2`, `.3`): el baseline pedía siempre `.1` y los
perdía sin avisar.

Uso:
    python -m prediccion_luz.fuentes.omie <carpeta_datos> [--desde AAAA-MM-DD]
Crea `<carpeta_datos>/omie/`.
"""

import argparse
import math
import re
import sys
import time
import urllib.request
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from datetime import time as hora_del_dia
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from prediccion_luz.almacen import escribir_parquet

MADRID = ZoneInfo("Europe/Madrid")
URL_LISTADO = (
    "https://www.omie.es/es/file-access-list?parents%5B0%5D=/"
    "&parents%5B1%5D=Mercado%20Diario&parents%5B2%5D=1.%20Precios"
    "&dir=Precios%20horarios%20del%20mercado%20diario%20en%20Espa%C3%B1a"
    "&realdir=marginalpdbc"
)
URL_FICHERO = "https://www.omie.es/es/file-download?parents=marginalpdbc&filename={}"
# Primer día de entrega con 96 periodos de 15 min.
INICIO_CUARTOHORARIO = date(2025, 10, 1)
DESDE = date(2023, 1, 1)
HILOS = 4  # Máximo que se le pide a OMIE (CLAUDE.md).
# OMIE publica el precio de D+1 hacia las 13:00 de D. El listado no da la hora
# real de publicación (su "Modificado" cambia si el fichero se vuelve a subir),
# así que se usa la nominal.
HORA_PUBLICACION = hora_del_dia(13)
# Los zips anuales (marginalpdbc_2022.zip) no casan: solo ficheros diarios.
PATRON_NOMBRE = re.compile(r"marginalpdbc_(\d{8})\.(\d+)\b")

COLUMNAS_NATIVA = [
    "inicio_utc",
    "duracion_min",
    "fecha",
    "periodo",
    "precio_es",
    "version",
    "disponible_utc",
]
COLUMNAS_HORARIA = [
    "inicio_utc",
    "fecha",
    "hora_local",
    "precio_es",
    "n_periodos",
    "version",
    "disponible_utc",
]


# Nombres y rutas


def nombre_fichero(fecha: date, version: int) -> str:
    return f"marginalpdbc_{fecha:%Y%m%d}.{version}"


def leer_nombres(texto: str) -> set[tuple[date, int]]:
    """(fecha, versión) de cada fichero diario que aparece en `texto`."""
    return {
        (datetime.strptime(dia, "%Y%m%d").date(), int(version))  # noqa: DTZ007
        for dia, version in PATRON_NOMBRE.findall(texto)
    }


def carpeta_cruda(carpeta: Path) -> Path:
    return carpeta / "omie" / "marginalpdbc"


def ruta_cruda(carpeta: Path, fecha: date, version: int) -> Path:
    return carpeta_cruda(carpeta) / f"{fecha:%Y}" / nombre_fichero(fecha, version)


def ficheros_locales(carpeta: Path) -> set[tuple[date, int]]:
    raiz = carpeta_cruda(carpeta)
    if not raiz.exists():
        return set()
    return leer_nombres("\n".join(ruta.name for ruta in raiz.glob("*/marginalpdbc_*")))


# Lectura


def medianoche_utc(fecha: date) -> datetime:
    return datetime.combine(fecha, hora_del_dia(0), tzinfo=MADRID).astimezone(UTC)


def periodos_esperados(fecha: date) -> int:
    """23, 24 o 25 horas según el cambio de hora; por 4 desde el 1-10-2025."""
    horas = (medianoche_utc(fecha + timedelta(days=1)) - medianoche_utc(fecha)) / (
        timedelta(hours=1)
    )
    return int(horas) * (4 if fecha >= INICIO_CUARTOHORARIO else 1)


def disponible_utc(fecha: date) -> datetime:
    vispera = fecha - timedelta(days=1)
    return datetime.combine(vispera, HORA_PUBLICACION, tzinfo=MADRID).astimezone(UTC)


def leer_marginalpdbc(texto: str, fecha: date, version: int) -> pd.DataFrame:
    """Lee un fichero `marginalpdbc` a la tabla nativa.

    Formato: cabecera `MARGINALPDBC;`, una fila `AAAA;MM;DD;periodo;PT;ES;` por
    periodo y pie `*`. Lanza ValueError si algo no cuadra con `fecha`.
    """
    lineas = [linea.strip() for linea in texto.splitlines() if linea.strip()]
    if not lineas or lineas[0] != "MARGINALPDBC;":
        raise ValueError(f"{fecha}: falta la cabecera MARGINALPDBC")
    if lineas[-1] != "*":
        raise ValueError(f"{fecha}: falta el pie '*' (fichero incompleto)")

    precios = []
    for linea in lineas[1:-1]:
        campos = linea.split(";")
        if len(campos) < 6:
            raise ValueError(f"{fecha}: fila con menos de 6 campos: {linea!r}")
        try:
            fecha_fila = date(int(campos[0]), int(campos[1]), int(campos[2]))
            periodo = int(campos[3])
            precio = float(campos[5])
        except ValueError as error:
            raise ValueError(f"{fecha}: fila no válida: {linea!r}") from error
        if fecha_fila != fecha:
            raise ValueError(f"{fecha}: fila de otro día ({fecha_fila})")
        if periodo != len(precios) + 1:
            raise ValueError(f"{fecha}: periodo {periodo} fuera de orden")
        if not math.isfinite(precio):
            raise ValueError(f"{fecha}: precio no finito en el periodo {periodo}")
        precios.append(precio)

    esperados = periodos_esperados(fecha)
    if len(precios) != esperados:
        raise ValueError(f"{fecha}: {len(precios)} periodos, se esperaban {esperados}")

    duracion = 15 if fecha >= INICIO_CUARTOHORARIO else 60
    # UTC es continuo: contar periodos desde la medianoche de Madrid sitúa bien
    # los días de 23 y 25 horas sin casos especiales.
    inicio = pd.Timestamp(medianoche_utc(fecha))
    return pd.DataFrame(
        {
            "inicio_utc": inicio
            + pd.to_timedelta(range(esperados), unit="min") * duracion,
            "duracion_min": duracion,
            "fecha": fecha,
            "periodo": range(1, esperados + 1),
            "precio_es": precios,
            "version": version,
            "disponible_utc": pd.Timestamp(disponible_utc(fecha)),
        },
        columns=COLUMNAS_NATIVA,
    )


def leer_bytes(contenido: bytes, fecha: date, version: int) -> pd.DataFrame:
    return leer_marginalpdbc(contenido.decode("latin-1"), fecha, version)


# Tablas


def tabla_nativa(carpeta: Path) -> pd.DataFrame:
    """Une el crudo; de cada día, la versión más alta."""
    ultima: dict[date, int] = {}
    for fecha, version in ficheros_locales(carpeta):
        ultima[fecha] = max(version, ultima.get(fecha, 0))
    partes = [
        leer_bytes(ruta_cruda(carpeta, fecha, version).read_bytes(), fecha, version)
        for fecha, version in sorted(ultima.items())
    ]
    if not partes:
        return pd.DataFrame(columns=COLUMNAS_NATIVA)
    tabla = pd.concat(partes, ignore_index=True)
    if tabla["inicio_utc"].duplicated().any():
        raise ValueError("Periodos solapados entre días")
    return tabla


def tabla_horaria(nativa: pd.DataFrame) -> pd.DataFrame:
    """Media de los periodos de cada hora UTC. Los días tienen 23, 24 o 25 filas;
    en el de 25, la hora local 2 aparece dos veces."""
    if nativa.empty:
        return pd.DataFrame(columns=COLUMNAS_HORARIA)
    hora = nativa["inicio_utc"].dt.floor("h")
    horaria = (
        nativa.groupby(hora)
        .agg(
            fecha=("fecha", "first"),
            precio_es=("precio_es", "mean"),
            n_periodos=("periodo", "size"),
            duracion_min=("duracion_min", "first"),
            version=("version", "first"),
            disponible_utc=("disponible_utc", "first"),
        )
        .rename_axis("inicio_utc")
        .reset_index()
    )
    incompletas = horaria["n_periodos"] * horaria["duracion_min"] != 60
    if incompletas.any():
        raise ValueError(
            f"Horas incompletas: {horaria.loc[incompletas, 'inicio_utc'].tolist()}"
        )
    horaria["hora_local"] = horaria["inicio_utc"].dt.tz_convert(MADRID).dt.hour
    return horaria[COLUMNAS_HORARIA]


def huecos(fechas: Iterable[date], desde: date, hasta: date) -> list[date]:
    hay = set(fechas)
    todas = (desde + timedelta(days=i) for i in range((hasta - desde).days + 1))
    return [fecha for fecha in todas if fecha not in hay]


# Descarga


def descargar(url: str, intentos: int = 3, espera: float = 10.0) -> bytes:
    """Tras `intentos` fallos, lanza RuntimeError."""
    for intento in range(1, intentos + 1):
        try:
            with urllib.request.urlopen(url, timeout=60) as respuesta:
                return respuesta.read()
        except OSError as error:
            if intento == intentos:
                raise RuntimeError(
                    f"{url}: sin respuesta tras {intentos} intentos"
                ) from error
            time.sleep(espera * intento)
    raise AssertionError("inalcanzable")


def actualizar_crudo(
    carpeta: Path, desde: date, descarga: Callable[[str], bytes] = descargar
) -> tuple[list[Path], list[str], date | None]:
    """Descarga los ficheros del listado que no están en local.

    Devuelve los guardados, los errores y la última fecha publicada. Cada fichero
    se valida antes de guardarse y nunca se sobrescribe: una corrección (`.2`)
    se guarda junto a la versión anterior.
    """
    listado = descarga(URL_LISTADO).decode("utf-8", errors="replace")
    publicados = {(f, v) for f, v in leer_nombres(listado) if f >= desde}
    pendientes = sorted(publicados - ficheros_locales(carpeta))

    def bajar(fichero: tuple[date, int]) -> Path:
        fecha, version = fichero
        contenido = descarga(URL_FICHERO.format(nombre_fichero(fecha, version)))
        leer_bytes(contenido, fecha, version)
        ruta = ruta_cruda(carpeta, fecha, version)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with ruta.open("xb") as destino:
            destino.write(contenido)
        return ruta

    guardados, errores = [], []
    with ThreadPoolExecutor(HILOS) as hilos:
        futuros = {f: hilos.submit(bajar, f) for f in pendientes}
    for (fecha, version), futuro in futuros.items():
        try:
            guardados.append(futuro.result())
        except (RuntimeError, ValueError, OSError) as error:
            errores.append(f"{nombre_fichero(fecha, version)}: {error}")
    ultima = max((f for f, _ in publicados), default=None)
    return guardados, errores, ultima


def main(
    argv: list[str] | None = None, descarga: Callable[[str], bytes] = descargar
) -> int:
    parser = argparse.ArgumentParser(
        description="Descarga lo que falta de OMIE y reconstruye sus tablas Parquet."
    )
    parser.add_argument(
        "carpeta", type=Path, help="carpeta de datos (crea <carpeta>/omie)"
    )
    parser.add_argument("--desde", type=date.fromisoformat, default=DESDE)
    parser.add_argument(
        "--sin-descarga", action="store_true", help="solo reconstruye las tablas"
    )
    args = parser.parse_args(argv)

    errores: list[str] = []
    ultima = None
    if not args.sin_descarga:
        guardados, errores, ultima = actualizar_crudo(
            args.carpeta, args.desde, descarga
        )
        print(f"Descargados {len(guardados)} ficheros nuevos")

    nativa = tabla_nativa(args.carpeta)
    nativa = nativa[nativa["fecha"] >= args.desde].reset_index(drop=True)
    horaria = tabla_horaria(nativa)
    escribir_parquet(nativa, args.carpeta / "omie" / "omie_precio.parquet")
    escribir_parquet(horaria, args.carpeta / "omie" / "omie_precio_horario.parquet")
    print(f"Tablas: {len(nativa)} periodos, {len(horaria)} horas")

    if ultima is None and len(nativa):
        ultima = nativa["fecha"].max()
    faltan = huecos(nativa["fecha"], args.desde, ultima) if ultima else []
    for error in errores:
        print(f"Error: {error}", file=sys.stderr)
    if faltan:
        lista = ", ".join(map(str, faltan[:10])) + (", ..." if len(faltan) > 10 else "")
        print(f"{len(faltan)} días sin precio: {lista}", file=sys.stderr)
    return 1 if errores or faltan else 0


if __name__ == "__main__":
    sys.exit(main())
