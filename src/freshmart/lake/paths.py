from datetime import date
from pathlib import Path


def raw_table_path(
    raw_dir: Path,
    source: str,
    table: str,
    ingestion_date: date,
) -> Path:
    """Construye la ruta particionada de una tabla en raw."""
    return (
        raw_dir
        / source
        / table
        / str(ingestion_date.year)
        / f"{ingestion_date.month:02d}"
        / f"{ingestion_date.day:02d}"
    )
