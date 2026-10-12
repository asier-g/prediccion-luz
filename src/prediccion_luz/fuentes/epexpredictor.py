"""Archivo diario, cifrado, de la previsión de EpexPredictor para España.

Su API solo sirve la previsión actual: lo que no se guarda cada día se pierde.
Se captura a la hora de nuestro corte (D a las 15:00, Madrid) para que la
comparación de la tarea 3.4 sea justa, y se guarda cifrada: el archivo y las
comparaciones son privados aunque el repositorio sea público.

Uso:
    CLAVE_ARCHIVO=... python -m prediccion_luz.fuentes.epexpredictor <carpeta>
"""

import argparse
import gzip
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from datetime import time as hora_del_dia
from pathlib import Path
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet

MADRID = ZoneInfo("Europe/Madrid")
URL = "https://epexpredictor.batzill.com/prices"
# Resolución nativa (15 min), en €/MWh y con las horas en UTC, como el resto de datos.
PARAMETROS = {"region": "ES", "unit": "EUR_PER_MWH", "timezone": "UTC"}
# Ventana de captura en hora de Madrid: desde el corte, con margen para los
# retrasos del cron de GitHub. Fuera de ella, el workflow no hace nada.
INICIO_VENTANA = hora_del_dia(15)
FIN_VENTANA = hora_del_dia(18)
# La previsión debe llegar al menos hasta el final de D+3 (Madrid).
DIAS_MINIMOS = 3
EXTENSION = ".json.gz.cifrado"
VARIABLE_CLAVE = "CLAVE_ARCHIVO"


def url_peticion() -> str:
    return f"{URL}?{urllib.parse.urlencode(PARAMETROS)}"


def _exigir_zona(momento: datetime) -> None:
    if momento.tzinfo is None:
        raise ValueError(f"Fecha sin zona horaria: {momento!r}")


def fecha_madrid(momento: datetime) -> date:
    _exigir_zona(momento)
    return momento.astimezone(MADRID).date()


def ruta_fichero(carpeta: Path, momento: datetime) -> Path:
    """Un fichero por día, con la fecha de Madrid del momento de captura."""
    fecha = fecha_madrid(momento)
    return carpeta / f"{fecha:%Y}" / f"{fecha.isoformat()}{EXTENSION}"


def en_ventana(momento: datetime) -> bool:
    _exigir_zona(momento)
    return INICIO_VENTANA <= momento.astimezone(MADRID).time() < FIN_VENTANA


def descargar(url: str, intentos: int = 3, espera: float = 30.0) -> dict:
    """Descarga y decodifica el JSON. Tras `intentos` fallos, lanza RuntimeError."""
    for intento in range(1, intentos + 1):
        try:
            with urllib.request.urlopen(url, timeout=30) as respuesta:
                return json.load(respuesta)
        except (OSError, ValueError) as error:
            if intento == intentos:
                raise RuntimeError(
                    f"EpexPredictor no responde tras {intentos} intentos: {error}"
                ) from error
            print(f"Intento {intento} fallido ({error}); se reintenta", file=sys.stderr)
            time.sleep(espera * intento)
    raise AssertionError("inalcanzable")


def _leer_fecha_utc(texto: object) -> datetime:
    if not isinstance(texto, str):
        raise ValueError(f"Fecha no válida: {texto!r}")
    momento = datetime.fromisoformat(texto)
    if momento.utcoffset() != timedelta(0):
        raise ValueError(f"Fecha que no está en UTC: {texto!r}")
    return momento


def validar(respuesta: object, momento: datetime) -> None:
    """Lanza ValueError si la respuesta no tiene el formato esperado o no
    cubre hasta el final de D+3, siendo D la fecha de Madrid de `momento`."""
    if not isinstance(respuesta, dict):
        raise ValueError("La respuesta no es un objeto JSON")
    for campo in ("prices", "knownUntil"):
        if campo not in respuesta:
            raise ValueError(f"Falta el campo {campo!r}")
    precios = respuesta["prices"]
    if not isinstance(precios, list) or not precios:
        raise ValueError("La lista de precios está vacía")
    _leer_fecha_utc(respuesta["knownUntil"])

    ultimo_inicio = None
    for periodo in precios:
        if not isinstance(periodo, dict) or not {"startsAt", "total"} <= periodo.keys():
            raise ValueError(f"Periodo sin 'startsAt' o 'total': {periodo!r}")
        inicio = _leer_fecha_utc(periodo["startsAt"])
        total = periodo["total"]
        if isinstance(total, bool) or not isinstance(total, int | float):
            raise ValueError(f"Precio no numérico: {total!r}")
        if not math.isfinite(total):
            raise ValueError(f"Precio no finito: {total!r}")
        ultimo_inicio = inicio if ultimo_inicio is None else max(ultimo_inicio, inicio)

    dia_siguiente = fecha_madrid(momento) + timedelta(days=DIAS_MINIMOS + 1)
    fin_minimo = datetime.combine(dia_siguiente, hora_del_dia(0), tzinfo=MADRID)
    # Vale tanto si el último periodo es de 15 min como si es de una hora.
    if ultimo_inicio < fin_minimo - timedelta(hours=1):
        raise ValueError(
            f"La previsión acaba en {ultimo_inicio.isoformat()}: "
            f"no llega al final de D+{DIAS_MINIMOS}"
        )


def cifrar(datos: dict, clave: str | bytes) -> bytes:
    comprimido = gzip.compress(json.dumps(datos, ensure_ascii=False).encode(), mtime=0)
    return Fernet(clave).encrypt(comprimido)


def descifrar(cifrado: bytes, clave: str | bytes) -> dict:
    return json.loads(gzip.decompress(Fernet(clave).decrypt(cifrado)))


def guardar(
    carpeta: Path, capturado: datetime, url: str, respuesta: dict, clave: str | bytes
) -> Path:
    """Guarda la respuesta tal cual, dentro de un sobre con su origen y hora de
    captura. Nunca sobrescribe: si el fichero del día ya existe, falla."""
    ruta = ruta_fichero(carpeta, capturado)
    sobre = {
        "fuente": "EpexPredictor",
        "url": url,
        "capturado_utc": capturado.astimezone(UTC).isoformat(),
        "respuesta": respuesta,
    }
    datos = cifrar(sobre, clave)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("xb") as fichero:
        fichero.write(datos)
    return ruta


def main(
    argv: list[str] | None = None,
    ahora: Callable[[], datetime] = lambda: datetime.now(UTC),
    descarga: Callable[[str], dict] = descargar,
) -> int:
    parser = argparse.ArgumentParser(
        description="Guarda, cifrada, la previsión actual de EpexPredictor para España."
    )
    parser.add_argument("carpeta", type=Path, help="carpeta del archivo")
    parser.add_argument(
        "--forzar",
        action="store_true",
        help="captura fuera de la ventana de 15:00 a 18:00 (solo pruebas manuales)",
    )
    args = parser.parse_args(argv)

    clave = os.environ.get(VARIABLE_CLAVE)
    if not clave:
        print(f"Falta la variable de entorno {VARIABLE_CLAVE}", file=sys.stderr)
        return 2
    Fernet(clave)  # Falla ya si la clave no tiene el formato correcto.

    momento = ahora()
    ruta = ruta_fichero(args.carpeta, momento)
    if ruta.exists():
        print(f"Nada que hacer: ya existe {ruta}")
        return 0
    if not args.forzar and not en_ventana(momento):
        hora = momento.astimezone(MADRID)
        print(f"Nada que hacer: son las {hora:%H:%M} en Madrid, fuera de la ventana")
        return 0

    url = url_peticion()
    respuesta = descarga(url)
    capturado = ahora()
    validar(respuesta, capturado)
    print(f"Guardado {guardar(args.carpeta, capturado, url, respuesta, clave)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
