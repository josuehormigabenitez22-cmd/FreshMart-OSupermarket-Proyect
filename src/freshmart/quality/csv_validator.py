"""Validador de CSV de entrada: detectar los problemas ANTES de procesar ("fail fast").

    python -m freshmart.quality.csv_validator data/campana_verano_ventas.csv --campaign verano

Comprueba estructura (columnas), tipos, nulos y duplicados, y devuelve un
``InformeCalidad`` (ver ``quality/result.py``): los ERROR impiden procesar el archivo
y los AVISO se informan para que nadie se lleve sorpresas en la limpieza.

Las fechas se comprueban con las mismas máscaras que usa la limpieza
(``campaigns/clean.py``), no con ``dayfirst=True``: así se detecta qué formatos trae el
archivo y si alguno es desconocido.
"""

import argparse
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal

import pandas as pd

from freshmart.campaigns.clean import (
    MASCARA_DIA_MES_ANIO,
    MASCARA_ISO,
    MASCARA_MES_TEXTO,
)
from freshmart.campaigns.cli import parse_campaign
from freshmart.campaigns.config import (
    COL_CANTIDAD,
    COL_DESCUENTO,
    COL_FECHA,
    COL_PRODUCTO_ID,
    COL_VENTA_ID,
    Campaign,
    get_config,
)
from freshmart.quality.result import InformeCalidad, ResultadoValidacion, Severidad

TipoColumna = Literal["numeric", "datetime", "string"]

FORMATOS_FECHA = {
    "AAAA-MM-DD": MASCARA_ISO,
    "DD/MM/AAAA": MASCARA_DIA_MES_ANIO,
    "Mon D, AAAA": MASCARA_MES_TEXTO,
}
DESCONOCIDO = "desconocido"


def detectar_formatos_fecha(valores: pd.Series) -> dict[str, int]:
    """Cuántos valores no nulos hay de cada formato de fecha conocido (y desconocidos)."""
    texto = valores.dropna().astype("string").str.strip()
    conteo: dict[str, int] = {}
    reconocidos = pd.Series(False, index=texto.index)
    for nombre, mascara in FORMATOS_FECHA.items():
        coincide = texto.str.match(mascara).fillna(False).astype(bool)
        if coincide.any():
            conteo[nombre] = int(coincide.sum())
        reconocidos |= coincide
    if (~reconocidos).any():
        conteo[DESCONOCIDO] = int((~reconocidos).sum())
    return conteo


def _validar_tipo(
    df: pd.DataFrame, columna: str, tipo: TipoColumna
) -> list[ResultadoValidacion]:
    valores = df[columna]
    if tipo == "numeric":
        malos = pd.to_numeric(valores, errors="coerce").isna() & valores.notna()
        ejemplos = valores[malos].head(3).tolist()
        return [
            ResultadoValidacion(
                f"tipo_{columna}",
                not malos.any(),
                f"{int(malos.sum())} valores no numéricos"
                + (f", p. ej. {ejemplos}" if ejemplos else ""),
            )
        ]
    if tipo == "datetime":
        formatos = detectar_formatos_fecha(valores)
        desconocidas = formatos.pop(DESCONOCIDO, 0)
        return [
            ResultadoValidacion(
                f"tipo_{columna}",
                desconocidas == 0,
                f"{desconocidas} fechas con formato desconocido",
            ),
            ResultadoValidacion(
                f"formatos_{columna}",
                len(formatos) <= 1,
                f"{len(formatos)} formatos: {formatos}",
                Severidad.AVISO,
            ),
        ]
    return []


def validar_csv(
    df: pd.DataFrame,
    columnas_esperadas: Sequence[str],
    tipos: Mapping[str, TipoColumna] | None = None,
    max_pct_nulos: float = 0.05,
    columnas_criticas: Sequence[str] = (),
    titulo: str = "Validación CSV",
) -> InformeCalidad:
    """Valida un CSV leído con ``dtype=str`` contra el esquema esperado."""
    resultados = [ResultadoValidacion("no_vacio", len(df) > 0, f"{len(df)} filas")]

    # 1. Estructura
    faltan = [c for c in columnas_esperadas if c not in df.columns]
    sobran = [c for c in df.columns if c not in columnas_esperadas]
    resultados += [
        ResultadoValidacion(
            "columnas_faltantes",
            not faltan,
            f"faltan {faltan}" if faltan else "ninguna",
        ),
        ResultadoValidacion(
            "columnas_extra",
            not sobran,
            f"no esperadas: {sobran}" if sobran else "ninguna",
            Severidad.AVISO,
        ),
    ]

    # 2. Tipos (solo de las columnas que existen)
    for columna, tipo in (tipos or {}).items():
        if columna in df.columns:
            resultados += _validar_tipo(df, columna, tipo)

    # 3. Nulos
    nulos_criticos = {
        c: int(df[c].isna().sum())
        for c in columnas_criticas
        if c in df.columns and df[c].isna().any()
    }
    resultados.append(
        ResultadoValidacion(
            "nulos_en_criticas",
            not nulos_criticos,
            f"nulos: {nulos_criticos}" if nulos_criticos else "ninguno",
        )
    )
    pct_nulos = df.isna().mean() if len(df) else pd.Series(dtype="float64")
    por_encima = {c: f"{p:.1%}" for c, p in pct_nulos.items() if p > max_pct_nulos}
    resultados.append(
        ResultadoValidacion(
            "umbral_nulos",
            not por_encima,
            f"por encima del {max_pct_nulos:.0%}: {por_encima}"
            if por_encima
            else f"todas por debajo del {max_pct_nulos:.0%}",
            Severidad.AVISO,
        )
    )

    # 4. Duplicados exactos (la limpieza los elimina: se avisa, no se bloquea)
    duplicados = int(df.duplicated().sum())
    resultados.append(
        ResultadoValidacion(
            "duplicados_exactos",
            duplicados == 0,
            f"{duplicados} filas duplicadas",
            Severidad.AVISO,
        )
    )

    return InformeCalidad(titulo=titulo, resultados=tuple(resultados))


def validar_csv_campana(df: pd.DataFrame, campaign: Campaign) -> InformeCalidad:
    """Valida el CSV de una campaña con el esquema que declara su ``CampaignConfig``."""
    config = get_config(campaign)
    original = {canonica: origen for origen, canonica in config.columnas.items()}
    return validar_csv(
        df,
        columnas_esperadas=list(config.columnas),
        tipos={
            original[COL_FECHA]: "datetime",
            original[COL_CANTIDAD]: "numeric",
            original[COL_DESCUENTO]: "numeric",
        },
        columnas_criticas=[
            original[COL_VENTA_ID],
            original[COL_PRODUCTO_ID],
            original[COL_FECHA],
        ],
        titulo=f"CSV {config.archivo}",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Valida un CSV de campaña antes de subirlo a raw."
    )
    parser.add_argument("csv", type=Path)
    parser.add_argument("--campaign", type=parse_campaign, required=True)
    args = parser.parse_args(argv)

    informe = validar_csv_campana(pd.read_csv(args.csv, dtype=str), args.campaign)
    print(informe.resumen())
    return 0 if informe.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
