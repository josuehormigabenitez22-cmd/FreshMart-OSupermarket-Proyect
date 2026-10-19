"""Gold del inventario: salud del stock por tienda y día, para el equipo de Operaciones.

Granularidad tienda + día. Responde a "¿cuántos productos tengo sin stock o por debajo
del de seguridad en cada tienda?" sin que nadie tenga que agregar silver a mano.
"""

from pathlib import Path

import pandas as pd

from freshmart.inventory.silver import TABLA_INVENTARIO
from freshmart.lake.parquet import escribir_parquet_atomico

TABLA_TIENDA_DIA = "inventario_tienda_dia"


def construir_inventario_tienda_dia(inventario: pd.DataFrame) -> pd.DataFrame:
    gold = (
        inventario.assign(fecha=pd.to_datetime(inventario["fecha"].astype(str)))
        .groupby(["tienda_id", "fecha"], as_index=False)
        .agg(
            productos=("producto_id", "nunique"),
            sin_stock=("sin_stock", "sum"),
            bajo_seguridad=("bajo_seguridad", "sum"),
            bajo_minimo=("bajo_minimo", "sum"),
            stock_total=("stock_actual", "sum"),
            unidades_vendidas=("unidades_vendidas", "sum"),
            unidades_recibidas=("unidades_recibidas", "sum"),
        )
        .sort_values(["tienda_id", "fecha"], ignore_index=True)
    )
    gold["pct_bajo_seguridad"] = gold["bajo_seguridad"] / gold["productos"]
    enteros = [c for c in gold.columns if c not in ("fecha", "pct_bajo_seguridad")]
    return gold.astype({c: "int64" for c in enteros})


def run_gold_inventario(silver_dir: Path, gold_dir: Path) -> int:
    inventario = pd.read_parquet(silver_dir / TABLA_INVENTARIO)
    gold = construir_inventario_tienda_dia(inventario)
    escribir_parquet_atomico(gold, gold_dir / TABLA_TIENDA_DIA)
    return len(gold)
