"""Segmentación de los clientes de la campaña por pedidos de los últimos 3 meses.

La base es la lista de la campaña (``campana_verano_clientes.csv``), con una fila por
cliente: la lista trae 15.247 filas porque un cliente aparece una vez por canal, pero son
14.946 clientes. Nombre y fecha de registro salen de la maestra (``clientes.csv``).

La misma lógica existe dos veces a propósito: en pandas (este módulo) y en SQL
(``sql/segmentacion_campana.sql``, ejecutado con DuckDB). ``verificar`` comprueba
que ambas dan exactamente el mismo resultado.
"""

import argparse
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from freshmart.settings import DATA_DIR, SEGMENTATION_PATH, SQL_DIR

FECHA_CORTE = date(2024, 9, 16)
REGISTRADOS_DESDE = pd.Timestamp("2024-06-01")
SQL_PATH = SQL_DIR / "segmentacion_campana.sql"
CAMPANA_CSV = "campana_verano_clientes.csv"

UMBRAL_PREMIUM = 7
UMBRAL_REGULAR = 2

COLUMNAS = [
    "cliente_id",
    "nombre",
    "fecha_registro",
    "pedidos_3m",
    "segmento_calculado",
]


def parsear_fechas_pedido(fechas: pd.Series) -> pd.Series:
    """Parsea fecha_pedido en dos pasadas: ISO primero y dd/mm/aaaa después."""
    resultado = pd.to_datetime(fechas, format="%Y-%m-%d %H:%M:%S", errors="coerce")

    pendientes = resultado.isna() & fechas.notna()
    if pendientes.any():
        resultado.loc[pendientes] = pd.to_datetime(
            fechas[pendientes],
            dayfirst=True,
            format="%d/%m/%Y %H:%M",
            errors="coerce",
        )

    sin_parsear = resultado.isna() & fechas.notna()
    if sin_parsear.any():
        ejemplos = fechas[sin_parsear].head(3).tolist()
        raise ValueError(
            f"{int(sin_parsear.sum())} fechas de pedido sin parsear: {ejemplos}"
        )

    return resultado


def deduplicar_clientes(clientes: pd.DataFrame) -> pd.DataFrame:
    """Deja una fila por cliente_id, prefiriendo el código postal completo."""
    df = clientes.copy()
    df["_cp_completo"] = df["codigo_postal"].str.len() == 5
    df["codigo_postal"] = df["codigo_postal"].str.zfill(5)

    df = df.sort_values(
        ["cliente_id", "_cp_completo", "telefono"],
        ascending=[True, False, True],
        kind="stable",
    )
    df = df.drop_duplicates("cliente_id", keep="first")
    return df.drop(columns="_cp_completo").reset_index(drop=True)


def contar_pedidos_3m(pedidos: pd.DataFrame, fecha_corte: date) -> pd.Series:
    """Pedidos no cancelados por cliente en [corte - 3 meses, corte)."""
    fechas = parsear_fechas_pedido(pedidos["fecha_pedido"])
    fin = pd.Timestamp(fecha_corte)
    inicio = fin - pd.DateOffset(months=3)

    en_ventana = (
        pedidos["cliente_id"].notna()
        & (pedidos["estado"] != "cancelado")
        & (fechas >= inicio)
        & (fechas < fin)
    )
    ids = pd.to_numeric(pedidos.loc[en_ventana, "cliente_id"]).astype("int64")
    return ids.groupby(ids).size().rename("pedidos_3m")


def asignar_segmento(pedidos_3m: pd.Series) -> pd.Series:
    segmento = pd.Series("nuevo", index=pedidos_3m.index, dtype=object)
    segmento[pedidos_3m >= UMBRAL_REGULAR] = "regular"
    segmento[pedidos_3m >= UMBRAL_PREMIUM] = "premium"
    return segmento


def segmentar_pandas(
    data_dir: Path = DATA_DIR,
    fecha_corte: date = FECHA_CORTE,
) -> pd.DataFrame:
    # Trampa 3: codigo_postal como str (y todo lo demás también, parseamos a mano).
    campana = pd.read_csv(data_dir / CAMPANA_CSV, dtype=str)
    clientes = pd.read_csv(data_dir / "clientes.csv", dtype=str)
    pedidos = pd.read_csv(data_dir / "pedidos.csv", dtype=str)

    # Base: una fila por cliente de la campaña (la lista repite por canal).
    base = (
        pd.to_numeric(campana["cliente_id"])
        .astype("int64")
        .drop_duplicates()
        .to_frame()
    )

    unicos = deduplicar_clientes(clientes)
    unicos["cliente_id"] = unicos["cliente_id"].astype("int64")

    conteo = contar_pedidos_3m(pedidos, fecha_corte)

    # Trampa 1: los dos joins son LEFT para no perder a los clientes de la campaña
    # sin ficha en la maestra ni a los que no tienen pedidos.
    df = base.merge(unicos, on="cliente_id", how="left").merge(
        conteo, left_on="cliente_id", right_index=True, how="left"
    )
    df["pedidos_3m"] = df["pedidos_3m"].fillna(0).astype("int64")
    df["fecha_registro"] = pd.to_datetime(df["fecha_registro"], format="%Y-%m-%d")
    df["segmento_calculado"] = asignar_segmento(df["pedidos_3m"])

    return normalizar(df)


def segmentar_sql(
    data_dir: Path = DATA_DIR,
    fecha_corte: date = FECHA_CORTE,
    sql_path: Path = SQL_PATH,
) -> pd.DataFrame:
    con = duckdb.connect()
    try:
        for vista, archivo in (
            ("campana_raw", CAMPANA_CSV),
            ("clientes_raw", "clientes.csv"),
            ("pedidos_raw", "pedidos.csv"),
        ):
            ruta = (data_dir / archivo).as_posix().replace("'", "''")
            con.execute(
                f"CREATE VIEW {vista} AS "
                f"SELECT * FROM read_csv('{ruta}', header=true, all_varchar=true)"
            )
        con.execute(
            "SET VARIABLE fecha_corte = CAST(? AS DATE)", [fecha_corte.isoformat()]
        )
        df = con.execute(sql_path.read_text(encoding="utf-8")).df()
    finally:
        con.close()

    return normalizar(df)


def normalizar(df: pd.DataFrame) -> pd.DataFrame:
    """Mismo orden, tipos e índice para poder comparar ambos motores."""
    df = df[COLUMNAS].copy()
    df["cliente_id"] = df["cliente_id"].astype("int64")
    df["pedidos_3m"] = df["pedidos_3m"].astype("int64")
    df["fecha_registro"] = pd.to_datetime(df["fecha_registro"]).astype("datetime64[ns]")
    df["nombre"] = df["nombre"].astype(object)
    df["segmento_calculado"] = df["segmento_calculado"].astype(object)
    return df.sort_values("cliente_id").reset_index(drop=True)


def verificar(
    data_dir: Path = DATA_DIR,
    fecha_corte: date = FECHA_CORTE,
) -> pd.DataFrame:
    """Ejecuta pandas y SQL y exige que den el mismo resultado."""
    resultado_pandas = segmentar_pandas(data_dir, fecha_corte)
    resultado_sql = segmentar_sql(data_dir, fecha_corte)
    pd.testing.assert_frame_equal(resultado_pandas, resultado_sql)
    return resultado_pandas


def resumen(df: pd.DataFrame) -> dict[str, int]:
    sin_pedidos = df["pedidos_3m"] == 0
    return {
        "clientes": len(df),
        "premium": int((df["segmento_calculado"] == "premium").sum()),
        "regular": int((df["segmento_calculado"] == "regular").sum()),
        "nuevo": int((df["segmento_calculado"] == "nuevo").sum()),
        "sin_pedidos": int(sin_pedidos.sum()),
        "sin_pedidos_desde_junio": int(
            (sin_pedidos & (df["fecha_registro"] >= REGISTRADOS_DESDE)).sum()
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Segmenta clientes por pedidos de los últimos 3 meses."
    )
    parser.add_argument("--input", type=Path, default=DATA_DIR)
    parser.add_argument("--output", type=Path, default=SEGMENTATION_PATH)
    parser.add_argument("--date", default=FECHA_CORTE.isoformat(), help="AAAA-MM-DD")
    parser.add_argument("--engine", choices=["pandas", "sql"], default="pandas")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Ejecuta pandas y SQL y comprueba que son idénticos.",
    )
    args = parser.parse_args()
    corte = date.fromisoformat(args.date)

    if args.verify:
        df = verificar(args.input, corte)
        print("OK: pandas y SQL (DuckDB) dan el mismo resultado.")
    elif args.engine == "sql":
        df = segmentar_sql(args.input, corte)
    else:
        df = segmentar_pandas(args.input, corte)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False, date_format="%Y-%m-%d")

    for clave, valor in resumen(df).items():
        print(f"{clave}: {valor}")
    print(f"Segmentación guardada en: {args.output}")


if __name__ == "__main__":
    main()
