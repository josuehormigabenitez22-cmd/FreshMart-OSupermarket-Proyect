from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from freshmart.segmentation.segment import (
    parsear_fechas_pedido,
    resumen,
    segmentar_pandas,
    segmentar_sql,
    verificar,
)

CORTE = date(2024, 9, 16)

CLIENTES = """cliente_id,nombre,telefono,fecha_registro,codigo_postal
1,Ana,+34111,2024-07-01,28001
2,Beto,+34222,2023-01-10,8015
2,Beto,+34222,2023-01-10,08015
3,Cris,+34333,2022-05-05,46008
4,Dani,+34444,2021-03-03,41015
5,Eli,+34555,2024-02-02,48011
"""


def _pedidos() -> str:
    filas = ["pedido_id,cliente_id,fecha_pedido,estado"]
    n = 1

    def add(cliente: str, fecha: str, estado: str = "entregado") -> None:
        nonlocal n
        filas.append(f"{n},{cliente},{fecha},{estado}")
        n += 1

    # Cris: 7 válidos (premium) + 1 cancelado que no cuenta.
    for dia in range(1, 8):
        add("3.0", f"2024-08-{dia:02d} 10:00:00")
    add("3.0", "2024-08-20 10:00:00", "cancelado")

    # Dani: uno ISO y uno dd/mm AMBIGUO (05/08 = 5 de agosto, no 8 de mayo).
    add("4.0", "2024-07-10 09:30:00")
    add("4.0", "05/08/2024 18:45")

    # Eli: borde inferior incluido, borde superior (fecha de corte) excluido.
    add("5.0", "2024-06-16 00:00:00")
    add("5.0", "2024-09-16 00:00:00")
    add("5.0", "2024-06-15 23:59:59")

    # Pedido sin cliente: debe ignorarse sin romper nada.
    add("", "2024-08-01 10:00:00")
    return "\n".join(filas) + "\n"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    (tmp_path / "clientes.csv").write_text(CLIENTES, encoding="utf-8")
    (tmp_path / "pedidos.csv").write_text(_pedidos(), encoding="utf-8")
    return tmp_path


def test_parsear_fechas_en_dos_pasadas() -> None:
    serie = pd.Series(["2024-07-10 09:30:00", "05/08/2024 18:45"])
    fechas = parsear_fechas_pedido(serie)
    assert fechas.tolist() == [
        pd.Timestamp("2024-07-10 09:30:00"),
        pd.Timestamp("2024-08-05 18:45:00"),
    ]


def test_parsear_fechas_falla_si_no_reconoce_el_formato() -> None:
    with pytest.raises(ValueError, match="sin parsear"):
        parsear_fechas_pedido(pd.Series(["no-es-una-fecha"]))


def test_segmentacion_pandas(data_dir: Path) -> None:
    df = segmentar_pandas(data_dir, CORTE).set_index("cliente_id")

    # Deduplicado: Beto aparece una sola vez. LEFT JOIN: Ana (sin pedidos) está.
    assert len(df) == 5
    assert df.loc[1, "pedidos_3m"] == 0
    assert df.loc[3, "pedidos_3m"] == 7  # el cancelado no cuenta
    assert df.loc[4, "pedidos_3m"] == 2  # la fecha dd/mm se lee bien
    assert df.loc[5, "pedidos_3m"] == 1  # borde inferior sí, superior no
    assert df["segmento_calculado"].to_dict() == {
        1: "nuevo",
        2: "nuevo",
        3: "premium",
        4: "regular",
        5: "nuevo",
    }


def test_pandas_y_sql_dan_lo_mismo(data_dir: Path) -> None:
    resultado = verificar(data_dir, CORTE)  # lanza AssertionError si difieren
    assert len(resultado) == 5


def test_sql_aplica_las_mismas_reglas(data_dir: Path) -> None:
    df = segmentar_sql(data_dir, CORTE).set_index("cliente_id")
    assert df.loc[3, "pedidos_3m"] == 7
    assert df.loc[4, "pedidos_3m"] == 2
    assert df.loc[5, "pedidos_3m"] == 1


def test_resumen(data_dir: Path) -> None:
    assert resumen(segmentar_pandas(data_dir, CORTE)) == {
        "clientes": 5,
        "premium": 1,
        "regular": 1,
        "nuevo": 3,
        "sin_pedidos": 2,  # Ana y Beto
        "sin_pedidos_desde_junio": 1,  # solo Ana se registró desde junio
    }
