# FreshMart — Online Supermarket Data Engineering Project

**Estado:** En desarrollo 🚧 — el avance detallado está en [`PROGRESO.md`](PROGRESO.md).

## Descripción

**FreshMart** es un proyecto personal de Data Engineering basado en un supermercado online
ficticio. Reproduce la primera semana de un Junior Data Engineer: ingesta de los CSV de
Marketing a un data lake local, segmentación de clientes, limpieza configurable por campaña,
validaciones de calidad, una capa silver en Parquet y una capa gold con las métricas de
campaña para Marketing. El dashboard es el siguiente paso.

> Proyecto con fines educativos y de portfolio. FreshMart es un escenario ficticio y los datos
> se usan como material de práctica.

## Arquitectura

```text
data/*.csv ──► raw/ (originales, inmutables) ──► silver/ (limpio, Parquet) ──► gold/ (agregado)
```

- **raw**: copia exacta de cada CSV en `raw/{fuente}/{tabla}/{AAAA}/{MM}/{DD}/`, con un
  `_manifest.json` (sha256 y fecha de ingesta). Ejecutar la ingesta dos veces no cambia nada.
- **silver**: ventas de campaña limpias y validadas en
  `silver/campaign_ventas/campana=<verano|primavera>/part-0.parquet`, y el catálogo en
  `silver/productos/` y `silver/categorias/`. Si una validación falla, no se escribe nada.
- **gold**: `gold/campaign_performance/` (una fila por campaña y día: revenue bruto y neto,
  transacciones, clientes, ticket medio y acumulados) y `gold/campaign_top_products/` (top 50
  productos por revenue neto en cada campaña). La misma lógica está en pandas y en SQL
  (`sql/gold_*.sql`), y un test exige que coincidan. Por qué esta granularidad:
  [`docs/decisions/001-granularidad-gold.md`](docs/decisions/001-granularidad-gold.md).

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
│   ├── catalog/                 # Silver de productos y categorías
│   ├── campaigns/               # config, clean, validate, pipeline (→ silver), gold, cli
│   └── orders/                  # Extracción diaria de pedidos (la usa el DAG)
├── dags/                        # DAGs de Airflow (sin credenciales)
├── sql/                         # Consultas SQL (DuckDB)
├── scripts/                     # Puntos de entrada de línea de comandos
├── tests/
│   ├── unit/                    # Rápidos, con datos sintéticos
│   └── integration/             # Pipeline completo y CSV reales (se saltan sin data/)
├── docs/                        # Documentación: decisions/ (ADR), incidents/ (postmortems)
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
| Catálogo (productos y categorías) a silver | `python scripts/ejecutar_pipeline.py --catalog --input data --silver-dir freshmart-lake/silver` |
| Campañas a silver y después gold | `python scripts/ejecutar_pipeline.py --all --input data --silver-dir freshmart-lake/silver --gold-dir freshmart-lake/gold` |
| Solo gold (con silver ya construido) | `python scripts/ejecutar_pipeline.py --only-gold --silver-dir freshmart-lake/silver --gold-dir freshmart-lake/gold` |

Orden la primera vez: `--catalog` y luego `--all` con `--gold-dir` (gold necesita el catálogo).

`--campaign` admite `verano` o `primavera`. Con `--all`, cada campaña es independiente: si una
falla la validación, su partición no se toca, las demás se escriben y el código de salida es 1.
En ese caso gold **no** se reconstruye. Las rutas son obligatorias: no hay paths escritos en el
código del pipeline.

Resultado esperado con los datos del caso: verano 42.733 filas y primavera 31.204 (6/6
validaciones cada una); gold con 166 filas en `campaign_performance` y revenue neto de
996.555 € (verano) y 750.622 € (primavera).

### DAG `raw_orders_daily` (Airflow)

`dags/raw_orders_daily.py` extrae cada noche los pedidos del día anterior de PostgreSQL a
`s3://freshmart-lake/raw/orders/orders/AAAA/MM/DD/`. No contiene credenciales: la conexión es la
Airflow Connection `freshmart_orders_ro`, pensada para leerse de AWS Secrets Manager. Los
requisitos de despliegue y cómo relanzar días caídos están en el docstring del DAG. Contexto del
incidente que lo motivó: [`docs/incidents/DATA-162_postmortem.md`](docs/incidents/DATA-162_postmortem.md).

Airflow no es una dependencia del proyecto: la lógica de extracción está en
`freshmart.orders.raw_orders` y se testea sin él, y `tests/unit/test_dags.py` impide que entren
credenciales o SQL formateado en `dags/`.

## Calidad

| Comprobación | Comando | `make` (Linux/macOS/Git Bash) |
|---|---|---|
| Lint + formato + tipos | `ruff check .` · `ruff format --check .` · `mypy` | `make lint` |
| Todos los tests | `pytest` | `make test` |
| Solo unitarios | `pytest -m "not integration"` | `make test-unit` |
| Todo | — | `make check` |

Los hooks de pre-commit ejecutan ruff y mypy antes de cada commit. mypy corre en modo `strict`
sobre `src/`.

## Añadir una campaña

1. Añadir el valor al Enum `Campaign` en `src/freshmart/campaigns/config.py` (el valor es el
   de la columna `campana`/`promocion` del CSV).
2. Añadir su `CampaignConfig`: archivo, mapping de columnas al esquema común, cómo marca a los
   anónimos (`anonimo_valor`), nombre de partición y periodo (`fecha_min`, `fecha_max`).
3. Ejecutar `--campaign <nombre>` y revisar las 6 validaciones; si alguna falla, consultar el
   dato antes de tocar la limpieza.
4. Reconstruir gold con `--only-gold` y pasar `pytest`.

## Problemas conocidos

- Los CSV de Marketing no tienen un formato estándar: cada campaña necesita su mapping.
- Verano trae tres formatos de fecha; se parsean por máscara, nunca con `dayfirst=True`.
- Las ventas anónimas no tienen `cliente_id`: cuentan en revenue, no en clientes.
- El revenue neto no descuenta devoluciones (tardan hasta 14 días en registrarse).
- 12 ventas de verano (311 € brutos) son de productos que no están en `productos.csv`: se
  mantienen en gold sin nombre, pendiente de consultar con Marketing.

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

