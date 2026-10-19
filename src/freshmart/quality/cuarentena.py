"""Cuarentena de filas: apartar lo inválido sin borrarlo ni bloquear la tabla entera.

Regla del equipo: un dato raro se consulta, no se elimina. Para problemas de **tabla**
(vacía, clave repetida, esquema) el pipeline no escribe nada. Para problemas de **fila**
(stock negativo, precio negativo, total que no cuadra) las filas se apartan a
``silver/_cuarentena/<tabla>/`` con el motivo y el resto sigue. Ver
docs/decisions/005-cuarentena.md.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from freshmart.lake.parquet import escribir_parquet_atomico
from freshmart.quality.result import ResultadoValidacion, Severidad

DIRECTORIO_CUARENTENA = "_cuarentena"
COL_MOTIVO = "motivo_cuarentena"


@dataclass(frozen=True)
class Cuarentena:
    validas: pd.DataFrame
    apartadas: pd.DataFrame  # mismas columnas + motivo_cuarentena
    # Filas que incumplen cada regla (una fila puede contar en varias).
    conteo: dict[str, int]

    def resultados(self) -> list[ResultadoValidacion]:
        """Una comprobación AVISO por regla: informa sin bloquear."""
        return [
            ResultadoValidacion(
                f"cuarentena_{regla}",
                n == 0,
                f"{n} filas a cuarentena",
                Severidad.AVISO,
            )
            for regla, n in self.conteo.items()
        ]


def separar_cuarentena(df: pd.DataFrame, reglas: Mapping[str, pd.Series]) -> Cuarentena:
    """Separa las filas que incumplen alguna regla.

    ``reglas``: nombre -> máscara booleana con ``True`` en las filas que la INCUMPLEN.
    Los nulos en una máscara cuentan como que cumplen (de los nulos se ocupan otras
    validaciones).
    """
    incumple = pd.DataFrame(
        {
            nombre: mascara.fillna(False).astype(bool)
            for nombre, mascara in reglas.items()
        },
        index=df.index,
    )
    malas = incumple.any(axis=1).astype(bool)

    solo_malas = incumple[malas]
    motivos = pd.Series(
        [";".join(solo_malas.columns[fila]) for fila in solo_malas.to_numpy()],
        index=solo_malas.index,
        dtype="string",
    )
    apartadas = df[malas].assign(**{COL_MOTIVO: motivos})
    return Cuarentena(
        validas=df[~malas].reset_index(drop=True),
        apartadas=apartadas.reset_index(drop=True),
        conteo={nombre: int(incumple[nombre].sum()) for nombre in incumple.columns},
    )


def escribir_cuarentena(apartadas: pd.DataFrame, silver_dir: Path, tabla: str) -> Path:
    """Reemplaza la cuarentena de la tabla (también si queda vacía: refleja la última carga)."""
    return escribir_parquet_atomico(
        apartadas, silver_dir / DIRECTORIO_CUARENTENA / tabla
    )
