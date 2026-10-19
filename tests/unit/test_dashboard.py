import re
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from freshmart.campaigns.config import Campaign, get_config
from freshmart.campaigns.gold import clientes_nuevos_por_campana
from freshmart.dashboard.cards import ejecutar_cards, leer_cards
from freshmart.lake.parquet import escribir_parquet_atomico

PEDIDOS = """pedido_id,cliente_id,fecha_pedido,estado
1,1.0,2023-12-01 10:00:00,entregado
2,1.0,2024-07-01 10:00:00,entregado
3,2.0,05/07/2024 18:00,entregado
4,3.0,2024-04-01 09:00:00,cancelado
5,,2024-07-01 10:00:00,entregado
"""


def _gold(tmp_path: Path) -> Path:
    gold = tmp_path / "gold"
    performance = pd.DataFrame(
        {
            "campana": ["primavera", "verano", "verano"],
            "fecha": pd.to_datetime(["2024-04-10", "2024-07-01", "2024-07-02"]),
            "revenue_bruto": [10.0, 40.0, 60.0],
            "revenue_neto": [9.0, 36.0, 54.0],
            "num_transacciones": [1, 2, 4],
            "revenue_neto_acumulado": [9.0, 36.0, 90.0],
        }
    )
    top = pd.DataFrame(
        {
            "campana": ["verano"] * 12,
            "ranking": list(range(1, 13)),
            "producto_nombre": [f"P{i}" for i in range(1, 13)],
            "categoria": ["Helados"] * 12,
            "revenue_neto": [float(100 - i) for i in range(12)],
            "unidades_vendidas": [1] * 12,
        }
    )
    escribir_parquet_atomico(performance, gold / "campaign_performance")
    escribir_parquet_atomico(top, gold / "campaign_top_products")
    return gold


@pytest.fixture
def cards(tmp_path: Path) -> dict[str, pd.DataFrame]:
    (tmp_path / "pedidos.csv").write_text(PEDIDOS, encoding="utf-8")
    return ejecutar_cards(_gold(tmp_path), tmp_path)


def test_leer_cards_encuentra_las_cuatro() -> None:
    assert list(leer_cards()) == [
        "card_1_revenue",
        "card_2_clientes_nuevos",
        "card_3_top_10_productos",
        "card_4_evolucion_diaria",
    ]


def test_leer_cards_sin_marcas_falla(tmp_path: Path) -> None:
    sql = tmp_path / "x.sql"
    sql.write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(ValueError, match="ninguna card"):
        leer_cards(sql)


def test_card_1_ticket_es_suma_entre_suma(cards: dict[str, pd.DataFrame]) -> None:
    verano = cards["card_1_revenue"].set_index("campana").loc["verano"]
    assert verano["revenue_neto_total"] == pytest.approx(90)
    # (36 + 54) / (2 + 4) = 15; la media de los tickets diarios daría 15,75.
    assert verano["ticket_medio"] == pytest.approx(15)


def test_card_2_igual_que_la_version_pandas(
    cards: dict[str, pd.DataFrame], tmp_path: Path
) -> None:
    sql = cards["card_2_clientes_nuevos"].set_index("campana")["clientes_nuevos"]
    pandas = clientes_nuevos_por_campana(
        pd.read_csv(tmp_path / "pedidos.csv", dtype=str),
        pd.DataFrame({"cliente_id": [], "fecha_registro": []}),
    ).set_index("campana")["primera_compra"]
    assert sql.to_dict() == pandas.to_dict() == {"verano": 1, "primavera": 1}


def test_card_2_periodos_coinciden_con_campaign_config() -> None:
    # Metabase no lee Python: los periodos están repetidos en el SQL y no pueden divergir.
    sql = leer_cards()["card_2_clientes_nuevos"]
    en_sql = {
        nombre: (date.fromisoformat(inicio), date.fromisoformat(fin))
        for nombre, inicio, fin in re.findall(
            r"\('(\w+)',\s*DATE '([\d-]+)',\s*DATE '([\d-]+)'\)", sql
        )
    }
    en_config = {
        get_config(c).particion: (get_config(c).fecha_min, get_config(c).fecha_max)
        for c in Campaign
    }
    assert en_sql == en_config


def test_card_3_solo_top_10(cards: dict[str, pd.DataFrame]) -> None:
    assert cards["card_3_top_10_productos"]["ranking"].tolist() == list(range(1, 11))


def test_card_4_dia_de_campana_empieza_en_1(cards: dict[str, pd.DataFrame]) -> None:
    evolucion = cards["card_4_evolucion_diaria"]
    assert evolucion.groupby("campana")["dia_de_campana"].apply(list).to_dict() == {
        "primavera": [1],
        "verano": [1, 2],
    }
