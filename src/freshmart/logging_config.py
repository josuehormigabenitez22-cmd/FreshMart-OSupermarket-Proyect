"""Formato de logs común a todas las CLI del proyecto."""

import logging

from freshmart.settings import LOG_LEVEL

FORMATO = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def configurar_logging(nivel: str = LOG_LEVEL) -> None:
    """Configura el logger raíz. Solo se llama desde los ``main()``, nunca al importar."""
    logging.basicConfig(level=nivel.upper(), format=FORMATO, force=True)
