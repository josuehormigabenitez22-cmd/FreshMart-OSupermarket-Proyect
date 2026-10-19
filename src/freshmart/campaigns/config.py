"""
Configuración por campaña: qué archivo leer y cómo mapear sus columnas.

Cada campaña llega con nombres de columna y convenciones distintas. Aquí se
declaran las diferencias para que clean.py sea el mismo para todas.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from types import MappingProxyType
from typing import Final


class Campaign(StrEnum):
    """Los valores coinciden con la columna campana / promocion de los CSV"""

    VERANO = "verano_2024"
    PRIMAVERA = "primavera_2024"


# Esquema común de salida (los nombres de la campaña de verano).
COL_VENTA_ID = "venta_id"
COL_CLIENTE_ID = "cliente_id"
COL_PRODUCTO_ID = "producto_id"
COL_FECHA = "fecha_compra"
COL_CANTIDAD = "cantidad"
COL_PRECIO = "precio"
COL_DESCUENTO = "descuento_pct"
COL_TIENDA_ID = "tienda_id"
COL_CAMPANA = "campana"
COLUMNAS_CANONICAS: tuple[str, ...] = (
    COL_VENTA_ID,
    COL_CLIENTE_ID,
    COL_PRODUCTO_ID,
    COL_FECHA,
    COL_CANTIDAD,
    COL_PRECIO,
    COL_DESCUENTO,
    COL_TIENDA_ID,
    COL_CAMPANA,
)

# Columna derivada: la crea la limpieza, no viene en el CSV.
COL_CLIENTE_ANONIMO: Final = "cliente_anonimo"

# Esquema final del silver: columnas canónicas + derivadas.
COLUMNAS_LIMPIAS: tuple[str, ...] = (*COLUMNAS_CANONICAS, COL_CLIENTE_ANONIMO)

# Columnas que se convierten a Int64 (admite nulos).
COLUMNAS_ENTERAS: tuple[str, ...] = (
    COL_VENTA_ID,
    COL_CLIENTE_ID,
    COL_PRODUCTO_ID,
    COL_CANTIDAD,
    COL_TIENDA_ID,
)


@dataclass(frozen=True)
class CampaignConfig:
    archivo: str
    # Nombre original en el CSV -> nombre canónico.
    columnas: Mapping[str, str]
    # Cómo codifica la campaña a los clientes anónimos en cliente_id.
    # None = ya vienen como vacío (nulo); un entero = valor centinela.
    anonimo_valor: int | None
    particion: str  # valor de campana=<...> en silver
    # Periodo de la campaña con ambos extremos incluidos
    fecha_min: date
    fecha_max: date


CONFIGS: Mapping[Campaign, CampaignConfig] = MappingProxyType(
    {
        Campaign.VERANO: CampaignConfig(
            archivo="campana_verano_ventas.csv",
            columnas=MappingProxyType({c: c for c in COLUMNAS_CANONICAS}),
            anonimo_valor=None,
            particion="verano",
            fecha_min=date(2024, 6, 15),
            fecha_max=date(2024, 9, 15),
        ),
        Campaign.PRIMAVERA: CampaignConfig(
            archivo="campana_primavera_ventas.csv",
            columnas=MappingProxyType(
                {
                    "id_transaccion": COL_VENTA_ID,
                    "id_cliente": COL_CLIENTE_ID,
                    "id_producto": COL_PRODUCTO_ID,
                    "fecha_venta": COL_FECHA,
                    "unidades": COL_CANTIDAD,
                    "importe": COL_PRECIO,
                    "descuento": COL_DESCUENTO,
                    "almacen": COL_TIENDA_ID,
                    "promocion": COL_CAMPANA,
                }
            ),
            anonimo_valor=-1,
            particion="primavera",
            fecha_min=date(2024, 3, 1),
            fecha_max=date(2024, 5, 31),
        ),
    }
)


def get_config(campaign: Campaign) -> CampaignConfig:
    return CONFIGS[campaign]
