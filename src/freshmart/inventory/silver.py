"""Silver del inventario diario: una foto de stock por producto, tienda y día.

Mismo esquema que las campañas (limpieza pura → validación → Parquet atómico), con lo
que trae este archivo:

* Filas duplicadas exactas (el mismo batch ingestado dos veces): se eliminan.
* Stock negativo (imposible físicamente) y otras filas imposibles: a cuarentena.
  Las 5 claves que llegan con dos versiones distintas tienen una negativa: al apartarla
  la clave queda única.
* Que falte un producto en una tienda NO es un error: es el surtido de cada tienda.

Validaciones de tabla (si fallan no se escribe nada): no vacío, clave
(producto, tienda, fecha) única y productos que existen en el catálogo.
Salida: ``silver/inventario_diario/fecha=AAAA-MM-DD/part-0.parquet``.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from freshmart.campaigns.clean import eliminar_duplicados, normalizar_enteros
from freshmart.catalog.silver import TABLA_PRODUCTOS
from freshmart.lake.parquet import escribir_parquet_atomico
from freshmart.quality.cuarentena import (
    Cuarentena,
    escribir_cuarentena,
    separar_cuarentena,
)
from freshmart.quality.result import InformeCalidad, ResultadoValidacion

logger = logging.getLogger(__name__)

INVENTARIO_CSV = "inventario_diario.csv"
TABLA_INVENTARIO = "inventario_diario"
CLAVE = ["producto_id", "tienda_id", "fecha"]
COLUMNAS_ENTERAS = (
    "producto_id",
    "tienda_id",
    "stock_actual",
    "stock_minimo",
    "stock_seguridad",
    "unidades_vendidas",
    "unidades_recibidas",
)


class InventarioValidationError(Exception):
    """Falla una validación de tabla: no se escribió nada en silver."""

    def __init__(self, informe: InformeCalidad) -> None:
        super().__init__(informe.resumen())
        self.informe = informe


@dataclass(frozen=True)
class InventarioResult:
    filas: int
    cuarentena: int
    informe: InformeCalidad
    destino: Path


def limpiar_inventario(raw: pd.DataFrame) -> pd.DataFrame:
    df = eliminar_duplicados(raw)
    for columna in COLUMNAS_ENTERAS:
        df[columna] = normalizar_enteros(df[columna])
    df["fecha"] = pd.to_datetime(df["fecha"], format="%Y-%m-%d")
    return df


def reglas_de_fila(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Máscaras de filas imposibles (True = incumple)."""
    return {
        "stock_negativo": df["stock_actual"] < 0,
        "umbrales_negativos": (df["stock_minimo"] < 0) | (df["stock_seguridad"] < 0),
        "movimientos_negativos": (df["unidades_vendidas"] < 0)
        | (df["unidades_recibidas"] < 0),
        "seguridad_mayor_que_minimo": df["stock_seguridad"] > df["stock_minimo"],
    }


def marcar_alertas(df: pd.DataFrame) -> pd.DataFrame:
    """Flags de reposición: sin stock, por debajo del stock de seguridad y del mínimo."""
    return df.assign(
        sin_stock=(df["stock_actual"] == 0).astype(bool),
        bajo_seguridad=(df["stock_actual"] < df["stock_seguridad"]).astype(bool),
        bajo_minimo=(df["stock_actual"] < df["stock_minimo"]).astype(bool),
    )


def validar_inventario(
    df: pd.DataFrame, productos: pd.DataFrame
) -> list[ResultadoValidacion]:
    repetidas = int(df.duplicated(CLAVE).sum())
    fuera = int((~df["producto_id"].isin(productos["producto_id"])).sum())
    return [
        ResultadoValidacion("no_vacio", len(df) > 0, f"{len(df)} filas"),
        ResultadoValidacion(
            "clave_unica",
            repetidas == 0,
            f"{repetidas} filas con (producto, tienda, fecha) repetido",
        ),
        ResultadoValidacion(
            "producto_en_catalogo",
            fuera == 0,
            f"{fuera} filas de productos desconocidos",
        ),
    ]


def preparar_inventario(
    raw: pd.DataFrame, productos: pd.DataFrame
) -> tuple[pd.DataFrame, Cuarentena, InformeCalidad]:
    """Limpieza + cuarentena + validación, sin escribir nada."""
    cuarentena = separar_cuarentena(
        limpio := limpiar_inventario(raw), reglas_de_fila(limpio)
    )
    df = marcar_alertas(cuarentena.validas)
    informe = InformeCalidad(
        titulo="Validaciones inventario_diario",
        resultados=(*validar_inventario(df, productos), *cuarentena.resultados()),
    )
    return df, cuarentena, informe


def escribir_inventario(df: pd.DataFrame, silver_dir: Path) -> Path:
    """Una partición por fecha (cada día es una foto nueva del stock)."""
    tabla = silver_dir / TABLA_INVENTARIO
    for fecha, dia in df.groupby("fecha"):
        particion = tabla / f"fecha={pd.Timestamp(fecha):%Y-%m-%d}"  # type: ignore[arg-type]
        escribir_parquet_atomico(dia.drop(columns="fecha"), particion)
    return tabla


def run_inventario(input_dir: Path, silver_dir: Path) -> InventarioResult:
    productos_dir = silver_dir / TABLA_PRODUCTOS
    if not productos_dir.is_dir():
        raise FileNotFoundError(
            f"Falta {productos_dir}: ejecuta antes el catálogo "
            "(python scripts/ejecutar_pipeline.py --catalog ...)."
        )

    raw = pd.read_csv(input_dir / INVENTARIO_CSV, dtype=str)
    df, cuarentena, informe = preparar_inventario(raw, pd.read_parquet(productos_dir))
    for r in informe.resultados:
        (logger.info if r.ok else logger.warning)(
            "[inventario] %s: %s", r.nombre, r.detalle
        )
    if not informe.ok:
        raise InventarioValidationError(informe)

    destino = escribir_inventario(df, silver_dir)
    escribir_cuarentena(cuarentena.apartadas, silver_dir, TABLA_INVENTARIO)
    return InventarioResult(len(df), len(cuarentena.apartadas), informe, destino)
