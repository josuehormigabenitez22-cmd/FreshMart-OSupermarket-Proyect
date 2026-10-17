import logging

import pandas as pd
import pytest

from freshmart.campaigns.clean import (
    eliminar_duplicados,
    limpiar_campana,
    marcar_anonimos,
    normalizar_enteros,
    parsear_fechas,
    parsear_precio,
    renombrar_columnas,
)
from freshmart.campaigns.config import (
    COLUMNAS_CANONICAS,
    CONFIGS,
    Campaign,
    get_config,
)

# --- config ------------------------------------------------------------------


def test_config_anonimo_valor_por_campana() -> None:
    assert get_config(Campaign.VERANO).anonimo_valor is None
    assert get_config(Campaign.PRIMAVERA).anonimo_valor == -1


def test_config_todos_los_mappings_cubren_el_esquema_canonico() -> None:
    for campaign in Campaign:
        destino = set(CONFIGS[campaign].columnas.values())
        assert destino == set(COLUMNAS_CANONICAS)


# --- renombrar_columnas ------------------------------------------------------


def test_renombrar_columnas_caso_feliz() -> None:
    df = pd.DataFrame({"id_cliente": ["1"], "importe": ["2.5"], "sobra": ["x"]})
    resultado = renombrar_columnas(
        df, {"id_cliente": "cliente_id", "importe": "precio"}
    )
    assert list(resultado.columns) == ["cliente_id", "precio"]  # descarta 'sobra'


def test_renombrar_columnas_falla_si_falta_una() -> None:
    df = pd.DataFrame({"id_cliente": ["1"]})
    with pytest.raises(KeyError, match="importe"):
        renombrar_columnas(df, {"id_cliente": "cliente_id", "importe": "precio"})


def test_renombrar_columnas_no_muta_la_entrada() -> None:
    df = pd.DataFrame({"a": ["1"]})
    renombrar_columnas(df, {"a": "b"})
    assert list(df.columns) == ["a"]


# --- eliminar_duplicados -----------------------------------------------------


def test_eliminar_duplicados_caso_feliz(caplog: pytest.LogCaptureFixture) -> None:
    df = pd.DataFrame({"id": ["1", "1", "2"], "v": ["a", "a", "b"]})
    with caplog.at_level(logging.WARNING):
        resultado = eliminar_duplicados(df)
    assert resultado["id"].tolist() == ["1", "2"]
    assert "1" in caplog.text  # registra cuántos eliminó


def test_eliminar_duplicados_conserva_filas_que_difieren_en_una_columna() -> None:
    df = pd.DataFrame({"id": ["1", "1"], "v": ["a", "b"]})
    assert len(eliminar_duplicados(df)) == 2
    assert len(eliminar_duplicados(df.iloc[0:0])) == 0  # vacío


# --- parsear_fechas ----------------------------------------------------------


def test_parsear_fechas_las_tres_mascaras() -> None:
    serie = pd.Series(["2024-08-05", "14/07/2024", "Jun 30, 2024"])
    assert parsear_fechas(serie).tolist() == [
        pd.Timestamp("2024-08-05"),
        pd.Timestamp("2024-07-14"),
        pd.Timestamp("2024-06-30"),
    ]


def test_parsear_fechas_ambigua_es_dia_primero_y_mes_texto_de_un_digito() -> None:
    # 05/08/2024 es 5 de agosto (no 8 de mayo); 'Aug 5' lleva el día sin cero.
    serie = pd.Series(["05/08/2024", "Aug 5, 2024"])
    assert parsear_fechas(serie).tolist() == [pd.Timestamp("2024-08-05")] * 2


def test_parsear_fechas_mantiene_nulos_y_conserva_el_indice() -> None:
    serie = pd.Series(["2024-08-05", None], index=[10, 20])
    resultado = parsear_fechas(serie)
    assert resultado.index.tolist() == [10, 20]
    assert pd.isna(resultado[20])


def test_parsear_fechas_formato_desconocido_lanza_error() -> None:
    with pytest.raises(ValueError, match="ninguna máscara"):
        parsear_fechas(pd.Series(["2024/08/05"]))


def test_parsear_fechas_fecha_imposible_lanza_error() -> None:
    with pytest.raises(ValueError):
        parsear_fechas(pd.Series(["31/02/2024"]))


# --- parsear_precio ----------------------------------------------------------


def test_parsear_precio_coma_y_euro() -> None:
    serie = pd.Series(["9,89€", "0,8€", "1.41", "12"])
    assert parsear_precio(serie).tolist() == [9.89, 0.8, 1.41, 12.0]


def test_parsear_precio_nulo_pasa_y_miles_se_rechazan() -> None:
    assert pd.isna(parsear_precio(pd.Series([None]))[0])
    with pytest.raises(ValueError, match="inválidos"):
        parsear_precio(pd.Series(["1.234,56€"]))
    with pytest.raises(ValueError, match="inválidos"):
        parsear_precio(pd.Series(["abc"]))


# --- normalizar_enteros ------------------------------------------------------


def test_normalizar_enteros_acepta_ids_con_decimal_cero() -> None:
    resultado = normalizar_enteros(pd.Series(["105049.0", "7"]))
    assert str(resultado.dtype) == "Int64"
    assert resultado.tolist() == [105049, 7]


def test_normalizar_enteros_nulos_y_no_enteros() -> None:
    resultado = normalizar_enteros(pd.Series(["5", None]))
    assert resultado[0] == 5
    assert pd.isna(resultado[1])
    with pytest.raises(ValueError, match="no enteros"):
        normalizar_enteros(pd.Series(["1.5"]))


# --- marcar_anonimos ---------------------------------------------------------


def test_marcar_anonimos_centinela_pasa_a_nulo() -> None:
    ids = pd.Series([-1, 100, -1], dtype="Int64")
    resultado = marcar_anonimos(ids, -1)
    assert resultado.isna().tolist() == [True, False, True]
    assert resultado[1] == 100


def test_marcar_anonimos_none_no_toca_nada_y_respeta_los_nulos() -> None:
    ids = pd.Series([-1, None, 5], dtype="Int64")
    assert marcar_anonimos(ids, None).isna().tolist() == [False, True, False]
    # Con centinela, un nulo previo no rompe la comparación.
    assert marcar_anonimos(ids, -1).isna().tolist() == [True, True, False]


# --- limpiar_campana (integración de las piezas) -----------------------------


def test_limpiar_campana_verano() -> None:
    raw = pd.DataFrame(
        {
            "venta_id": ["1", "1", "2"],
            "cliente_id": ["105049.0", "105049.0", None],
            "producto_id": ["2229", "2229", "2312"],
            "fecha_compra": ["14/07/2024", "14/07/2024", "Jun 30, 2024"],
            "cantidad": ["1", "1", "2"],
            "precio": ["9,89€", "9,89€", "0,8€"],
            "descuento_pct": ["20.0", "20.0", "0.0"],
            "tienda_id": ["2", "2", "3"],
            "campana": ["verano_2024"] * 3,
        }
    )
    df = limpiar_campana(raw, Campaign.VERANO)
    assert len(df) == 2  # duplicado fuera
    assert df["cliente_anonimo"].tolist() == [False, True]
    assert df["precio"].tolist() == [9.89, 0.8]
    assert str(df["cliente_id"].dtype) == "Int64"


def test_limpiar_campana_primavera_renombra_y_marca_anonimos() -> None:
    raw = pd.DataFrame(
        {
            "id_transaccion": ["7001001", "7001002"],
            "id_cliente": ["109292", "-1"],
            "id_producto": ["2047", "2231"],
            "fecha_venta": ["11/04/2024", "24/05/2024"],
            "unidades": ["1", "1"],
            "importe": ["1.41", "12.49"],
            "descuento": ["0.0", "0.0"],
            "almacen": ["2", "5"],
            "promocion": ["primavera_2024"] * 2,
        }
    )
    df = limpiar_campana(raw, Campaign.PRIMAVERA)
    assert list(df.columns[: len(COLUMNAS_CANONICAS)]) == list(COLUMNAS_CANONICAS)
    assert df["cliente_anonimo"].tolist() == [False, True]
    assert df["cliente_id"].isna().tolist() == [False, True]
