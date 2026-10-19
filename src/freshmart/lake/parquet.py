"""Escritura de tablas Parquet en el lake (silver y gold)."""

import shutil
from pathlib import Path

import pandas as pd

PARQUET_FILE = "part-0.parquet"


def escribir_parquet_atomico(df: pd.DataFrame, destino: Path) -> Path:
    """Escribe ``df`` en ``destino/part-0.parquet`` reemplazando el directorio entero.

    Se escribe primero en un directorio temporal oculto (que pyarrow ignora al leer)
    y se renombra al final, para no dejar nunca una tabla o partición a medias.
    """
    temporal = destino.with_name(f".{destino.name}.tmp")

    shutil.rmtree(temporal, ignore_errors=True)
    temporal.mkdir(parents=True)
    try:
        df.to_parquet(temporal / PARQUET_FILE, engine="pyarrow", index=False)
        if destino.exists():
            shutil.rmtree(destino)
        temporal.replace(destino)
    except Exception:
        shutil.rmtree(temporal, ignore_errors=True)
        raise

    return destino
