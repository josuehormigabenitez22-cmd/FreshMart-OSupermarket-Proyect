"""Línea de comandos del inventario: CSV → silver (con cuarentena) → gold por tienda y día.

    python -m freshmart.inventory.cli --input data --silver-dir <silver> --gold-dir <gold>

Necesita el catálogo en silver (``ejecutar_pipeline.py --catalog``).
"""

import argparse
from collections.abc import Sequence
from pathlib import Path

from freshmart.inventory.gold import TABLA_TIENDA_DIA, run_gold_inventario
from freshmart.inventory.silver import InventarioValidationError, run_inventario
from freshmart.logging_config import configurar_logging


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventario diario a silver y gold.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--silver-dir", type=Path, required=True)
    parser.add_argument("--gold-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    configurar_logging()

    try:
        resultado = run_inventario(args.input, args.silver_dir)
    except InventarioValidationError as error:
        print(error.informe.resumen())
        print("Silver NO modificado.")
        return 1
    except FileNotFoundError as error:
        print(error)
        return 1

    print(resultado.informe.resumen())
    print(f"Filas escritas: {resultado.filas} · en cuarentena: {resultado.cuarentena}")
    filas_gold = run_gold_inventario(args.silver_dir, args.gold_dir)
    print(f"Gold: {TABLA_TIENDA_DIA} {filas_gold} filas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
