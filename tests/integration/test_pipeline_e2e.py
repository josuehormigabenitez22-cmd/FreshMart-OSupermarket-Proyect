"""Pipeline de extremo a extremo (CSV -> limpieza -> validación -> Parquet) con CSV pequeños."""

from pathlib import Path

import pandas as pd
import pytest

from freshmart.campaigns.cli import main
from freshmart.campaigns.config import Campaign
from freshmart.campaigns.pipeline import (
    PARQUET_FILE,
    SILVER_TABLE,
    PipelineValidationError,
    partition_dir,
    run_pipeline,
)

CABECERA_VERANO = "venta_id,cliente_id,producto_id,fecha_compra,cantidad,precio,descuento_pct,tienda_id,campana\n"

# Reúne los problemas reales: duplicado exacto, 3 formatos de fecha, precio con
# coma y €, cliente anónimo (vacío) y una venta con cantidad 0.
VERANO_OK = (
    CABECERA_VERANO
    + '1,105049.0,2229,14/07/2024,1,"9,89€",20.0,2,verano_2024\n'
    + '1,105049.0,2229,14/07/2024,1,"9,89€",20.0,2,verano_2024\n'
    + '2,,2312,"Jun 30, 2024",2,"0,8€",0.0,3,verano_2024\n'
    + '3,101591.0,2167,2024-08-05,0,"4,27€",0.0,2,verano_2024\n'
    + '4,110687.0,2039,2024-08-04,3,"23,25€",10.0,3,verano_2024\n'
)

# Misma estructura pero la venta 2 no trae fecha: la validación debe fallar.
VERANO_FECHA_VACIA = VERANO_OK.replace('"Jun 30, 2024"', "")

PRIMAVERA_OK = (
    "id_transaccion,id_cliente,id_producto,fecha_venta,unidades,importe,descuento,almacen,promocion\n"
    "7001001,109292,2047,11/04/2024,1,1.41,0.0,2,primavera_2024\n"
    "7001002,-1,2231,24/05/2024,1,12.49,0.0,5,primavera_2024\n"
)


PRODUCTOS = (
    "producto_id,nombre,marca,categoria_id,precio_base,peso_kg,es_perecedero,"
    "dias_caducidad,activo,fecha_alta\n"
    "2229,Helado,Frigo,7.0,9.89,1.0,sí,30.0,True,2022-01-01\n"
    "2039,Agua,Font Vella,8.0,0.50,1.5,no,,True,2021-01-01\n"
)
CATEGORIAS = "categoria_id,nombre,padre_id,nivel\n7,Helados,,1\n8,Agua,,1\n"


def _escribir(input_dir: Path, nombre: str, contenido: str) -> None:
    input_dir.mkdir(exist_ok=True)
    (input_dir / nombre).write_text(contenido, encoding="utf-8")


def _entrada_completa(entrada: Path) -> None:
    _escribir(entrada, "campana_verano_ventas.csv", VERANO_OK)
    _escribir(entrada, "campana_primavera_ventas.csv", PRIMAVERA_OK)
    _escribir(entrada, "productos.csv", PRODUCTOS)
    _escribir(entrada, "categorias.csv", CATEGORIAS)


def test_e2e_verano_limpia_valida_y_escribe_parquet_particionado(
    tmp_path: Path,
) -> None:
    entrada, silver = tmp_path / "in", tmp_path / "silver"
    _escribir(entrada, "campana_verano_ventas.csv", VERANO_OK)

    resultado = run_pipeline(Campaign.VERANO, entrada, silver)

    assert resultado.informe.ok
    assert (resultado.informe.aprobadas, resultado.informe.total) == (6, 6)
    assert resultado.filas == 3  # 5 filas - 1 duplicado - 1 cantidad 0
    assert resultado.destino == silver / SILVER_TABLE / "campana=verano"
    assert (resultado.destino / PARQUET_FILE).is_file()

    # Leyendo el directorio de la tabla, la partición reaparece como columna.
    df = pd.read_parquet(silver / SILVER_TABLE).sort_values("venta_id")
    assert df["venta_id"].tolist() == [1, 2, 4]
    assert set(df["campana"].astype(str)) == {"verano"}
    assert df["precio"].tolist() == [9.89, 0.8, 23.25]
    assert df["cliente_anonimo"].tolist() == [False, True, False]
    assert df["fecha_compra"].dt.strftime("%Y-%m-%d").tolist() == [
        "2024-07-14",
        "2024-06-30",
        "2024-08-04",
    ]


def test_e2e_primavera_renombra_columnas_y_marca_anonimos(tmp_path: Path) -> None:
    entrada, silver = tmp_path / "in", tmp_path / "silver"
    _escribir(entrada, "campana_primavera_ventas.csv", PRIMAVERA_OK)

    resultado = run_pipeline(Campaign.PRIMAVERA, entrada, silver)

    assert resultado.destino.name == "campana=primavera"
    df = pd.read_parquet(silver / SILVER_TABLE)
    assert df["cliente_anonimo"].tolist() == [False, True]
    assert df["cliente_id"].isna().tolist() == [False, True]  # el -1 ya es nulo


def test_e2e_dos_campanas_conviven_en_silver(tmp_path: Path) -> None:
    entrada, silver = tmp_path / "in", tmp_path / "silver"
    _escribir(entrada, "campana_verano_ventas.csv", VERANO_OK)
    _escribir(entrada, "campana_primavera_ventas.csv", PRIMAVERA_OK)

    run_pipeline(Campaign.VERANO, entrada, silver)
    run_pipeline(Campaign.PRIMAVERA, entrada, silver)

    df = pd.read_parquet(silver / SILVER_TABLE)
    assert df["campana"].astype(str).value_counts().to_dict() == {
        "verano": 3,
        "primavera": 2,
    }


def test_e2e_si_falla_una_validacion_no_se_escribe_nada_en_silver(
    tmp_path: Path,
) -> None:
    entrada, silver = tmp_path / "in", tmp_path / "silver"
    _escribir(entrada, "campana_verano_ventas.csv", VERANO_FECHA_VACIA)

    with pytest.raises(PipelineValidationError) as excinfo:
        run_pipeline(Campaign.VERANO, entrada, silver)

    assert not excinfo.value.informe.ok
    fallos = [r.nombre for r in excinfo.value.informe.resultados if not r.ok]
    assert fallos == ["fechas_validas"]
    assert not silver.exists()  # ni siquiera se crea el directorio


def test_e2e_fecha_fuera_de_la_campana_no_se_escribe(tmp_path: Path) -> None:
    entrada, silver = tmp_path / "in", tmp_path / "silver"
    _escribir(
        entrada,
        "campana_verano_ventas.csv",
        VERANO_OK.replace("2024-08-04", "2024-12-04"),
    )

    with pytest.raises(PipelineValidationError) as excinfo:
        run_pipeline(Campaign.VERANO, entrada, silver)

    fallos = [r.nombre for r in excinfo.value.informe.resultados if not r.ok]
    assert fallos == ["fechas_en_rango"]
    assert not silver.exists()


def test_e2e_un_fallo_no_estropea_una_particion_anterior(tmp_path: Path) -> None:
    entrada, silver = tmp_path / "in", tmp_path / "silver"
    _escribir(entrada, "campana_verano_ventas.csv", VERANO_OK)
    run_pipeline(Campaign.VERANO, entrada, silver)
    parquet = partition_dir(silver, Campaign.VERANO) / PARQUET_FILE
    antes = parquet.read_bytes()

    _escribir(entrada, "campana_verano_ventas.csv", VERANO_FECHA_VACIA)
    with pytest.raises(PipelineValidationError):
        run_pipeline(Campaign.VERANO, entrada, silver)

    assert parquet.read_bytes() == antes


def test_e2e_csv_sin_ventas_validas_falla_en_no_vacio(tmp_path: Path) -> None:
    entrada, silver = tmp_path / "in", tmp_path / "silver"
    solo_cero = CABECERA_VERANO + '1,10.0,2229,2024-07-14,0,"9,89€",0.0,2,verano_2024\n'
    _escribir(entrada, "campana_verano_ventas.csv", solo_cero)

    with pytest.raises(PipelineValidationError) as excinfo:
        run_pipeline(Campaign.VERANO, entrada, silver)

    assert excinfo.value.informe.resultados[0].nombre == "no_vacio"
    assert not excinfo.value.informe.resultados[0].ok
    assert not silver.exists()


def test_e2e_cli_codigo_de_salida_y_salida_por_pantalla(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    entrada, silver = tmp_path / "in", tmp_path / "silver"
    _escribir(entrada, "campana_verano_ventas.csv", VERANO_OK)
    args = [
        "--campaign",
        "verano",
        "--input",
        str(entrada),
        "--silver-dir",
        str(silver),
    ]

    assert main(args) == 0
    assert "6/6 OK" in capsys.readouterr().out

    _escribir(entrada, "campana_verano_ventas.csv", VERANO_FECHA_VACIA)
    assert main(args) == 1
    salida = capsys.readouterr().out
    assert "5/6 OK" in salida
    assert "Silver NO modificado" in salida


def test_e2e_cli_all_procesa_todas_las_campanas(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    entrada, silver = tmp_path / "in", tmp_path / "silver"
    _escribir(entrada, "campana_verano_ventas.csv", VERANO_OK)
    _escribir(entrada, "campana_primavera_ventas.csv", PRIMAVERA_OK)

    codigo = main(["--all", "--input", str(entrada), "--silver-dir", str(silver)])

    assert codigo == 0
    assert "Campañas OK: 2/2" in capsys.readouterr().out
    df = pd.read_parquet(silver / SILVER_TABLE)
    assert set(df["campana"].astype(str)) == {"verano", "primavera"}


def test_e2e_cli_all_una_campana_fallida_no_bloquea_a_la_otra(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    entrada, silver = tmp_path / "in", tmp_path / "silver"
    _escribir(entrada, "campana_verano_ventas.csv", VERANO_FECHA_VACIA)
    _escribir(entrada, "campana_primavera_ventas.csv", PRIMAVERA_OK)

    codigo = main(["--all", "--input", str(entrada), "--silver-dir", str(silver)])

    assert codigo == 1
    assert "Campañas OK: 1/2" in capsys.readouterr().out
    assert not partition_dir(silver, Campaign.VERANO).exists()
    assert (partition_dir(silver, Campaign.PRIMAVERA) / PARQUET_FILE).is_file()


def test_e2e_cli_catalogo_silver_y_gold(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    entrada, silver, gold = tmp_path / "in", tmp_path / "silver", tmp_path / "gold"
    _entrada_completa(entrada)
    rutas = ["--input", str(entrada), "--silver-dir", str(silver)]

    assert main(["--catalog", *rutas]) == 0
    assert main(["--all", *rutas, "--gold-dir", str(gold)]) == 0
    assert "Gold: campaign_performance 5 filas" in capsys.readouterr().out

    performance = pd.read_parquet(gold / "campaign_performance")
    assert performance["num_transacciones"].sum() == 5  # 3 verano + 2 primavera
    top = pd.read_parquet(gold / "campaign_top_products")
    helado = top[top["producto_id"] == 2229].iloc[0]
    assert (helado["producto_nombre"], helado["categoria"]) == ("Helado", "Helados")


def test_e2e_cli_only_gold_reconstruye_sin_leer_csv(tmp_path: Path) -> None:
    entrada, silver, gold = tmp_path / "in", tmp_path / "silver", tmp_path / "gold"
    _entrada_completa(entrada)
    rutas = ["--input", str(entrada), "--silver-dir", str(silver)]
    assert main(["--catalog", *rutas]) == 0
    assert main(["--all", *rutas]) == 0
    assert not gold.exists()  # sin --gold-dir no se construye gold

    for csv in entrada.iterdir():
        csv.unlink()  # --only-gold solo debe leer silver
    assert (
        main(["--only-gold", "--silver-dir", str(silver), "--gold-dir", str(gold)]) == 0
    )
    assert len(pd.read_parquet(gold / "campaign_performance")) == 5


def test_e2e_cli_gold_sin_catalogo_falla_con_mensaje(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    entrada, silver, gold = tmp_path / "in", tmp_path / "silver", tmp_path / "gold"
    _entrada_completa(entrada)
    rutas = ["--input", str(entrada), "--silver-dir", str(silver)]

    assert main(["--all", *rutas, "--gold-dir", str(gold)]) == 1
    assert "--catalog" in capsys.readouterr().out
    assert not gold.exists()


def test_e2e_cli_campana_fallida_no_reconstruye_gold(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    entrada, silver, gold = tmp_path / "in", tmp_path / "silver", tmp_path / "gold"
    _entrada_completa(entrada)
    _escribir(entrada, "campana_verano_ventas.csv", VERANO_FECHA_VACIA)
    rutas = ["--input", str(entrada), "--silver-dir", str(silver)]
    assert main(["--catalog", *rutas]) == 0

    assert main(["--all", *rutas, "--gold-dir", str(gold)]) == 1
    assert "Gold NO reconstruido" in capsys.readouterr().out
    assert not gold.exists()


def test_cli_exige_paths_por_argumentos(tmp_path: Path) -> None:
    # Sin --input / --silver-dir no hay valores por defecto escritos en el código.
    with pytest.raises(SystemExit) as excinfo:
        main(["--campaign", "verano"])
    assert excinfo.value.code == 2
