"""Resultado de validación único para todo el proyecto.

Lo usan las validaciones del pipeline (``campaigns/validate.py``), las del catálogo y el
validador de CSV de entrada (``quality/csv_validator.py``). En vez de tener
una clase con listas de errores y otra con warnings, cada comprobación es un ``ResultadoValidacion`` con su severidad, y un informe las
agrupa.

* ``ERROR``: si falla, el informe no es válido (no se escribe, no se procesa).
* ``AVISO``: se informa pero no bloquea (p. ej. duplicados que la limpieza ya elimina).
"""

from dataclasses import dataclass
from enum import StrEnum


class Severidad(StrEnum):
    ERROR = "error"
    AVISO = "aviso"


@dataclass(frozen=True)
class ResultadoValidacion:
    nombre: str
    ok: bool
    detalle: str
    severidad: Severidad = Severidad.ERROR


@dataclass(frozen=True)
class InformeCalidad:
    titulo: str
    resultados: tuple[ResultadoValidacion, ...]

    @property
    def total(self) -> int:
        return len(self.resultados)

    @property
    def aprobadas(self) -> int:
        return sum(r.ok for r in self.resultados)

    @property
    def errores(self) -> tuple[ResultadoValidacion, ...]:
        return tuple(
            r for r in self.resultados if not r.ok and r.severidad is Severidad.ERROR
        )

    @property
    def avisos(self) -> tuple[ResultadoValidacion, ...]:
        return tuple(
            r for r in self.resultados if not r.ok and r.severidad is Severidad.AVISO
        )

    @property
    def ok(self) -> bool:
        """Válido si no falla ninguna comprobación de severidad ERROR."""
        return not self.errores

    def resumen(self) -> str:
        cabecera = f"{self.titulo}: {self.aprobadas}/{self.total} OK"
        if self.avisos:
            cabecera += f" ({len(self.avisos)} avisos)"
        lineas = [cabecera]
        for r in self.resultados:
            if r.ok:
                marca = "OK"
            elif r.severidad is Severidad.AVISO:
                marca = "AVISO"
            else:
                marca = "FALLA"
            lineas.append(f"  [{marca}] {r.nombre}: {r.detalle}")
        return "\n".join(lineas)
