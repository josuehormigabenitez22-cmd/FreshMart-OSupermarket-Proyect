"""Limpieza de las ventas de campaña.

Una función pura por problema (no mutan su entrada) y una función de
orquestación, ``limpiar_campana``, que las encadena según la configuración.
"""

import logging
import re
from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from freshmart.campaigns.config import (
    COL_CANTIDAD,
    COL_CLIENTE_ANONIMO,
    COL_CLIENTE_ID,
    COL_DESCUENTO,
    COL_FECHA,
    COL_PRECIO,
    COLUMNAS_ENTERAS,
    COLUMNAS_LIMPIAS,
    Campaign,
    get_config,
)
from freshmart.settings import DATA_DIR

logger = logging.getLogger(__name__)

# --- Máscaras de fecha -------------------------------------------------------
# Cada máscara identifica un formato concreto; nunca se deja que pandas "adivine"
# el formato fila a fila (dd/mm vs mm/dd es ambiguo en 4.323 filas de verano).
MASCARA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MASCARA_DIA_MES_ANIO = re.compile(r"^\d{2}/\d{2}/\d{4}$")
MASCARA_MES_TEXTO = re.compile(r"^([A-Z][a-z]{2}) (\d{1,2}), (\d{4})$")

# Meses en inglés, sin depender del locale del sistema (%b cambia en Windows).
MESES_EN = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}

# "9,89€", "0,8€", "1.41", "12". Rechaza separadores de miles ("1.234,56€").
PATRON_PRECIO = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*€?\s*$")


def renombrar_columnas(df: pd.DataFrame, columnas: Mapping[str, str]) -> pd.DataFrame:
    """Renombra a los nombres canónicos y exige que estén todas las columnas."""
    faltan = [c for c in columnas if c not in df.columns]
    if faltan:
        raise KeyError(f"Faltan columnas en el CSV: {faltan}")

    resultado = df[list(columnas)].rename(columns=dict(columnas))
    logger.info("Columnas renombradas: %d", len(columnas))
    return resultado


def eliminar_duplicados(df: pd.DataFrame) -> pd.DataFrame:
    """Elimina filas exactamente repetidas (conserva la primera aparición)."""
    resultado = df.drop_duplicates(keep="first").reset_index(drop=True)
    eliminadas = len(df) - len(resultado)
    if eliminadas:
        logger.warning("Duplicados exactos eliminados: %d", eliminadas)
    else:
        logger.info("Sin duplicados exactos")
    return resultado


def parsear_fechas(fechas: pd.Series) -> pd.Series:
    """Parsea fechas por máscara: ISO, dd/mm/aaaa y 'Mes d, aaaa' (inglés).

    Los nulos se mantienen como NaT. Un valor que no encaje en ninguna máscara,
    o una fecha imposible (31/02/2024), lanza ValueError.
    """
    texto = fechas.astype("string").str.strip()
    resultado = pd.Series(pd.NaT, index=texto.index, dtype="datetime64[ns]")

    es_iso = texto.str.match(MASCARA_ISO).fillna(False).astype(bool)
    es_dmy = texto.str.match(MASCARA_DIA_MES_ANIO).fillna(False).astype(bool)
    es_texto = texto.str.match(MASCARA_MES_TEXTO).fillna(False).astype(bool)

    desconocidas = texto.notna() & ~(es_iso | es_dmy | es_texto)
    if desconocidas.any():
        ejemplos = texto[desconocidas].head(3).tolist()
        raise ValueError(
            f"{int(desconocidas.sum())} fechas no encajan en ninguna máscara: {ejemplos}"
        )

    if es_iso.any():
        resultado.loc[es_iso] = pd.to_datetime(texto[es_iso], format="%Y-%m-%d")
    if es_dmy.any():
        resultado.loc[es_dmy] = pd.to_datetime(texto[es_dmy], format="%d/%m/%Y")
    if es_texto.any():
        partes = texto[es_texto].str.extract(MASCARA_MES_TEXTO)
        meses = partes[0].map(MESES_EN)
        if meses.isna().any():
            malos = partes.loc[meses.isna(), 0].head(3).tolist()
            raise ValueError(f"Mes en texto desconocido: {malos}")
        iso = (
            partes[2]
            + "-"
            + meses.astype(int).astype(str).str.zfill(2)
            + "-"
            + partes[1].str.zfill(2)
        )
        resultado.loc[es_texto] = pd.to_datetime(iso, format="%Y-%m-%d")

    logger.info(
        "Fechas parseadas: iso=%d dia/mes/anio=%d mes_texto=%d nulas=%d",
        int(es_iso.sum()),
        int(es_dmy.sum()),
        int(es_texto.sum()),
        int(texto.isna().sum()),
    )
    return resultado.astype("datetime64[ns]")


def parsear_precio(precios: pd.Series) -> pd.Series:
    """Convierte precios en texto a float. '0,8€' es válido (=0.8).

    Los nulos se mantienen. Cualquier otro formato lanza ValueError.
    """
    texto = precios.astype("string")
    numero = texto.str.extract(PATRON_PRECIO)[0]

    invalidos = texto.notna() & numero.isna()
    if invalidos.any():
        ejemplos = texto[invalidos].head(3).tolist()
        raise ValueError(f"{int(invalidos.sum())} precios inválidos: {ejemplos}")

    resultado = numero.str.replace(",", ".", regex=False).astype("float64")
    logger.info("Precios convertidos: %d", int(resultado.notna().sum()))
    return resultado


def normalizar_enteros(valores: pd.Series) -> pd.Series:
    """Convierte a Int64 (con nulos). Acepta '105049.0'; rechaza '1.5'."""
    numeros = pd.to_numeric(valores, errors="raise")

    no_enteros = numeros.notna() & (numeros % 1 != 0)
    if no_enteros.any():
        ejemplos = valores[no_enteros].head(3).tolist()
        raise ValueError(f"Valores no enteros: {ejemplos}")

    resultado = numeros.astype("Int64")
    logger.info(
        "%s -> Int64: %d valores (nulos: %d)",
        valores.name,
        len(resultado),
        int(resultado.isna().sum()),
    )
    return resultado


def marcar_anonimos(ids: pd.Series, anonimo_valor: int | None) -> pd.Series:
    """Sustituye el valor centinela de anónimo por nulo.

    Si la campaña ya marca los anónimos como nulos (``anonimo_valor=None``),
    devuelve los ids tal cual.
    """
    if anonimo_valor is None:
        return ids.copy()

    es_anonimo = (ids == anonimo_valor).fillna(False).astype(bool)
    logger.info(
        "Clientes anónimos (%s) pasados a nulo: %d",
        anonimo_valor,
        int(es_anonimo.sum()),
    )
    return ids.mask(es_anonimo)


def eliminar_cantidades_no_positivas(df: pd.DataFrame) -> pd.DataFrame:
    """Descarta ventas con cantidad <= 0: una venta de 0 unidades no es una venta.

    Las cantidades nulas NO se descartan aquí: las reporta la validación.
    """
    no_positiva = (df[COL_CANTIDAD] <= 0).fillna(False).astype(bool)
    resultado = df.loc[~no_positiva].reset_index(drop=True)
    if no_positiva.any():
        logger.warning(
            "Ventas con cantidad <= 0 descartadas: %d", int(no_positiva.sum())
        )
    else:
        logger.info("Sin ventas con cantidad <= 0")
    return resultado


def leer_campana(campaign: Campaign, data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """Lee el CSV crudo de la campaña con todo como texto."""
    ruta = data_dir / get_config(campaign).archivo
    df = pd.read_csv(ruta, dtype=str)
    logger.info("Leído %s: %d filas", ruta.name, len(df))
    return df


def limpiar_campana(raw: pd.DataFrame, campaign: Campaign) -> pd.DataFrame:
    """Aplica la limpieza completa según la configuración de la campaña."""
    config = get_config(campaign)

    df = renombrar_columnas(raw, config.columnas)
    df = eliminar_duplicados(df)

    df[COL_FECHA] = parsear_fechas(df[COL_FECHA])
    df[COL_PRECIO] = parsear_precio(df[COL_PRECIO])
    df[COL_DESCUENTO] = pd.to_numeric(df[COL_DESCUENTO], errors="raise").astype(
        "float64"
    )

    for columna in COLUMNAS_ENTERAS:
        df[columna] = normalizar_enteros(df[columna])

    df = eliminar_cantidades_no_positivas(df)

    df[COL_CLIENTE_ID] = marcar_anonimos(df[COL_CLIENTE_ID], config.anonimo_valor)
    df[COL_CLIENTE_ANONIMO] = df[COL_CLIENTE_ID].isna()

    logger.info("Campaña %s limpia: %d filas", campaign.value, len(df))
    return df[list(COLUMNAS_LIMPIAS)]
