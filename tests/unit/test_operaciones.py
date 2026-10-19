"""Paso 9: cuarentena, inventario, líneas de pedido y tareas de los DAGs."""

from datetime import date
from io import StringIO
from pathlib import Path

import pandas as pd
import pytest

from freshmart.inventory.gold import construir_inventario_tienda_dia
from freshmart.inventory.silver import (
    InventarioValidationError,
    preparar_inventario,
    run_inventario,
)
from freshmart.lake.parquet import escribir_parquet_atomico
from freshmart.orchestration import tasks
from freshmart.orders.lineas import run_lineas
from freshmart.quality.cuarentena import COL_MOTIVO, separar_cuarentena

# --- Cuarentena -----------------------------------------------------------------


def test_separar_cuarentena_aparta_con_motivos() -> None:
    df = pd.DataFrame({"x": [1, -1, 5, -7], "y": [0, 0, 9, 9]})
    resultado = separar_cuarentena(df, {"negativo": df["x"] < 0, "grande": df["y"] > 5})

    assert resultado.validas["x"].tolist() == [1]
    assert resultado.apartadas[COL_MOTIVO].tolist() == [
        "negativo",
        "grande",
        "negativo;grande",
    ]
    assert resultado.conteo == {"negativo": 2, "grande": 2}
    assert [r.ok for r in resultado.resultados()] == [False, False]


def test_separar_cuarentena_sin_filas_malas_y_nulos_cumplen() -> None:
    df = pd.DataFrame({"x": pd.array([1, None], dtype="Int64")})
    resultado = separar_cuarentena(df, {"negativo": df["x"] < 0})
    assert len(resultado.validas) == 2
    assert resultado.apartadas.empty
    assert COL_MOTIVO in resultado.apartadas.columns


# --- Inventario -------------------------------------------------------------------

CABECERA_INV = (
    "producto_id,tienda_id,fecha,stock_actual,stock_minimo,stock_seguridad,"
    "unidades_vendidas,unidades_recibidas\n"
)
INVENTARIO = (
    CABECERA_INV
    + "1,1,2024-09-15,50,20,8,5,0\n"
    + "1,1,2024-09-15,50,20,8,5,0\n"  # mismo batch dos veces
    + "2,1,2024-09-15,0,20,8,3,0\n"  # sin stock
    + "2,1,2024-09-16,10,20,8,3,13\n"  # bajo mínimo, no bajo seguridad
    + "3,1,2024-09-16,5,20,8,1,0\n"  # bajo seguridad
    + "3,1,2024-09-16,-4,20,8,1,0\n"  # misma clave, versión negativa → cuarentena
)


def _productos(ids: list[int]) -> pd.DataFrame:
    return pd.DataFrame({"producto_id": pd.array(ids, dtype="Int64")})


def _raw(csv: str) -> pd.DataFrame:
    return pd.read_csv(StringIO(csv), dtype=str)


def test_inventario_dedup_cuarentena_y_alertas() -> None:
    df, cuarentena, informe = preparar_inventario(
        _raw(INVENTARIO), _productos([1, 2, 3])
    )

    assert informe.ok  # la versión negativa sale y la clave queda única
    assert len(df) == 4
    assert cuarentena.apartadas[COL_MOTIVO].tolist() == ["stock_negativo"]
    alertas = df.set_index(["producto_id", "fecha"])[
        ["sin_stock", "bajo_minimo", "bajo_seguridad"]
    ]
    assert alertas.loc[(2, pd.Timestamp("2024-09-15"))].tolist() == [True, True, True]
    assert alertas.loc[(2, pd.Timestamp("2024-09-16"))].tolist() == [False, True, False]
    assert alertas.loc[(3, pd.Timestamp("2024-09-16"))].tolist() == [False, True, True]


def test_inventario_clave_repetida_o_producto_desconocido_bloquea() -> None:
    conflicto = INVENTARIO.replace(
        ",-4,20,8,1,0", ",6,20,8,1,0"
    )  # dos versiones válidas
    _, _, informe = preparar_inventario(_raw(conflicto), _productos([1, 2, 3]))
    assert [r.nombre for r in informe.errores] == ["clave_unica"]

    _, _, informe = preparar_inventario(_raw(INVENTARIO), _productos([1, 2]))
    assert [r.nombre for r in informe.errores] == ["producto_en_catalogo"]


def test_run_inventario_particiona_por_fecha_y_no_escribe_si_falla(
    tmp_path: Path,
) -> None:
    silver = tmp_path / "silver"
    escribir_parquet_atomico(_productos([1, 2, 3]), silver / "productos")
    (tmp_path / "inventario_diario.csv").write_text(INVENTARIO, encoding="utf-8")

    resultado = run_inventario(tmp_path, silver)

    assert (resultado.filas, resultado.cuarentena) == (4, 1)
    particiones = sorted(p.name for p in (silver / "inventario_diario").iterdir())
    assert particiones == ["fecha=2024-09-15", "fecha=2024-09-16"]
    assert len(pd.read_parquet(silver / "_cuarentena" / "inventario_diario")) == 1

    otro = tmp_path / "otro"
    escribir_parquet_atomico(_productos([1]), otro / "productos")
    with pytest.raises(InventarioValidationError):
        run_inventario(tmp_path, otro)
    assert not (otro / "inventario_diario").exists()
    assert not (otro / "_cuarentena").exists()


def test_run_inventario_sin_catalogo_pide_ejecutarlo(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="catálogo"):
        run_inventario(tmp_path, tmp_path / "silver")


def test_gold_inventario_tienda_dia() -> None:
    df, _, _ = preparar_inventario(_raw(INVENTARIO), _productos([1, 2, 3]))
    gold = construir_inventario_tienda_dia(df).set_index("fecha")
    dia_16 = gold.loc[pd.Timestamp("2024-09-16")]
    assert dia_16["productos"] == 2
    assert dia_16["bajo_minimo"] == 2
    assert dia_16["bajo_seguridad"] == 1
    assert dia_16["pct_bajo_seguridad"] == pytest.approx(0.5)
    assert gold.loc[pd.Timestamp("2024-09-15"), "sin_stock"] == 1


# --- Líneas de pedido ---------------------------------------------------------------

LINEAS = (
    "linea_id,pedido_id,producto_id,cantidad,precio_unitario,descuento_pct,total_linea\n"
    "1,10,1,2,6.67,5.0,12.67\n"  # 2 × 6,67 × 0,95 = 12,673 → 12,67
    "2,10,2,1,0.0,0.0,0.0\n"  # precio 0: aviso, se queda
    "3,11,9,1,5.0,0.0,5.0\n"  # producto fuera de catálogo: aviso, se queda
    "4,11,1,0,3.0,0.0,0.0\n"  # cantidad 0 → cuarentena
    "5,12,1,1,-1.03,0.0,-1.03\n"  # precio negativo → cuarentena
    "6,12,2,1,10.91,0.0,10.86\n"  # total que no cuadra → cuarentena
)


def test_run_lineas_cuarentena_y_avisos(tmp_path: Path) -> None:
    silver = tmp_path / "silver"
    escribir_parquet_atomico(_productos([1, 2]), silver / "productos")
    (tmp_path / "lineas_pedido.csv").write_text(LINEAS, encoding="utf-8")

    resultado = run_lineas(tmp_path, silver)

    assert (resultado.filas, resultado.cuarentena) == (3, 3)
    assert resultado.informe.ok
    assert {r.nombre for r in resultado.informe.avisos} == {
        "precio_cero",
        "producto_en_catalogo",
        "cuarentena_cantidad_no_positiva",
        "cuarentena_precio_negativo",
        "cuarentena_total_inconsistente",
    }
    apartadas = pd.read_parquet(silver / "_cuarentena" / "lineas_pedido")
    assert dict(zip(apartadas["linea_id"], apartadas[COL_MOTIVO], strict=True)) == {
        4: "cantidad_no_positiva",
        5: "precio_negativo",
        6: "total_inconsistente",
    }


# --- Tareas de los DAGs -----------------------------------------------------------


def test_tarea_validar_csv_falla_con_un_csv_que_no_es_de_la_campana(
    tmp_path: Path,
) -> None:
    (tmp_path / "campana_verano_ventas.csv").write_text(
        "otra,cosa\n1,2\n", encoding="utf-8"
    )
    with pytest.raises(tasks.CsvNoValidoError, match="columnas_faltantes"):
        tasks.tarea_validar_csv("verano_2024", str(tmp_path))


def test_tarea_gaps_avisa_y_devuelve_los_dias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gold = tmp_path / "gold"
    performance = pd.DataFrame(
        {
            "campana": ["verano"] * 2,
            "fecha": pd.to_datetime(["2024-07-01", "2024-07-03"]),
        }
    )
    escribir_parquet_atomico(performance, gold / "campaign_performance")
    enviados: list[tuple[list[date], str]] = []
    monkeypatch.setattr(
        tasks,
        "enviar_alerta_slack",
        lambda gaps, campana: enviados.append((gaps, campana)),
    )

    assert tasks.tarea_gaps("verano_2024", str(gold)) == ["2024-07-02"]
    assert enviados == [([date(2024, 7, 2)], "verano")]


def test_tarea_gaps_sin_datos_de_la_campana_falla(tmp_path: Path) -> None:
    gold = tmp_path / "gold"
    performance = pd.DataFrame(
        {"campana": ["verano"], "fecha": pd.to_datetime(["2024-07-01"])}
    )
    escribir_parquet_atomico(performance, gold / "campaign_performance")
    with pytest.raises(RuntimeError, match="primavera"):
        tasks.tarea_gaps("primavera_2024", str(gold))
