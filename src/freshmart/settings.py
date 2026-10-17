# Rutas necesarias para el proyecto

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

DATA_DIR = ROOT_DIR / "data"
REPORTS_DIR = ROOT_DIR / "reports"
REPORT_PATH = REPORTS_DIR / "exploracion_campana.json"

SQL_DIR = ROOT_DIR / "sql"
SEGMENTATION_PATH = DATA_DIR / "segmentacion_campana.csv"

LAKE_ROOT = ROOT_DIR / "freshmart-lake"
RAW_DIR = LAKE_ROOT / "raw"
SILVER_DIR = LAKE_ROOT / "silver"
GOLD_DIR = LAKE_ROOT / "gold"
