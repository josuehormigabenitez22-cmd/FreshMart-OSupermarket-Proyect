"""Capa gold de campañas: métricas para Marketing a partir de silver.

Dos tablas (ver docs/decisions/001-granularidad-gold.md):

* ``campaign_performance`` — una fila por campaña y día (166 con verano + primavera).
* ``campaign_top_products`` — una fila por campaña y producto, top N por revenue neto.

Definiciones (las mismas que se le explican a negocio):

* revenue bruto = precio × cantidad
* revenue neto  = bruto × (1 − descuento_pct / 100). Después de descuentos y ANTES de
  devoluciones (tardan hasta 14 días en registrarse).
* ticket medio  = revenue neto / número de transacciones.
* Las ventas anónimas cuentan en revenue y transacciones, no en clientes.

La misma lógica está en SQL (``sql/gold_*.sql``); ``verificar_gold`` exige que pandas
y DuckDB den el mismo resultado.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

from freshmart.campaigns.config import COL_CLIENTE_ANONIMO, Campaign, get_config
from freshmart.campaigns.pipeline import SILVER_TABLE
from freshmart.catalog.silver import TABLA_CATEGORIAS, TABLA_PRODUCTOS
from freshmart.lake.parquet import escribir_parquet_atomico
from freshmart.segmentation.segment import parsear_fechas_pedido
from freshmart.settings import SQL_DIR

logger = logging.getLogger(__name__)

TABLA_PERFORMANCE = "campaign_performance"
TABLA_TOP_PRODUCTS = "campaign_top_products"
TOP_N = 50  # María pide el top 10; se guarda más margen para el dashboard

COLUMNAS_PERFORMANCE = [
    "campana",
    "fecha",
    "revenue_bruto",
    "revenue_neto",
    "num_transacciones",
    "unidades_vendidas",
    "clientes_unicos",
    "ventas_anonimas",
    "productos_distintos",
    "ticket_medio",
    "revenue_neto_acumulado",
    "transacciones_acumuladas",
]
COLUMNAS_TOP_PRODUCTS = [
    "campana",
    "ranking",
    "producto_id",
    "producto_nombre",
    "marca",
    "categoria",
    "revenue_bruto",
    "revenue_neto",
    "unidades_vendidas",
    "compradores_unicos",
    "num_transacciones",
]


@dataclass(frozen=True)
class GoldResult:
    performance: int
    top_products: int
    destinos: tuple[Path, Path]


# --- Lógica (funciones puras) -------------------------------------------------


def _con_revenue(ventas: pd.DataFrame) -> pd.DataFrame:
    return ventas.assign(
        campana=ventas["campana"].astype(str),
        fecha=ventas["fecha_compra"].dt.normalize(),
        revenue_bruto=ventas["precio"] * ventas["cantidad"].astype("float64"),
    ).assign(
        revenue_neto=lambda d: (
            d["revenue_bruto"] * (1 - d["descuento_pct"].fillna(0) / 100)
        )
    )


def construir_campaign_performance(ventas: pd.DataFrame) -> pd.DataFrame:
    """Métricas diarias por campaña, con acumulados para los gráficos de evolución."""
    gold = (
        _con_revenue(ventas)
        .groupby(["campana", "fecha"], as_index=False)
        .agg(
            revenue_bruto=("revenue_bruto", "sum"),
            revenue_neto=("revenue_neto", "sum"),
            num_transacciones=("venta_id", "count"),
            unidades_vendidas=("cantidad", "sum"),
            clientes_unicos=("cliente_id", "nunique"),  # nunique ignora los anónimos
            ventas_anonimas=(COL_CLIENTE_ANONIMO, "sum"),
            productos_distintos=("producto_id", "nunique"),
        )
        .sort_values(["campana", "fecha"], ignore_index=True)
    )
    por_campana = gold.groupby("campana")
    gold = gold.assign(
        ticket_medio=gold["revenue_neto"] / gold["num_transacciones"],
        revenue_neto_acumulado=por_campana["revenue_neto"].cumsum(),
        transacciones_acumuladas=por_campana["num_transacciones"].cumsum(),
    )
    logger.info("campaign_performance: %d filas (campaña × día)", len(gold))
    return normalizar_performance(gold)


def construir_top_products(
    ventas: pd.DataFrame,
    productos: pd.DataFrame,
    categorias: pd.DataFrame,
    top_n: int = TOP_N,
) -> pd.DataFrame:
    """Top N productos por revenue neto en cada campaña (empates: menor producto_id)."""
    stats = (
        _con_revenue(ventas)
        .groupby(["campana", "producto_id"], as_index=False)
        .agg(
            revenue_bruto=("revenue_bruto", "sum"),
            revenue_neto=("revenue_neto", "sum"),
            unidades_vendidas=("cantidad", "sum"),
            compradores_unicos=("cliente_id", "nunique"),
            num_transacciones=("venta_id", "count"),
        )
    )
    catalogo = productos[["producto_id", "nombre", "marca", "categoria_id"]].rename(
        columns={"nombre": "producto_nombre"}
    )
    nombres_categoria = categorias[["categoria_id", "nombre"]].rename(
        columns={"nombre": "categoria"}
    )
    # LEFT JOIN: un producto que no está en el maestro sigue contando (sin nombre).
    stats = (
        stats.merge(catalogo, on="producto_id", how="left")
        .merge(nombres_categoria, on="categoria_id", how="left")
        .sort_values(
            ["campana", "revenue_neto", "producto_id"],
            ascending=[True, False, True],
            ignore_index=True,
        )
    )
    stats["ranking"] = stats.groupby("campana").cumcount() + 1  # = ROW_NUMBER()

    sin_maestro = int(stats["producto_nombre"].isna().sum())
    if sin_maestro:
        logger.warning("Productos vendidos que no están en el maestro: %d", sin_maestro)
    return normalizar_top_products(stats[stats["ranking"] <= top_n])


def clientes_nuevos_por_campana(
    pedidos: pd.DataFrame, clientes: pd.DataFrame
) -> pd.DataFrame:
    """Clientes nuevos por campaña, con las dos definiciones que se discutieron con María.

    * ``primera_compra``: clientes cuya primera compra de TODO el historial de pedidos
      (cualquier estado) cae dentro del periodo de la campaña. Es la que cuenta Laura.
    * ``registro_nuevo``: clientes (deduplicados) con ``fecha_registro`` en el periodo.

    La primera compra se busca en todo el historial: si solo se mirase la campaña,
    cualquier comprador saldría como "nuevo".
    """
    con_cliente = pedidos[pedidos["cliente_id"].notna()]
    fechas = parsear_fechas_pedido(con_cliente["fecha_pedido"])
    ids = pd.to_numeric(con_cliente["cliente_id"]).astype("int64")
    primera = fechas.groupby(ids).min().dt.normalize()

    registro = pd.to_datetime(
        clientes.drop_duplicates("cliente_id")["fecha_registro"], format="%Y-%m-%d"
    )

    filas = []
    for campaign in Campaign:
        config = get_config(campaign)
        inicio, fin = pd.Timestamp(config.fecha_min), pd.Timestamp(config.fecha_max)
        filas.append(
            {
                "campana": config.particion,
                "primera_compra": int(primera.between(inicio, fin).sum()),
                "registro_nuevo": int(registro.between(inicio, fin).sum()),
            }
        )
    return pd.DataFrame(filas)


def normalizar_performance(df: pd.DataFrame) -> pd.DataFrame:
    """Mismo orden y tipos sea cual sea el motor (pandas o DuckDB)."""
    df = df[COLUMNAS_PERFORMANCE].copy()
    df["campana"] = df["campana"].astype(str)
    df["fecha"] = pd.to_datetime(df["fecha"]).astype("datetime64[ns]")
    for columna in (
        "num_transacciones",
        "unidades_vendidas",
        "clientes_unicos",
        "ventas_anonimas",
        "productos_distintos",
        "transacciones_acumuladas",
    ):
        df[columna] = df[columna].astype("int64")
    for columna in (
        "revenue_bruto",
        "revenue_neto",
        "ticket_medio",
        "revenue_neto_acumulado",
    ):
        df[columna] = df[columna].astype("float64")
    return df.sort_values(["campana", "fecha"], ignore_index=True)


def normalizar_top_products(df: pd.DataFrame) -> pd.DataFrame:
    df = df[COLUMNAS_TOP_PRODUCTS].copy()
    df["campana"] = df["campana"].astype(str)
    for columna in (
        "ranking",
        "unidades_vendidas",
        "compradores_unicos",
        "num_transacciones",
    ):
        df[columna] = df[columna].astype("int64")
    for columna in ("revenue_bruto", "revenue_neto"):
        df[columna] = df[columna].astype("float64")
    df["producto_id"] = df["producto_id"].astype("Int64")
    for columna in ("producto_nombre", "marca", "categoria"):
        df[columna] = df[columna].astype("string")
    return df.sort_values(["campana", "ranking"], ignore_index=True)


# --- Entrada / salida -------------------------------------------------------------


def leer_silver(silver_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    faltan = [
        t
        for t in (SILVER_TABLE, TABLA_PRODUCTOS, TABLA_CATEGORIAS)
        if not (silver_dir / t).is_dir()
    ]
    if faltan:
        raise FileNotFoundError(
            f"Faltan tablas silver en {silver_dir}: {faltan}. "
            "Ejecuta antes el pipeline de campañas (--all) y el del catálogo (--catalog)."
        )
    return (
        pd.read_parquet(silver_dir / SILVER_TABLE),
        pd.read_parquet(silver_dir / TABLA_PRODUCTOS),
        pd.read_parquet(silver_dir / TABLA_CATEGORIAS),
    )


def run_gold(silver_dir: Path, gold_dir: Path, top_n: int = TOP_N) -> GoldResult:
    ventas, productos, categorias = leer_silver(silver_dir)
    performance = construir_campaign_performance(ventas)
    top = construir_top_products(ventas, productos, categorias, top_n)
    destinos = (
        escribir_parquet_atomico(performance, gold_dir / TABLA_PERFORMANCE),
        escribir_parquet_atomico(top, gold_dir / TABLA_TOP_PRODUCTS),
    )
    logger.info("Gold escrito en %s", gold_dir)
    return GoldResult(len(performance), len(top), destinos)


# --- Versión SQL (DuckDB) -----------------------------------------------------------


def _ruta_sql(path: Path) -> str:
    return path.as_posix().replace("'", "''")


def construir_gold_sql(
    silver_dir: Path, top_n: int = TOP_N
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ejecuta ``sql/gold_*.sql`` con DuckDB sobre los Parquet de silver."""
    con = duckdb.connect()
    try:
        ventas = _ruta_sql(silver_dir / SILVER_TABLE / "*" / "*.parquet")
        con.execute(
            "CREATE VIEW campaign_ventas AS SELECT * FROM "
            f"read_parquet('{ventas}', hive_partitioning = true)"
        )
        for tabla in (TABLA_PRODUCTOS, TABLA_CATEGORIAS):
            ruta = _ruta_sql(silver_dir / tabla / "*.parquet")
            con.execute(f"CREATE VIEW {tabla} AS SELECT * FROM read_parquet('{ruta}')")
        con.execute("SET VARIABLE top_n = ?", [top_n])

        performance = con.execute(
            (SQL_DIR / "gold_campaign_performance.sql").read_text(encoding="utf-8")
        ).df()
        top = con.execute(
            (SQL_DIR / "gold_campaign_top_products.sql").read_text(encoding="utf-8")
        ).df()
    finally:
        con.close()
    return normalizar_performance(performance), normalizar_top_products(top)


def verificar_gold(silver_dir: Path, top_n: int = TOP_N) -> None:
    """Falla si pandas y SQL no dan las mismas tablas gold (tolerancia en floats)."""
    ventas, productos, categorias = leer_silver(silver_dir)
    performance_sql, top_sql = construir_gold_sql(silver_dir, top_n)
    pd.testing.assert_frame_equal(
        construir_campaign_performance(ventas), performance_sql, rtol=1e-9
    )
    pd.testing.assert_frame_equal(
        construir_top_products(ventas, productos, categorias, top_n), top_sql, rtol=1e-9
    )
