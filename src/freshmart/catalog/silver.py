"""Silver del catálogo: productos y categorías (los necesita la capa gold).

Problemas del CSV de productos que se resuelven aquí:

* ``categoria_id`` llega como ``"22.0"`` → ``Int64``.
* ``es_perecedero`` mezcla ``no/false/FALSE/0/False`` con ``sí/true/TRUE/1/True``.
* ``dias_caducidad`` es nulo en los no perecederos → ``Int64`` con nulos.

Si una validación falla no se escribe ninguna de las dos tablas.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from freshmart.campaigns.clean import normalizar_enteros
from freshmart.lake.parquet import escribir_parquet_atomico
from freshmart.quality.result import ResultadoValidacion

logger = logging.getLogger(__name__)

PRODUCTOS_CSV = "productos.csv"
CATEGORIAS_CSV = "categorias.csv"
TABLA_PRODUCTOS = "productos"
TABLA_CATEGORIAS = "categorias"

VERDADEROS = frozenset({"true", "1", "sí", "si", "yes"})
FALSOS = frozenset({"false", "0", "no"})


class CatalogoValidationError(Exception):
    """El catálogo no pasa las validaciones: no se escribió nada en silver."""

    def __init__(self, fallos: list[ResultadoValidacion]) -> None:
        super().__init__("; ".join(f"{r.nombre}: {r.detalle}" for r in fallos))
        self.fallos = fallos


@dataclass(frozen=True)
class CatalogoResult:
    productos: int
    categorias: int
    destinos: tuple[Path, Path]


def normalizar_booleanos(valores: pd.Series) -> pd.Series:
    """Texto a ``boolean`` (con nulos). Un valor no reconocido lanza ValueError."""
    texto = valores.astype("string").str.strip().str.lower()
    desconocidos = texto.notna() & ~texto.isin(VERDADEROS | FALSOS)
    if desconocidos.any():
        ejemplos = valores[desconocidos].unique()[:3].tolist()
        raise ValueError(f"{valores.name}: valores booleanos desconocidos {ejemplos}")
    return texto.isin(VERDADEROS).astype("boolean").mask(texto.isna())


def limpiar_productos(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    for columna in ("producto_id", "categoria_id", "dias_caducidad"):
        df[columna] = normalizar_enteros(df[columna])
    for columna in ("precio_base", "peso_kg"):
        df[columna] = pd.to_numeric(df[columna], errors="raise").astype("float64")
    for columna in ("es_perecedero", "activo"):
        df[columna] = normalizar_booleanos(df[columna])
    df["fecha_alta"] = pd.to_datetime(df["fecha_alta"], format="%Y-%m-%d")
    logger.info("Productos limpios: %d", len(df))
    return df


def limpiar_categorias(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    for columna in ("categoria_id", "padre_id", "nivel"):
        df[columna] = normalizar_enteros(df[columna])
    logger.info("Categorías limpias: %d", len(df))
    return df


def _id_unico(df: pd.DataFrame, columna: str, nombre: str) -> ResultadoValidacion:
    nulos = int(df[columna].isna().sum())
    repetidos = int(df[columna].dropna().duplicated().sum())
    return ResultadoValidacion(
        nombre,
        len(df) > 0 and nulos == 0 and repetidos == 0,
        f"{len(df)} filas, {nulos} ids nulos, {repetidos} repetidos",
    )


def validar_catalogo(
    productos: pd.DataFrame, categorias: pd.DataFrame
) -> list[ResultadoValidacion]:
    huerfanos = productos["categoria_id"].notna() & ~productos["categoria_id"].isin(
        categorias["categoria_id"]
    )
    return [
        _id_unico(productos, "producto_id", "productos_id_unico"),
        _id_unico(categorias, "categoria_id", "categorias_id_unico"),
        ResultadoValidacion(
            "productos_categoria_existe",
            not huerfanos.any(),
            f"{int(huerfanos.sum())} productos con una categoría inexistente",
        ),
    ]


def run_catalogo(input_dir: Path, silver_dir: Path) -> CatalogoResult:
    """CSV de catálogo → limpieza → validación → silver/productos y silver/categorias."""
    productos = limpiar_productos(pd.read_csv(input_dir / PRODUCTOS_CSV, dtype=str))
    categorias = limpiar_categorias(pd.read_csv(input_dir / CATEGORIAS_CSV, dtype=str))

    resultados = validar_catalogo(productos, categorias)
    for r in resultados:
        (logger.info if r.ok else logger.error)(
            "[catalogo] %s: %s", r.nombre, r.detalle
        )
    fallos = [r for r in resultados if not r.ok]
    if fallos:
        raise CatalogoValidationError(fallos)

    destinos = (
        escribir_parquet_atomico(productos, silver_dir / TABLA_PRODUCTOS),
        escribir_parquet_atomico(categorias, silver_dir / TABLA_CATEGORIAS),
    )
    return CatalogoResult(len(productos), len(categorias), destinos)
