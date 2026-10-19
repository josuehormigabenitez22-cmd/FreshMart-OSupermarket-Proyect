"""
Validaciones de calidad sobre ventas de campaña ya limpias.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

import pandas as pd

from freshmart.campaigns.config import (
    COL_CANTIDAD,
    COL_DESCUENTO,
    COL_FECHA,
    COL_PRECIO,
    COL_VENTA_ID,
    COLUMNAS_LIMPIAS,
    Campaign,
    get_config,
)

logger = logging.getLogger(__name__)

NO_VACIO = "no_vacio"
COLUMNAS_ESPERADAS = "columnas_esperadas"
VENTA_ID_UNICO = "venta_id_unico"
FECHAS_VALIDAS = "fechas_validas"
FECHAS_EN_RANGO = "fechas_en_rango"
VALORES_VALIDOS = "valores_validos"


@dataclass(frozen=True)
class ResultadoValidacion:
    nombre: str
    ok: bool
    detalle: str


@dataclass(frozen=True)
class InformeValidacion:
    campaign: Campaign
    resultados: tuple[ResultadoValidacion, ...]

    @property
    def total(self) -> int:
        return len(self.resultados)

    @property
    def aprobadas(self) -> int:
        return sum(r.ok for r in self.resultados)

    @property
    def ok(self) -> bool:
        return self.aprobadas == self.total

    def resumen(self) -> str:
        lineas = [
            f"Validaciones {self.campaign.value}: {self.aprobadas}/{self.total} OK"
        ]
        lineas += [
            f"  [{'OK' if r.ok else 'FALLA'}] {r.nombre}: {r.detalle}"
            for r in self.resultados
        ]
        return "\n".join(lineas)


def _cumple(condicion: pd.Series) -> pd.Series:
    """Booleano limpio: los nulos (NA/NaN) cuentan como que NO cumplen"""
    return condicion.fillna(False).astype(bool)


def validar_no_vacio(df: pd.DataFrame) -> ResultadoValidacion:
    filas = len(df)
    return ResultadoValidacion(NO_VACIO, filas > 0, f"{filas} filas")


def validar_columnas(df: pd.DataFrame) -> ResultadoValidacion:
    faltan = [c for c in COLUMNAS_LIMPIAS if c not in df.columns]
    detalle = (
        f"faltan {faltan}" if faltan else f"{len(COLUMNAS_LIMPIAS)} columnas presentes"
    )
    return ResultadoValidacion(COLUMNAS_ESPERADAS, not faltan, detalle)


def validar_venta_id_unico(df: pd.DataFrame) -> ResultadoValidacion:
    nulos = int(df[COL_VENTA_ID].isna().sum())
    repetidos = int(df[COL_VENTA_ID].dropna().duplicated().sum())
    ok = nulos == 0 and repetidos == 0
    return ResultadoValidacion(
        VENTA_ID_UNICO, ok, f"{nulos} nulos, {repetidos} repetidos"
    )


def validar_fechas(df: pd.DataFrame) -> ResultadoValidacion:
    # lo que no sea una fecha válida pasa a NaT y se cuenta
    fechas = pd.to_datetime(df[COL_FECHA], errors="coerce")
    invalidas = int(fechas.isna().sum())
    return ResultadoValidacion(
        FECHAS_VALIDAS, invalidas == 0, f"{invalidas} fechas inválidas"
    )


# Añadimos una función de validez para verificar que las fechas están en rango
def validar_fechas_en_rango(
    df: pd.DataFrame, campaign: Campaign
) -> ResultadoValidacion:
    """
    Las fechas deben caer dentro del periodo de la campaña.
    Las fechas nulas o inválidas no cuentan aquí: ya las reporta la función de fechas_validas
    """
    config = get_config(campaign)
    dias = pd.to_datetime(df[COL_FECHA], errors="coerce").dt.normalize()
    inicio, fin = pd.Timestamp(config.fecha_min), pd.Timestamp(config.fecha_max)
    fuera = int((dias.notna() & ~dias.between(inicio, fin)).sum())
    return ResultadoValidacion(
        FECHAS_EN_RANGO,
        fuera == 0,
        f"{fuera} fuera de [{config.fecha_min}, {config.fecha_max}]",
    )


def validar_valores(df: pd.DataFrame) -> ResultadoValidacion:
    cantidad_mala = int((~_cumple(df[COL_CANTIDAD] >= 1)).sum())
    precio_malo = int((~_cumple(df[COL_PRECIO] > 0)).sum())
    descuento_malo = int((~_cumple(df[COL_DESCUENTO].between(0, 100))).sum())
    ok = cantidad_mala + precio_malo + descuento_malo == 0
    detalle = (
        f"cantidad<1: {cantidad_mala}, precio<=0: {precio_malo}, descuento fuera de 0-100: "
        f"{descuento_malo}"
    )
    return ResultadoValidacion(VALORES_VALIDOS, ok, detalle)


_BLOQUEANTES = frozenset({NO_VACIO, COLUMNAS_ESPERADAS})


def _validaciones(
    campaign: Campaign,
) -> tuple[tuple[str, Callable[[pd.DataFrame], ResultadoValidacion]], ...]:
    """
    Orden de ejecución. Las dos primeras son bloqueantes: sin filas o sin columnas el resto de comprobaciones no tiene sentido
    """
    return (
        (NO_VACIO, validar_no_vacio),
        (COLUMNAS_ESPERADAS, validar_columnas),
        (VENTA_ID_UNICO, validar_venta_id_unico),
        (FECHAS_VALIDAS, validar_fechas),
        (FECHAS_EN_RANGO, partial(validar_fechas_en_rango, campaign=campaign)),
        (VALORES_VALIDOS, validar_valores),
    )


def validar(df: pd.DataFrame, campaign: Campaign) -> InformeValidacion:
    """Ejecuta las 6 validaciones, empezando por la comprobación de DataFrame vacío"""
    resultados: list[ResultadoValidacion] = []
    bloqueado_por: str | None = None

    for nombre, funcion in _validaciones(campaign):
        if bloqueado_por is not None:
            resultado = ResultadoValidacion(
                nombre, False, f"no ejecutada ({bloqueado_por} falló)"
            )
        else:
            resultado = funcion(df)
            if not resultado.ok and nombre in _BLOQUEANTES:
                bloqueado_por = nombre

        log = logger.info if resultado.ok else logger.error
        log("[%s] %s: %s", campaign.value, resultado.nombre, resultado.detalle)
        resultados.append(resultado)

    return InformeValidacion(campaign=campaign, resultados=tuple(resultados))
