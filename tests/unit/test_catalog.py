from io import StringIO
from pathlib import Path

import pandas as pd
import pytest

from freshmart.catalog.silver import (
    CatalogoValidationError,
    limpiar_categorias,
    limpiar_productos,
    normalizar_booleanos,
    run_catalogo,
    validar_catalogo,
)

PRODUCTOS = """producto_id,nombre,marca,categoria_id,precio_base,peso_kg,es_perecedero,dias_caducidad,activo,fecha_alta
2001,Té al limón Pepsi 1,Pepsi,22.0,10.14,7.96,no,,True,2022-09-18
2002,Yogur natural,Danone,4.0,1.20,0.5,sí,14.0,False,2021-03-02
2003,Producto sin categoría,Marca,,2.00,1.0,FALSE,,True,2020-01-01
"""
CATEGORIAS = """categoria_id,nombre,padre_id,nivel
4,Frescos,,1
22,Refrescos,2.0,2
"""


def _raw(csv: str) -> pd.DataFrame:
    return pd.read_csv(StringIO(csv), dtype=str)


def test_normalizar_booleanos_todas_las_variantes() -> None:
    serie = pd.Series(
        ["no", "false", "FALSE", "0", "False", "sí", "true", "1", "TRUE", None]
    )
    assert normalizar_booleanos(serie).tolist() == [
        False,
        False,
        False,
        False,
        False,
        True,
        True,
        True,
        True,
        pd.NA,
    ]


def test_normalizar_booleanos_valor_desconocido_falla() -> None:
    with pytest.raises(ValueError, match="quizás"):
        normalizar_booleanos(pd.Series(["true", "quizás"], name="es_perecedero"))


def test_limpiar_productos_tipos() -> None:
    df = limpiar_productos(_raw(PRODUCTOS))
    assert str(df["producto_id"].dtype) == "Int64"
    assert df["categoria_id"].tolist()[:2] == [22, 4]  # "22.0" → 22
    assert df["categoria_id"].isna().tolist() == [False, False, True]
    assert df["es_perecedero"].tolist() == [False, True, False]
    assert df["dias_caducidad"].isna().tolist() == [True, False, True]
    assert df["nombre"].iloc[0] == "Té al limón Pepsi 1"


def test_limpiar_categorias_padre_nulo_y_float() -> None:
    df = limpiar_categorias(_raw(CATEGORIAS))
    assert df["padre_id"].isna().tolist() == [True, False]
    assert df["padre_id"].iloc[1] == 2


def test_validar_catalogo_caso_feliz() -> None:
    resultados = validar_catalogo(
        limpiar_productos(_raw(PRODUCTOS)), limpiar_categorias(_raw(CATEGORIAS))
    )
    assert all(r.ok for r in resultados)


def test_validar_catalogo_id_repetido_y_categoria_huerfana() -> None:
    productos = limpiar_productos(_raw(PRODUCTOS))
    productos.loc[1, "producto_id"] = 2001  # repetido
    productos.loc[0, "categoria_id"] = 999  # no existe
    fallos = [
        r.nombre
        for r in validar_catalogo(productos, limpiar_categorias(_raw(CATEGORIAS)))
        if not r.ok
    ]
    assert fallos == ["productos_id_unico", "productos_categoria_existe"]


def test_run_catalogo_escribe_las_dos_tablas(tmp_path: Path) -> None:
    (tmp_path / "productos.csv").write_text(PRODUCTOS, encoding="utf-8")
    (tmp_path / "categorias.csv").write_text(CATEGORIAS, encoding="utf-8")

    resultado = run_catalogo(tmp_path, tmp_path / "silver")

    assert (resultado.productos, resultado.categorias) == (3, 2)
    leidos = pd.read_parquet(tmp_path / "silver" / "productos")
    assert str(leidos["categoria_id"].dtype) == "Int64"


def test_run_catalogo_invalido_no_escribe_nada(tmp_path: Path) -> None:
    (tmp_path / "productos.csv").write_text(
        PRODUCTOS.replace(",22.0,", ",999.0,"), encoding="utf-8"
    )
    (tmp_path / "categorias.csv").write_text(CATEGORIAS, encoding="utf-8")

    with pytest.raises(CatalogoValidationError, match="categoría inexistente"):
        run_catalogo(tmp_path, tmp_path / "silver")
    assert not (tmp_path / "silver").exists()
