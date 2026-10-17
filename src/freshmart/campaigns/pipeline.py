"""Pipeline de campaña: raw (CSV) -> limpieza -> validación -> silver (Parquet).

Si alguna validación falla no se escribe nada en silver. Los paths no están en
el código: se reciben por argumentos (función y línea de comandos).

Layout de salida (estilo Hive):

    <silver_dir>/campaign_ventas/campana=<verano|primavera>/part-0.parquet

La columna ``campana`` no se guarda dentro del Parquet: la aporta la partición.
Al leer el directorio con pandas/pyarrow vuelve a aparecer como columna.
"""

import argparse
import logging
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from freshmart.campaigns.clean import leer_campana, limpiar_campana
from freshmart.campaigns.config import COL_CAMPANA, Campaign, get_config
from freshmart.campaigns.validate import InformeValidacion, validar

logger = logging.getLogger(__name__)

SILVER_TABLE = "campaign_ventas"
PARQUET_FILE = "part-0.parquet"


class PipelineValidationError(Exception):
    """Alguna validación falló: no se escribió nada en silver."""

    def __init__(self, informe: InformeValidacion) -> None:
        super().__init__(informe.resumen())
        self.informe = informe


@dataclass(frozen=True)
class PipelineResult:
    campaign: Campaign
    filas: int
    informe: InformeValidacion
    destino: Path


def partition_dir(silver_dir: Path, campaign: Campaign) -> Path:
    return silver_dir / SILVER_TABLE / f"{COL_CAMPANA}={get_config(campaign).particion}"


def escribir_silver(df: pd.DataFrame, silver_dir: Path, campaign: Campaign) -> Path:
    """Escribe la partición de la campaña en Parquet, reemplazándola entera.

    Se escribe primero en un directorio temporal oculto (que pyarrow ignora) y
    se renombra al final, para no dejar nunca una partición a medias.
    """
    destino = partition_dir(silver_dir, campaign)
    temporal = destino.with_name(f".{destino.name}.tmp")

    shutil.rmtree(temporal, ignore_errors=True)
    temporal.mkdir(parents=True)
    try:
        df.drop(columns=[COL_CAMPANA]).to_parquet(
            temporal / PARQUET_FILE, engine="pyarrow", index=False
        )
        if destino.exists():
            shutil.rmtree(destino)
        temporal.replace(destino)
    except Exception:
        shutil.rmtree(temporal, ignore_errors=True)
        raise

    return destino


def run_pipeline(
    campaign: Campaign, input_dir: Path, silver_dir: Path
) -> PipelineResult:
    """Ejecuta el pipeline de una campaña. Lanza PipelineValidationError si falla."""
    raw = leer_campana(campaign, input_dir)
    limpio = limpiar_campana(raw, campaign)

    informe = validar(limpio, campaign)
    if not informe.ok:
        logger.error("Validación fallida: no se escribe nada en silver")
        raise PipelineValidationError(informe)

    destino = escribir_silver(limpio, silver_dir, campaign)
    logger.info("Silver escrito: %s (%d filas)", destino, len(limpio))
    return PipelineResult(
        campaign=campaign, filas=len(limpio), informe=informe, destino=destino
    )


def parse_campaign(texto: str) -> Campaign:
    """Acepta 'verano_2024' (valor del Enum) o 'verano' (nombre de partición)."""
    for campaign in Campaign:
        if texto in (campaign.value, get_config(campaign).particion):
            return campaign
    validos = ", ".join(c.value for c in Campaign)
    raise argparse.ArgumentTypeError(
        f"campaña desconocida '{texto}' (válidas: {validos})"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Limpia y valida una campaña y la escribe en silver (Parquet)."
    )
    parser.add_argument("--campaign", type=parse_campaign, required=True)
    parser.add_argument(
        "--input", type=Path, required=True, help="Directorio con los CSV."
    )
    parser.add_argument(
        "--silver-dir", type=Path, required=True, help="Directorio silver."
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    try:
        resultado = run_pipeline(args.campaign, args.input, args.silver_dir)
    except PipelineValidationError as error:
        print(error.informe.resumen())
        print("Silver NO modificado.")
        return 1

    print(resultado.informe.resumen())
    print(f"Filas escritas: {resultado.filas}")
    print(f"Silver: {resultado.destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
