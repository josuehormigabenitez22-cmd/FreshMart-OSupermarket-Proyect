import pandas as pd
import pytest

from freshmart.campaigns.config import Campaign
from freshmart.campaigns.validate import (
    COLUMNAS_ESPERADAS,
    FECHAS_VALIDAS,
    NO_VACIO,
    VALORES_VALIDOS,
    VENTA_ID_UNICO,
    validar,
    validar_columnas,
    validar_fechas,
    validar_no_vacio,
    validar_valores,
    validar_venta_id_unico,
)


def _df_valido() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "venta_id": pd.array([1, 2], dtype="Int64"),
            "cliente_id": pd.array([10, None], dtype="Int64"),
            "producto_id": pd.array([5, 6], dtype="Int64"),
            "fecha_compra": pd.to_datetime(["2024-07-01", "2024-07-02"]),
            "cantidad": pd.array([1, 3], dtype="Int64"),
            "precio": [9.89, 0.8],
            "descuento_pct": [0.0, 20.0],
            "tienda_id": pd.array([1, 2], dtype="Int64"),
            "campana": ["verano_2024", "verano_2024"],
            "cliente_anonimo": [False, True],
        }
    )


# --- no_vacio ----------------------------------------------------------------


def test_no_vacio_caso_feliz() -> None:
    assert validar_no_vacio(_df_valido()).ok


def test_no_vacio_dataframe_vacio_falla() -> None:
    assert not validar_no_vacio(_df_valido().iloc[0:0]).ok


# --- columnas_esperadas ------------------------------------------------------


def test_columnas_caso_feliz() -> None:
    assert validar_columnas(_df_valido()).ok


def test_columnas_falta_una_y_se_nombra() -> None:
    resultado = validar_columnas(_df_valido().drop(columns=["precio"]))
    assert not resultado.ok
    assert "precio" in resultado.detalle


# --- venta_id_unico ----------------------------------------------------------


def test_venta_id_unico_caso_feliz() -> None:
    assert validar_venta_id_unico(_df_valido()).ok


def test_venta_id_unico_repetidos_y_nulos_fallan() -> None:
    repetido = _df_valido().assign(venta_id=pd.array([1, 1], dtype="Int64"))
    assert not validar_venta_id_unico(repetido).ok
    con_nulo = _df_valido().assign(venta_id=pd.array([1, None], dtype="Int64"))
    assert not validar_venta_id_unico(con_nulo).ok


# --- fechas_validas ----------------------------------------------------------


def test_fechas_caso_feliz() -> None:
    assert validar_fechas(_df_valido()).ok


def test_fechas_invalidas_se_coercionan_y_fallan_sin_lanzar_excepcion() -> None:
    # Con errors="coerce" una fecha imposible es NaT: la validación falla, no explota.
    df = _df_valido().assign(fecha_compra=["2024-07-01", "2024-13-45"])
    resultado = validar_fechas(df)
    assert not resultado.ok
    assert "1 fechas inválidas" in resultado.detalle


def test_fechas_nulas_cuentan_como_invalidas() -> None:
    df = _df_valido().assign(fecha_compra=pd.to_datetime(["2024-07-01", None]))
    assert not validar_fechas(df).ok


# --- valores_validos ---------------------------------------------------------


def test_valores_caso_feliz() -> None:
    assert validar_valores(_df_valido()).ok


@pytest.mark.parametrize(
    ("columna", "valores"),
    [
        ("cantidad", pd.array([1, 0], dtype="Int64")),
        ("cantidad", pd.array([1, None], dtype="Int64")),  # nulo = no cumple
        ("precio", [9.89, 0.0]),
        ("descuento_pct", [0.0, 120.0]),
    ],
)
def test_valores_limite_fallan(columna: str, valores: object) -> None:
    df = _df_valido().assign(**{columna: valores})
    assert not validar_valores(df).ok


# --- validar (orquestación) --------------------------------------------------


def test_validar_cinco_de_cinco() -> None:
    informe = validar(_df_valido(), Campaign.VERANO)
    assert informe.ok
    assert (informe.aprobadas, informe.total) == (5, 5)
    assert informe.campaign is Campaign.VERANO
    assert "5/5 OK" in informe.resumen()


def test_validar_empieza_por_no_vacio_y_no_ejecuta_el_resto_si_esta_vacio() -> None:
    informe = validar(_df_valido().iloc[0:0], Campaign.PRIMAVERA)
    assert informe.resultados[0].nombre == NO_VACIO
    assert not informe.ok
    assert informe.aprobadas == 0
    assert all("no ejecutada" in r.detalle for r in informe.resultados[1:])


def test_validar_sin_columnas_no_lanza_keyerror() -> None:
    informe = validar(pd.DataFrame({"x": [1]}), Campaign.VERANO)
    assert not informe.ok
    nombres = [r.nombre for r in informe.resultados]
    assert nombres == [
        NO_VACIO,
        COLUMNAS_ESPERADAS,
        VENTA_ID_UNICO,
        FECHAS_VALIDAS,
        VALORES_VALIDOS,
    ]
    assert informe.resultados[0].ok  # tiene filas
    assert not informe.resultados[1].ok  # faltan columnas
