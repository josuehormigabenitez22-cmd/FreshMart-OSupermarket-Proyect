"""Línea de comandos del pipeline de campañas.

    # silver de una campaña o de todas
    python -m freshmart.campaigns.cli --campaign verano --input data --silver-dir <silver>
    python -m freshmart.campaigns.cli --all --input data --silver-dir <silver>
    # silver del catálogo (productos y categorías), lo necesita gold
    python -m freshmart.campaigns.cli --catalog --input data --silver-dir <silver>
    # gold a partir de silver ya construido
    python -m freshmart.campaigns.cli --only-gold --silver-dir <silver> --gold-dir <gold>

Con ``--all`` se procesan todas las campañas del Enum. Cada una es independiente:
si una falla la validación, su partición de silver no se toca y el resto sigue.
Si además se pasa ``--gold-dir``, gold se reconstruye solo cuando todas han ido bien.
El código de salida es 1 si algo falló.
"""

import argparse
from collections.abc import Sequence
from pathlib import Path

from freshmart.campaigns.config import Campaign, get_config
from freshmart.campaigns.gold import run_gold
from freshmart.campaigns.pipeline import PipelineValidationError, run_pipeline
from freshmart.catalog.silver import CatalogoValidationError, run_catalogo
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
        description="Pipeline de campañas: CSV → silver (Parquet) → gold."
    )
    accion = parser.add_mutually_exclusive_group(required=True)
    accion.add_argument(
        "--campaign",
        type=parse_campaign,
        help="Campaña a procesar a silver: verano o primavera.",
    )
    accion.add_argument(
        "--all", action="store_true", help="Procesa todas las campañas a silver."
    )
    accion.add_argument(
        "--catalog",
        action="store_true",
        help="Procesa productos y categorías a silver.",
    )
    accion.add_argument(
        "--only-gold",
        action="store_true",
        help="Construye gold a partir de silver, sin leer CSV.",
    )
    parser.add_argument("--input", type=Path, help="Directorio con los CSV.")
    parser.add_argument(
        "--silver-dir", type=Path, required=True, help="Directorio silver."
    )
    parser.add_argument(
        "--gold-dir",
        type=Path,
        help="Directorio gold. Obligatorio con --only-gold; con --campaign/--all "
        "reconstruye gold después de silver.",
    )
    return parser


def _validar_argumentos(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> None:
    if args.only_gold:
        if args.gold_dir is None:
            parser.error("--only-gold necesita --gold-dir")
    elif args.input is None:
        parser.error("--input es obligatorio salvo con --only-gold")


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


def procesar_catalogo(input_dir: Path, silver_dir: Path) -> bool:
    try:
        resultado = run_catalogo(input_dir, silver_dir)
    except CatalogoValidationError as error:
        print(f"Catálogo no válido: {error}")
        print("Silver NO modificado.")
        return False
    print(
        f"Catálogo: {resultado.productos} productos, {resultado.categorias} categorías"
    )
    return True


def procesar_gold(silver_dir: Path, gold_dir: Path) -> bool:
    try:
        resultado = run_gold(silver_dir, gold_dir)
    except FileNotFoundError as error:
        print(error)
        print("Gold NO modificado.")
        return False
    print(
        f"Gold: campaign_performance {resultado.performance} filas, "
        f"campaign_top_products {resultado.top_products} filas"
    )
    return True


def main(argv: Sequence[str] | None = None) -> int:
    parser = crear_parser()
    args = parser.parse_args(argv)
    _validar_argumentos(parser, args)
    configurar_logging()

    if args.only_gold:
        return 0 if procesar_gold(args.silver_dir, args.gold_dir) else 1
    if args.catalog:
        return 0 if procesar_catalogo(args.input, args.silver_dir) else 1

    campanas = list(Campaign) if args.all else [args.campaign]
    fallidas = [c for c in campanas if not procesar(c, args.input, args.silver_dir)]
    if len(campanas) > 1:
        print(f"Campañas OK: {len(campanas) - len(fallidas)}/{len(campanas)}")
    if fallidas:
        if args.gold_dir is not None:
            print("Gold NO reconstruido: alguna campaña falló.")
        return 1

    if args.gold_dir is not None and not procesar_gold(args.silver_dir, args.gold_dir):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
