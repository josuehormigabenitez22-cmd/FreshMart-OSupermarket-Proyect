"""Rutas del proyecto.

Por defecto todo cuelga de la raíz del repo. Cada ruta se puede sobrescribir con
una variable de entorno (ver ``.env.example``) para ejecutar contra otro lake sin
tocar el código.
"""

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]


def _ruta(variable: str, por_defecto: Path) -> Path:
    valor = os.environ.get(variable)
    return Path(valor) if valor else por_defecto


DATA_DIR = _ruta("FRESHMART_DATA_DIR", ROOT_DIR / "data")
REPORTS_DIR = _ruta("FRESHMART_REPORTS_DIR", ROOT_DIR / "reports")
REPORT_PATH = REPORTS_DIR / "exploracion_campana.json"

SQL_DIR = ROOT_DIR / "sql"
SEGMENTATION_PATH = DATA_DIR / "segmentacion_campana.csv"

LAKE_ROOT = _ruta("FRESHMART_LAKE_DIR", ROOT_DIR / "freshmart-lake")
RAW_DIR = LAKE_ROOT / "raw"
SILVER_DIR = LAKE_ROOT / "silver"
GOLD_DIR = LAKE_ROOT / "gold"

LOG_LEVEL = os.environ.get("FRESHMART_LOG_LEVEL", "INFO")
