"""Lectura y escritura de las tablas procesadas en Parquet."""

from pathlib import Path

import pandas as pd


def escribir_parquet(tabla: pd.DataFrame, ruta: Path) -> None:
    """Escribe en un temporal y lo renombra: una ejecución interrumpida nunca
    deja una tabla a medias."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + ".tmp")
    tabla.to_parquet(temporal, index=False)
    temporal.replace(ruta)


def leer_parquet(ruta: Path) -> pd.DataFrame:
    return pd.read_parquet(ruta)
