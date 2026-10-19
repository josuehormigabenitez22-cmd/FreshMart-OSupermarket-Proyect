"""Guardas sobre dags/ que no necesitan Airflow instalado (DATA-162)."""

import ast
import re
from pathlib import Path

import pytest

DAGS_DIR = Path(__file__).resolve().parents[2] / "dags"
DAGS = sorted(DAGS_DIR.glob("*.py"))

# Patrones que delatan una credencial o una conexión montada a mano.
SOSPECHOSOS = [
    re.compile(r"password\s*=\s*['\"]", re.IGNORECASE),
    re.compile(r"psycopg2\.connect\("),
    re.compile(r"postgres(?:ql)?://[^\s'\"]+:[^\s'\"]+@", re.IGNORECASE),
]


def test_hay_dags() -> None:
    assert DAGS, "no se encontró ningún DAG en dags/"


@pytest.mark.parametrize("dag", DAGS, ids=lambda p: p.name)
def test_dag_compila(dag: Path) -> None:
    ast.parse(dag.read_text(encoding="utf-8"), filename=str(dag))


@pytest.mark.parametrize("dag", DAGS, ids=lambda p: p.name)
def test_dag_sin_credenciales(dag: Path) -> None:
    codigo = dag.read_text(encoding="utf-8")
    encontrados = [p.pattern for p in SOSPECHOSOS if p.search(codigo)]
    assert not encontrados, f"{dag.name} parece contener credenciales: {encontrados}"


@pytest.mark.parametrize("dag", DAGS, ids=lambda p: p.name)
def test_dag_sin_sql_formateado(dag: Path) -> None:
    # Un f-string que contiene SELECT es SQL interpolado (riesgo de inyección).
    arbol = ast.parse(dag.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.JoinedStr):
            texto = "".join(v.value for v in nodo.values if isinstance(v, ast.Constant))
            assert "SELECT" not in texto.upper(), f"{dag.name}: SQL en f-string"


def test_la_guarda_detecta_el_dag_del_curso() -> None:
    # El DAG original del curso tenía exactamente esto: la guarda debe saltar.
    codigo = 'conn = psycopg2.connect(host="x", password="no-real")'
    assert any(p.search(codigo) for p in SOSPECHOSOS)
