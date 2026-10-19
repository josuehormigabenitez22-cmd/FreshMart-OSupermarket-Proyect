# FreshMart — Online Supermarket Data Engineering Project

**Estado:** En desarrollo 🚧 — el avance detallado está en [`PROGRESO.md`](PROGRESO.md).

## Descripción

**FreshMart** es un proyecto personal de Data Engineering basado en un supermercado online
ficticio. Reproduce la primera semana de un Junior Data Engineer: ingesta de los CSV de
Marketing a un data lake local, segmentación de clientes, limpieza configurable por campaña,
validaciones de calidad y una capa silver en Parquet, con la capa gold y el dashboard como
siguientes pasos.

> Proyecto con fines educativos y de portfolio. FreshMart es un escenario ficticio y los datos
> se usan como material de práctica.

## Arquitectura

```text
data/*.csv ──► raw/ (originales, inmutables) ──► silver/ (limpio, Parquet) ──► gold/ (agregado)
```

- **raw**: copia exacta de cada CSV en `raw/{fuente}/{tabla}/{AAAA}/{MM}/{DD}/`, con un
  `_manifest.json` (sha256 y fecha de ingesta). Ejecutar la ingesta dos veces no cambia nada.
- **silver**: ventas de campaña limpias y validadas en
  `silver/campaign_ventas/campana=<verano|primavera>/part-0.parquet`. Si una validación falla,
  no se escribe nada.
- **gold**: pendiente (Paso 6 de `PROGRESO.md`).

## Tecnologías

Python 3.11 · pandas · pyarrow (Parquet) · DuckDB (SQL local) · pytest · ruff · mypy · pre-commit

## Estructura

```text
FreshMart-OSupermarket-Proyect/
├── src/freshmart/
│   ├── settings.py              # Rutas (sobrescribibles por variables de entorno)
│   ├── logging_config.py        # Formato de logs común
│   ├── lake/                    # Ingesta inmutable a raw + manifest
│   ├── exploration/             # Perfilado de CSV → reports/exploracion_campana.json
│   ├── segmentation/            # Segmentación de clientes (pandas, verificada contra SQL)
│   └── campaigns/               # config, clean, validate, pipeline (raw → silver), cli
├── sql/                         # Consultas SQL (DuckDB)
├── scripts/                     # Puntos de entrada de línea de comandos
├── tests/
│   ├── unit/                    # Rápidos, con datos sintéticos
│   └── integration/             # Pipeline completo y CSV reales (se saltan sin data/)
├── docs/                        # Enunciado del curso y documentación
├── reports/                     # Informes generados
├── data/                        # CSV de entrada (no versionados)
└── freshmart-lake/              # Lake local raw/silver/gold (no versionado)
```

## Instalación

Requisitos: Python 3.11+ y Git. Los CSV del caso van en `data/` (no están en el repositorio).

```powershell
git clone <URL_DEL_REPOSITORIO>
cd FreshMart-OSupermarket-Proyect
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
pre-commit install
```

Configuración opcional: copia `.env.example` y exporta las variables que quieras cambiar
(rutas del lake, nivel de log).

## Uso

Con el entorno activado, desde la raíz del repo:

| Tarea | Comando |
|---|---|
| Explorar los CSV de verano | `python scripts/explorar_campana.py` |
| Subir los CSV a raw | `python scripts/subir_a_raw.py` |
| Segmentación (pandas == SQL) | `python scripts/segmentar.py --verify` |
| Pipeline de una campaña a silver | `python scripts/ejecutar_pipeline.py --campaign verano --input data --silver-dir freshmart-lake/silver` |
| Pipeline de todas las campañas | `python scripts/ejecutar_pipeline.py --all --input data --silver-dir freshmart-lake/silver` |

`--campaign` admite `verano` o `primavera`. Con `--all`, cada campaña es independiente: si una
falla la validación, su partición no se toca, las demás se escriben y el código de salida es 1.
Las rutas de entrada y salida son obligatorias: no hay paths escritos en el código del pipeline.

Resultado esperado con los datos del caso: verano 42.733 filas y primavera 31.204, ambas con
6/6 validaciones OK.

## Calidad

| Comprobación | Comando | `make` (Linux/macOS/Git Bash) |
|---|---|---|
| Lint + formato + tipos | `ruff check .` · `ruff format --check .` · `mypy` | `make lint` |
| Todos los tests | `pytest` | `make test` |
| Solo unitarios | `pytest -m "not integration"` | `make test-unit` |
| Todo | — | `make check` |

Los hooks de pre-commit ejecutan ruff y mypy antes de cada commit. mypy corre en modo `strict`
sobre `src/`.

## Roadmap

El plan completo por pasos (raw, segmentación, silver, incidente DATA-162, gold, dashboard,
bonus de calidad) y su estado están en [`PROGRESO.md`](PROGRESO.md).

## Autor

Proyecto personal desarrollado como parte de mi portfolio de Data Engineering y mi proceso de
aprendizaje en arquitectura y procesamiento de datos.

## License

This project is proprietary and all rights are reserved.
Viewing the repository for portfolio evaluation does not
grant permission to reuse, modify, or distribute its contents.

See [LICENSE](LICENSE) for details.

