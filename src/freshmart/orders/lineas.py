"""Silver de las líneas de pedido (``lineas_pedido.csv``).

    python -m freshmart.orders.lineas --input data --silver-dir freshmart-lake/silver

Filas imposibles a cuarentena (no se borran): cantidad ≤ 0, precio negativo, descuento
fuera de 0–100 y ``total_linea`` que no cuadra con cantidad × precio × (1 − descuento).
Se avisa, sin apartar, de los precios a 0 (¿regalos o promociones?) y de los productos
que no están en el catálogo.

Ojo: la suma de las líneas NO cuadra con ``total_neto`` de ``pedidos.csv`` en casi
ningún pedido. No se construye nada que dependa de esa conciliación hasta aclararla.
"""

import argparse
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from freshmart.campaigns.clean import normalizar_enteros
from freshmart.catalog.silver import TABLA_PRODUCTOS
from freshmart.lake.parquet import escribir_parquet_atomico
from freshmart.logging_config import configurar_logging
from freshmart.quality.cuarentena import escribir_cuarentena, separar_cuarentena
from freshmart.quality.result import InformeCalidad, ResultadoValidacion, Severidad

logger = logging.getLogger(__name__)

LINEAS_CSV = "lineas_pedido.csv"
TABLA_LINEAS = "lineas_pedido"
TOLERANCIA_TOTAL = 0.011  # el total viene redondeado a céntimos


class LineasValidationError(Exception):
    def __init__(self, informe: InformeCalidad) -> None:
        super().__init__(informe.resumen())
        self.informe = informe


@dataclass(frozen=True)
class LineasResult:
    filas: int
    cuarentena: int
    informe: InformeCalidad
    destino: Path


def limpiar_lineas(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    for columna in ("linea_id", "pedido_id", "producto_id", "cantidad"):
        df[columna] = normalizar_enteros(df[columna])
    for columna in ("precio_unitario", "descuento_pct", "total_linea"):
        df[columna] = pd.to_numeric(df[columna], errors="raise").astype("float64")
    return df


def total_calculado(df: pd.DataFrame) -> pd.Series:
    return (
        df["cantidad"].astype("float64")
        * df["precio_unitario"]
        * (1 - df["descuento_pct"] / 100)
    ).round(2)


def reglas_de_fila(df: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "cantidad_no_positiva": df["cantidad"] <= 0,
        "precio_negativo": df["precio_unitario"] < 0,
        "descuento_fuera_de_rango": ~df["descuento_pct"].between(0, 100),
        "total_inconsistente": (total_calculado(df) - df["total_linea"]).abs()
        > TOLERANCIA_TOTAL,
    }


def validar_lineas(
    df: pd.DataFrame, productos: pd.DataFrame
) -> list[ResultadoValidacion]:
    repetidas = int(df["linea_id"].duplicated().sum())
    precio_cero = int((df["precio_unitario"] == 0).sum())
    fuera = int((~df["producto_id"].isin(productos["producto_id"])).sum())
    return [
        ResultadoValidacion("no_vacio", len(df) > 0, f"{len(df)} filas"),
        ResultadoValidacion("linea_id_unico", repetidas == 0, f"{repetidas} repetidas"),
        ResultadoValidacion(
            "precio_cero",
            precio_cero == 0,
            f"{precio_cero} líneas a 0 € (¿regalos o promociones? consultar)",
            Severidad.AVISO,
        ),
        ResultadoValidacion(
            "producto_en_catalogo",
            fuera == 0,
            f"{fuera} líneas de productos que no están en el catálogo",
            Severidad.AVISO,
        ),
    ]


def run_lineas(input_dir: Path, silver_dir: Path) -> LineasResult:
    productos_dir = silver_dir / TABLA_PRODUCTOS
    if not productos_dir.is_dir():
        raise FileNotFoundError(f"Falta {productos_dir}: ejecuta antes el catálogo.")

    limpio = limpiar_lineas(pd.read_csv(input_dir / LINEAS_CSV, dtype=str))
    cuarentena = separar_cuarentena(limpio, reglas_de_fila(limpio))
    informe = InformeCalidad(
        titulo="Validaciones lineas_pedido",
        resultados=(
            *validar_lineas(cuarentena.validas, pd.read_parquet(productos_dir)),
            *cuarentena.resultados(),
        ),
    )
    for r in informe.resultados:
        (logger.info if r.ok else logger.warning)(
            "[lineas] %s: %s", r.nombre, r.detalle
        )
    if not informe.ok:
        raise LineasValidationError(informe)

    destino = escribir_parquet_atomico(cuarentena.validas, silver_dir / TABLA_LINEAS)
    escribir_cuarentena(cuarentena.apartadas, silver_dir, TABLA_LINEAS)
    return LineasResult(
        len(cuarentena.validas), len(cuarentena.apartadas), informe, destino
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Líneas de pedido a silver.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--silver-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    configurar_logging()

    try:
        resultado = run_lineas(args.input, args.silver_dir)
    except (LineasValidationError, FileNotFoundError) as error:
        print(error)
        print("Silver NO modificado.")
        return 1
    print(resultado.informe.resumen())
    print(f"Filas escritas: {resultado.filas} · en cuarentena: {resultado.cuarentena}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
