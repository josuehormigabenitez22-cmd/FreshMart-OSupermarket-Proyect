"""Línea de comandos del pipeline de campañas.

    python -m freshmart.campaigns.cli --campaign verano --input data --silver-dir <dir>
    python -m freshmart.campaigns.cli --all --input data --silver-dir <dir>

Con ``--all`` se procesan todas las campañas del Enum. Cada una es independiente:
si una falla la validación, su partición de silver no se toca y el resto sigue.
El código de salida es 1 si alguna falló.
"""

import argparse
from collections.abc import Sequence
from pathlib import Path

from freshmart.campaigns.config import Campaign, get_config
from freshmart.campaigns.pipeline import PipelineValidationError, run_pipeline
from freshmart.logging_config import configurar_logging


def parse_campaign(texto: str) -> Campaign:
    """Acepta 'verano_2024' (valor del Enum) o 'verano' (nombre de partición)."""
    for campaign in Campaign:
        if texto in (campaign.value, get_config(campaign).particion):
            return campaign
    validos = ", ".join(get_config(c).particion for c in Campaign)
    raise argparse.ArgumentTypeError(
        f"campaña desconocida '{texto}' (válidas: {validos})"
    )


def crear_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Limpia y valida campañas y las escribe en silver (Parquet)."
    )
    seleccion = parser.add_mutually_exclusive_group(required=True)
    seleccion.add_argument(
        "--campaign",
        type=parse_campaign,
        help="Campaña a procesar: verano o primavera.",
    )
    seleccion.add_argument(
        "--all", action="store_true", help="Procesa todas las campañas."
    )
    parser.add_argument(
        "--input", type=Path, required=True, help="Directorio con los CSV."
    )
    parser.add_argument(
        "--silver-dir", type=Path, required=True, help="Directorio silver."
    )
    return parser


def procesar(campaign: Campaign, input_dir: Path, silver_dir: Path) -> bool:
    """Ejecuta una campaña e imprime su resumen. Devuelve si se escribió silver."""
    try:
        resultado = run_pipeline(campaign, input_dir, silver_dir)
    except PipelineValidationError as error:
        print(error.informe.resumen())
        print("Silver NO modificado.")
        return False

    print(resultado.informe.resumen())
    print(f"Filas escritas: {resultado.filas}")
    print(f"Silver: {resultado.destino}")
    return True


def main(argv: Sequence[str] | None = None) -> int:
    args = crear_parser().parse_args(argv)
    configurar_logging()

    campanas = list(Campaign) if args.all else [args.campaign]
    fallidas = [c for c in campanas if not procesar(c, args.input, args.silver_dir)]

    if len(campanas) > 1:
        print(f"Campañas OK: {len(campanas) - len(fallidas)}/{len(campanas)}")
    return 1 if fallidas else 0


if __name__ == "__main__":
    raise SystemExit(main())
