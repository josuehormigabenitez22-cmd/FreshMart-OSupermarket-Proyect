"""Paso 8: resultado de validación unificado, validador de CSV, gaps y alertas a Slack."""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from freshmart.campaigns.config import Campaign
from freshmart.lake.parquet import escribir_parquet_atomico
from freshmart.quality.csv_validator import (
    detectar_formatos_fecha,
    validar_csv,
    validar_csv_campana,
)
from freshmart.quality.csv_validator import (
    main as validar_csv_main,
)
from freshmart.quality.gap_detection import (
    detectar_gaps,
    rango_con_datos,
)
from freshmart.quality.gap_detection import (
    main as gaps_main,
)
from freshmart.quality.result import InformeCalidad, ResultadoValidacion, Severidad
from freshmart.quality.slack_alerts import construir_mensaje, enviar_alerta_slack

# --- Resultado unificado ------------------------------------------------------


def test_informe_avisos_no_invalidan_errores_si() -> None:
    con_aviso = InformeCalidad(
        "x",
        (
            ResultadoValidacion("a", True, "ok"),
            ResultadoValidacion("b", False, "dup", Severidad.AVISO),
        ),
    )
    assert con_aviso.ok
    assert [r.nombre for r in con_aviso.avisos] == ["b"]
    assert "1/2 OK (1 avisos)" in con_aviso.resumen()
    assert "[AVISO] b" in con_aviso.resumen()

    con_error = InformeCalidad("x", (ResultadoValidacion("c", False, "mal"),))
    assert not con_error.ok
    assert "[FALLA] c" in con_error.resumen()


def test_severidad_por_defecto_es_error() -> None:
    assert ResultadoValidacion("a", False, "").severidad is Severidad.ERROR


# --- Validador de CSV --------------------------------------------------------------

COLUMNAS = ["id", "fecha", "cantidad"]


def _csv(**columnas: list[str | None]) -> pd.DataFrame:
    base: dict[str, list[str | None]] = {
        "id": ["1", "2", "3"],
        "fecha": ["2024-07-01", "2024-07-02", "2024-07-03"],
        "cantidad": ["1", "2", "3"],
    }
    return pd.DataFrame({**base, **columnas})


def _validar(df: pd.DataFrame) -> InformeCalidad:
    return validar_csv(
        df,
        COLUMNAS,
        tipos={"fecha": "datetime", "cantidad": "numeric"},
        columnas_criticas=["id", "fecha"],
        max_pct_nulos=0.4,
    )


def _fallos(informe: InformeCalidad) -> dict[str, Severidad]:
    return {r.nombre: r.severidad for r in informe.resultados if not r.ok}


def test_csv_valido() -> None:
    informe = _validar(_csv())
    assert informe.ok
    assert _fallos(informe) == {}


def test_csv_columna_faltante_es_error_y_extra_es_aviso() -> None:
    df = _csv().drop(columns=["cantidad"]).assign(sobra="x")
    assert _fallos(_validar(df)) == {
        "columnas_faltantes": Severidad.ERROR,
        "columnas_extra": Severidad.AVISO,
    }


def test_csv_tipos_invalidos() -> None:
    df = _csv(cantidad=["1", "dos", None], fecha=["2024-07-01", "ayer", "2024-07-03"])
    informe = _validar(df)
    assert not informe.ok
    assert _fallos(informe) == {
        "tipo_cantidad": Severidad.ERROR,
        "tipo_fecha": Severidad.ERROR,
    }
    detalle = next(r.detalle for r in informe.resultados if r.nombre == "tipo_cantidad")
    assert "1 valores no numéricos" in detalle and "dos" in detalle  # el nulo no cuenta


def test_csv_varios_formatos_de_fecha_es_aviso() -> None:
    df = _csv(fecha=["2024-07-01", "02/07/2024", "Jul 3, 2024"])
    informe = _validar(df)
    assert informe.ok
    assert _fallos(informe) == {"formatos_fecha": Severidad.AVISO}


def test_csv_nulos_criticos_umbral_y_duplicados() -> None:
    df = _csv(id=["1", None, "1"], cantidad=["1", None, "1"], fecha=["2024-07-01"] * 3)
    df.loc[2] = df.loc[0]  # fila 2 = fila 0: duplicado exacto
    assert _fallos(_validar(df)) == {
        "nulos_en_criticas": Severidad.ERROR,
        "duplicados_exactos": Severidad.AVISO,
    }
    # Con un umbral más estricto, el 33 % de nulos de id/cantidad también avisa.
    estricto = validar_csv(df, COLUMNAS, max_pct_nulos=0.1)
    assert "umbral_nulos" in _fallos(estricto)


def test_csv_vacio_falla() -> None:
    assert not _validar(_csv().iloc[0:0]).ok


def test_detectar_formatos_fecha_ignora_nulos() -> None:
    serie = pd.Series(["2024-07-01", None, "01/07/2024", "?", "Jul 1, 2024"])
    assert detectar_formatos_fecha(serie) == {
        "AAAA-MM-DD": 1,
        "DD/MM/AAAA": 1,
        "Mon D, AAAA": 1,
        "desconocido": 1,
    }


def test_csv_campana_usa_los_nombres_originales_de_la_config() -> None:
    primavera = pd.DataFrame(
        {
            "id_transaccion": ["1"],
            "id_cliente": ["-1"],
            "id_producto": ["2"],
            "fecha_venta": ["11/04/2024"],
            "unidades": ["1"],
            "importe": ["1.41"],
            "descuento": ["0.0"],
            "almacen": ["2"],
            "promocion": ["primavera_2024"],
        }
    )
    assert validar_csv_campana(primavera, Campaign.PRIMAVERA).ok
    # El mismo archivo como si fuera de verano: faltan todas las columnas.
    assert not validar_csv_campana(primavera, Campaign.VERANO).ok


def test_cli_validar_csv_codigo_de_salida(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    csv = tmp_path / "x.csv"
    csv.write_text("id_transaccion\n1\n", encoding="utf-8")
    assert validar_csv_main([str(csv), "--campaign", "primavera"]) == 1
    assert "[FALLA] columnas_faltantes" in capsys.readouterr().out


# --- Detección de gaps --------------------------------------------------------


def _gold(tmp_path: Path, dias_verano: list[str]) -> Path:
    gold = tmp_path / "gold"
    df = pd.DataFrame(
        {
            "campana": ["verano"] * len(dias_verano) + ["primavera"],
            "fecha": pd.to_datetime([*dias_verano, "2024-04-01"]),
            "revenue_neto": 1.0,
        }
    )
    escribir_parquet_atomico(df, gold / "campaign_performance")
    return gold


def test_detectar_gaps_encuentra_los_dias_que_faltan(tmp_path: Path) -> None:
    gold = _gold(tmp_path, ["2024-07-01", "2024-07-02", "2024-07-05"])
    gaps = detectar_gaps(gold, "verano", date(2024, 7, 1), date(2024, 7, 6))
    assert gaps == [date(2024, 7, 3), date(2024, 7, 4), date(2024, 7, 6)]


def test_detectar_gaps_sin_huecos_y_solo_mira_su_campana(tmp_path: Path) -> None:
    gold = _gold(tmp_path, ["2024-07-01", "2024-07-02"])
    assert detectar_gaps(gold, "verano", date(2024, 7, 1), date(2024, 7, 2)) == []
    # Primavera solo tiene el 1/4: el 2/4 es un gap aunque verano tenga datos.
    assert detectar_gaps(gold, "primavera", date(2024, 4, 1), date(2024, 4, 2)) == [
        date(2024, 4, 2)
    ]


def test_detectar_gaps_ventana_invertida_falla(tmp_path: Path) -> None:
    gold = _gold(tmp_path, ["2024-07-01"])
    with pytest.raises(ValueError, match="Ventana vacía"):
        detectar_gaps(gold, "verano", date(2024, 7, 2), date(2024, 7, 1))


def test_rango_con_datos(tmp_path: Path) -> None:
    gold = _gold(tmp_path, ["2024-07-01", "2024-07-05"])
    assert rango_con_datos(gold, "verano") == (date(2024, 7, 1), date(2024, 7, 5))
    assert rango_con_datos(gold, "otono") is None


def test_cli_gaps_sin_ventana_revisa_huecos_internos(tmp_path: Path) -> None:
    gold = _gold(tmp_path, ["2024-07-01", "2024-07-03"])
    args = ["--gold-dir", str(gold), "--campaign", "verano"]
    assert gaps_main(args) == 1  # falta el 2/7
    gold_ok = _gold(tmp_path / "ok", ["2024-07-01", "2024-07-02"])
    assert gaps_main(["--gold-dir", str(gold_ok), "--campaign", "verano"]) == 0


# --- Alertas a Slack (sin red: el envío se inyecta) ----------------------------------


class EnviadorFalso:
    def __init__(self, estado: int = 200) -> None:
        self.estado = estado
        self.llamadas: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, cuerpo: bytes) -> int:
        self.llamadas.append((url, json.loads(cuerpo)))
        return self.estado


def test_sin_gaps_no_se_envia_nada() -> None:
    enviador = EnviadorFalso()
    assert not enviar_alerta_slack([], "verano", "https://hooks.example/x", enviador)
    assert enviador.llamadas == []


def test_con_gaps_se_envia_el_mensaje_al_webhook_del_entorno(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.example/desde-env")
    enviador = EnviadorFalso()
    gaps = [date(2024, 7, 3), date(2024, 7, 4)]

    assert enviar_alerta_slack(gaps, "verano", enviar=enviador)

    [(url, mensaje)] = enviador.llamadas
    assert url == "https://hooks.example/desde-env"
    assert mensaje == construir_mensaje(gaps, "verano")
    assert "2024-07-03, 2024-07-04" in mensaje["text"]
    assert "Total: 2 día(s)" in mensaje["text"]


def test_con_gaps_y_sin_webhook_falla_en_voz_alta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    with pytest.raises(RuntimeError, match="SLACK_WEBHOOK_URL"):
        enviar_alerta_slack([date(2024, 7, 3)], "verano", enviar=EnviadorFalso())


def test_slack_responde_error() -> None:
    with pytest.raises(RuntimeError, match="500"):
        enviar_alerta_slack(
            [date(2024, 7, 3)], "verano", "https://hooks.example/x", EnviadorFalso(500)
        )
