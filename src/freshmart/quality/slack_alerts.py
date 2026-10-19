"""Alertas a Slack (Incoming Webhook) cuando faltan datos.

El webhook es un secreto: se lee de la variable de entorno ``SLACK_WEBHOOK_URL``
(``.env.example``), nunca del código. Regla contra la fatiga de alertas: solo se avisa
cuando hace falta acción humana; sin gaps no se envía nada.
"""

import json
import logging
import os
import urllib.request
from collections.abc import Callable, Sequence
from datetime import date

logger = logging.getLogger(__name__)

VARIABLE_WEBHOOK = "SLACK_WEBHOOK_URL"
TIMEOUT_S = 10

# (url, cuerpo JSON en bytes) -> código HTTP. Inyectable para no llamar a Slack en tests.
Enviador = Callable[[str, bytes], int]


def _post_json(url: str, cuerpo: bytes) -> int:
    peticion = urllib.request.Request(
        url, data=cuerpo, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(peticion, timeout=TIMEOUT_S) as respuesta:  # noqa: S310
        return int(respuesta.status)


def construir_mensaje(gaps: Sequence[date], campana: str) -> dict[str, str]:
    dias = ", ".join(d.isoformat() for d in gaps)
    return {
        "text": (
            f":warning: *ALERTA: gold sin datos* ({campana})\n"
            f"Días afectados: {dias}\n"
            f"Total: {len(gaps)} día(s)\n"
            "Acción: revisar el pipeline de campañas (raw → silver → gold) y relanzar "
            "los días afectados."
        )
    }


def enviar_alerta_slack(
    gaps: Sequence[date],
    campana: str,
    webhook_url: str | None = None,
    enviar: Enviador = _post_json,
) -> bool:
    """Envía la alerta si hay gaps. Devuelve si se envió algo.

    Sin webhook configurado lanza ``RuntimeError``: una alerta que no puede salir debe
    notarse, no perderse en silencio.
    """
    if not gaps:
        logger.info("Sin gaps: no se envía alerta")
        return False

    url = webhook_url or os.environ.get(VARIABLE_WEBHOOK)
    if not url:
        raise RuntimeError(
            f"Hay {len(gaps)} gaps pero {VARIABLE_WEBHOOK} no está configurada: "
            "no se puede avisar a Slack."
        )

    cuerpo = json.dumps(construir_mensaje(gaps, campana)).encode("utf-8")
    estado = enviar(url, cuerpo)
    if estado != 200:
        raise RuntimeError(f"Slack respondió {estado} al enviar la alerta")
    logger.info("Alerta enviada a Slack: %d gap(s) en %s", len(gaps), campana)
    return True
