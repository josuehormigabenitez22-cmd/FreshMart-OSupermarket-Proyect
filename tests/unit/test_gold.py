from pathlib import Path

import pandas as pd
import pytest

from freshmart.campaigns.config import Campaign
from freshmart.campaigns.gold import (
    clientes_nuevos_por_campana,
    construir_campaign_performance,
    construir_top_products,
    leer_silver,
    run_gold,
    verificar_gold,
)
from freshmart.campaigns.pipeline import escribir_silver
from freshmart.lake.parquet import escribir_parquet_atomico


def _ventas() -> pd.DataFrame:
    """Dos días de verano y uno de primavera; el cliente 10 compra dos veces el día 1."""
    return pd.DataFrame(
        {
            "venta_id": pd.array([1, 2, 3, 4, 5], dtype="Int64"),
            "cliente_id": pd.array([10, 10, None, 11, 12], dtype="Int64"),
            "producto_id": pd.array([100, 200, 100, 100, 300], dtype="Int64"),
            "fecha_compra": pd.to_datetime(
                ["2024-07-01", "2024-07-01", "2024-07-01", "2024-07-02", "2024-04-10"]
            ),
            "cantidad": pd.array([2, 1, 1, 3, 1], dtype="Int64"),
            "precio": [10.0, 5.0, 10.0, 10.0, 8.0],
            "descuento_pct": [0.0, 20.0, 0.0, 10.0, 0.0],
            "tienda_id": pd.array([1, 1, 2, 1, 3], dtype="Int64"),
            "cliente_anonimo": [False, False, True, False, False],
            "campana": ["verano", "verano", "verano", "verano", "primavera"],
        }
    )


def _productos() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "producto_id": pd.array([100, 200], dtype="Int64"),
            "nombre": ["Helado", "Agua"],
            "marca": ["Frigo", "Font Vella"],
            "categoria_id": pd.array([7, 8], dtype="Int64"),
        }
    )


def _categorias() -> pd.DataFrame:
    return pd.DataFrame(
        {"categoria_id": pd.array([7, 8], dtype="Int64"), "nombre": ["Helados", "Agua"]}
    )


# --- campaign_performance -----------------------------------------------------


def test_performance_una_fila_por_campana_y_dia() -> None:
    gold = construir_campaign_performance(_ventas())
    assert list(
        zip(gold["campana"], gold["fecha"].dt.strftime("%m-%d"), strict=True)
    ) == [
        ("primavera", "04-10"),
        ("verano", "07-01"),
        ("verano", "07-02"),
    ]


def test_performance_metricas_del_dia() -> None:
    dia = construir_campaign_performance(_ventas()).iloc[1]  # verano 07-01
    assert dia["revenue_bruto"] == pytest.approx(20 + 5 + 10)
    assert dia["revenue_neto"] == pytest.approx(20 + 4 + 10)  # 20 % de descuento en 5 €
    assert dia["num_transacciones"] == 3
    assert dia["unidades_vendidas"] == 4
    assert dia["clientes_unicos"] == 1  # el 10 dos veces; el anónimo no cuenta
    assert dia["ventas_anonimas"] == 1
    assert dia["productos_distintos"] == 2
    assert dia["ticket_medio"] == pytest.approx(34 / 3)


def test_performance_acumulados_por_campana() -> None:
    gold = construir_campaign_performance(_ventas())
    verano = gold[gold["campana"] == "verano"]
    assert verano["revenue_neto_acumulado"].tolist() == pytest.approx([34, 34 + 27])
    assert verano["transacciones_acumuladas"].tolist() == [3, 4]
    # Los acumulados se reinician en cada campaña.
    assert gold.iloc[0]["transacciones_acumuladas"] == 1


# --- campaign_top_products ------------------------------------------------------


def test_top_products_ranking_y_enriquecimiento() -> None:
    top = construir_top_products(_ventas(), _productos(), _categorias())
    verano = top[top["campana"] == "verano"]
    assert verano["producto_id"].tolist() == [100, 200]
    assert verano["ranking"].tolist() == [1, 2]
    primero = verano.iloc[0]
    assert (primero["producto_nombre"], primero["marca"], primero["categoria"]) == (
        "Helado",
        "Frigo",
        "Helados",
    )
    assert primero["revenue_neto"] == pytest.approx(20 + 10 + 27)
    assert primero["compradores_unicos"] == 2  # 10 y 11; el anónimo no cuenta


def test_top_products_producto_fuera_del_maestro_se_conserva_sin_nombre() -> None:
    top = construir_top_products(_ventas(), _productos(), _categorias())
    primavera = top[top["campana"] == "primavera"].iloc[0]
    assert primavera["producto_id"] == 300
    assert pd.isna(primavera["producto_nombre"])


def test_top_products_respeta_top_n_y_desempata_por_id() -> None:
    ventas = _ventas().assign(precio=1.0, cantidad=pd.array([1] * 5, dtype="Int64"))
    ventas["descuento_pct"] = 0.0
    top = construir_top_products(ventas, _productos(), _categorias(), top_n=1)
    # En verano el 100 tiene 3 ventas; en primavera solo hay uno.
    assert top["ranking"].tolist() == [1, 1]
    empate = construir_top_products(
        ventas[ventas["venta_id"].isin([2, 4])], _productos(), _categorias()
    )
    assert empate["producto_id"].tolist() == [100, 200]  # mismo revenue: menor id


# --- clientes nuevos ------------------------------------------------------------


def test_clientes_nuevos_primera_compra_en_todo_el_historial() -> None:
    pedidos = pd.DataFrame(
        {
            "cliente_id": ["1.0", "1.0", "2.0", "3.0", None],
            "fecha_pedido": [
                "2023-12-01 10:00:00",  # el 1 ya compraba antes: no es nuevo
                "2024-07-01 10:00:00",
                "05/07/2024 18:00",  # dd/mm: 5 de julio → nuevo de verano
                "2024-04-01 09:00:00",  # nuevo de primavera
                "2024-07-01 10:00:00",  # sin cliente: se ignora
            ],
        }
    )
    clientes = pd.DataFrame(
        {
            "cliente_id": ["1", "2", "2", "3"],
            "fecha_registro": ["2023-01-01", "2024-06-20", "2024-06-20", "2024-03-02"],
        }
    )
    resultado = clientes_nuevos_por_campana(pedidos, clientes).set_index("campana")
    assert resultado.loc["verano"].tolist() == [1, 1]  # el 2, registrado una sola vez
    assert resultado.loc["primavera"].tolist() == [1, 1]


# --- E/S y SQL ------------------------------------------------------------------


def _silver(tmp_path: Path) -> Path:
    silver = tmp_path / "silver"
    ventas = _ventas()
    for campaign, particion in (
        (Campaign.VERANO, "verano"),
        (Campaign.PRIMAVERA, "primavera"),
    ):
        escribir_silver(ventas[ventas["campana"] == particion], silver, campaign)
    escribir_parquet_atomico(_productos(), silver / "productos")
    escribir_parquet_atomico(_categorias(), silver / "categorias")
    return silver


def test_pandas_y_sql_dan_el_mismo_gold(tmp_path: Path) -> None:
    verificar_gold(_silver(tmp_path))  # lanza AssertionError si difieren


def test_run_gold_escribe_las_dos_tablas(tmp_path: Path) -> None:
    resultado = run_gold(_silver(tmp_path), tmp_path / "gold")
    assert (resultado.performance, resultado.top_products) == (3, 3)
    assert len(pd.read_parquet(tmp_path / "gold" / "campaign_performance")) == 3


def test_leer_silver_sin_catalogo_da_un_error_claro(tmp_path: Path) -> None:
    silver = tmp_path / "silver"
    escribir_silver(_ventas()[:1], silver, Campaign.VERANO)
    with pytest.raises(FileNotFoundError, match="--catalog"):
        leer_silver(silver)
