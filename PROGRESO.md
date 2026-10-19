# PROGRESO — FreshMart, semana 1

> ✅ = hecho y verificado · ❌ = pendiente (o a medias: la línea dice qué falta).
> Se actualiza en el mismo cambio que completa cada tarea.

**Última actualización:** 2026-10-20 — Paso 9 (stretch) hecho en la rama
`feat/inventario-lineas-y-dags`.
Verificado: `pytest` 178 passed · `ruff` OK · `mypy --strict` OK · inventario y líneas con
datos reales · DAGs compilan y pasan la guarda.

## Estado actual

**Curso completo, con bonus y stretch (Pasos 0–9).** Solo quedan tareas que no se pueden
hacer desde este repo (desplegar en Airflow real, el pipeline de Raúl, el flujo de Git del
principio) y las preguntas abiertas a negocio de abajo.

| Paso | Tema | Hecho |
|---|---|---|
| 0 | Fundaciones | 14 / 15 |
| 1 | Día 1 · raw inmutable | 10 / 10 |
| 2 | Día 2 mañana · segmentación | 9 / 9 |
| 3 | Día 2 tarde · limpieza configurable | 10 / 10 |
| 4 | Día 3 · pipeline, validaciones y PR | 14 / 14 |
| 5 | Día 4 mañana · incidente DATA-162 | 8 / 8 |
| 6 | Día 4 tarde · capa gold | 11 / 11 |
| 7 | Día 5 · dashboard y cierre | 6 / 6 |
| 8 | Bonus · calidad y monitorización | 6 / 6 |
| 9 | Stretch · semana siguiente | 4 / 5 |

---

## Siguiente paso (en este orden)

1. **PR del Paso 9** (`feat/inventario-lineas-y-dags`). Comprobar la pestaña Commits antes de
   mergear.
2. **Llevar las preguntas de abajo a negocio.** Sobre todo la conciliación de líneas y
   pedidos: sin ella no se puede construir un gold de ventas fiable con `lineas_pedido`.

## Para preguntar a negocio

- **Jorge**: ¿segmentación por cliente (14.946) o por contacto de campaña (15.247)? Hoy se
  entrega por cliente.
- **Marketing**: 12 ventas de verano (311 €) son de productos `90xx` que no están en el catálogo.
- **Marketing**: el periodo de verano está configurado del 15/06 al 15/09, pero no hay ventas
  el 15/06, el 16/06 ni el 15/09. ¿La campaña empezó el 17/06 o faltan datos?
- **Infra**: rotar otra vez `data_readonly` cuando se despliegue DATA-162.
- **Finanzas / Operaciones**: la suma de las líneas de pedido no cuadra con `total_neto` de
  `pedidos.csv` en 48.480 de 48.520 pedidos. ¿Cuál es la fuente buena?
- **Operaciones**: el stock de un día no cuadra con el del anterior − vendido + recibido (solo
  31 de 8.772 pares). ¿Cómo y cuándo se toma la foto de stock?
- **Operaciones**: 34 fotos de stock negativas y 172 líneas en cuarentena
  (`silver/_cuarentena/`); 375 líneas a 0 € (¿regalos?) y 47 de productos fuera de catálogo.

---

## Paso 0 · Fundaciones

- ✅ `pyproject.toml` con Python ≥ 3.11 y pandas, pyarrow, duckdb, pytest, ruff, mypy.
- ✅ Herramientas de desarrollo en `[project.optional-dependencies] dev` (con `pandas-stubs` y
  `pre-commit`) y `[build-system]`. `pip install -e ".[dev]"` funciona.
- ✅ Configuración de herramientas en `pyproject.toml`: ruff (reglas E/F/I/UP/B), mypy
  `strict` sobre `src/` y pytest (`testpaths`, marcador `integration` puesto automáticamente por
  `tests/integration/conftest.py`).
- ✅ venv con Python 3.11.9 y paquete instalado en editable (`from freshmart...` funciona).
- ✅ `.pre-commit-config.yaml` con ruff-check y ruff-format (v0.17.1, la del venv).
- ✅ mypy en el pre-commit (hook local con el venv). `pre-commit run --all-files` en verde.
- ✅ `Makefile` con `install`, `lint`, `format`, `test`, `check`.
- ✅ Objetivos `setup`, `test-unit`, `raw`, `segment` y `pipeline` en el `Makefile`; los comandos
  equivalentes para Windows están en el README. (El `Makefile` no se ha podido ejecutar: no hay
  `make` en esta máquina.)
- ✅ `.gitignore` deja fuera `data/`, `freshmart-lake/` (raw, silver, gold) y el egg-info.
- ✅ Licencia coherente: README y LICENSE dicen propietaria.
- ✅ `.env.example` documenta `FRESHMART_*_DIR`, `FRESHMART_LOG_LEVEL` y `SLACK_WEBHOOK_URL`
  sin valores reales.
- ✅ `settings.py` acepta rutas por variables de entorno y `logging_config.py` centraliza el
  formato de logs (lo usa la CLI del pipeline).
- ✅ README al día: arquitectura, estructura real, instalación con `pip install -e ".[dev]"`,
  comandos y calidad.
- ✅ `ruff check`, `ruff format --check`, `mypy` (strict) y `pytest` en verde.
- ❌ Flujo Git del curso: ramas `feat/DATA-147-...`, commits convencionales y una PR por paso
  (el commit `11e171e` mezcla los Pasos 1–4 y no es convencional; desde aquí, una PR por paso).

## Paso 1 · Día 1: raw inmutable

- ✅ `explorar_campana.py` refactorizado a `src/freshmart/exploration/profiler.py` con `main()` y CLI.
- ✅ `subir_a_raw.py` refactorizado a `src/freshmart/lake/raw_upload.py` con `main()` y CLI
  (`--input`, `--output`, `--date`).
- ✅ Convención `raw/{fuente}/{tabla}/{AAAA}/{MM}/{DD}` en `lake/paths.py`.
- ✅ Idempotente: no sobrescribe un original existente y no reescribe el manifest si no cambia.
- ✅ `_manifest.json` con sha256 y fecha de ingesta.
- ✅ Subidos verano (3 archivos), primavera, clientes y pedidos.
- ✅ Test de idempotencia con `tmp_path`.
- ✅ `_manifest.json` sin rutas absolutas: `cargar_manifest` descarta los registros antiguos
  (también rutas de Windows cuando se ejecuta en Linux). El manifest local pasó de 11 registros a
  8, y la segunda ejecución no cambia nada.
- ✅ Subidos también `productos.csv` y `categorias.csv` (los necesita la capa gold).
- ✅ `logging` en vez de `print`. Si el CSV de origen cambió respecto a lo subido, avisa y **no**
  sobrescribe: indica que se suba con otra fecha de ingesta (`--date`).

## Paso 2 · Día 2 mañana: segmentación para Jorge

- ✅ `sql/segmentacion_campana.sql` con 3 CTEs, ejecutado con DuckDB.
- ✅ `segmentation/segment.py` con la misma lógica en pandas.
- ✅ `verificar()` comprueba que pandas y SQL dan exactamente lo mismo (`assert_frame_equal`).
- ✅ Clientes deduplicados antes de un LEFT JOIN.
- ✅ `fecha_pedido` en dos pasadas (ISO y luego `dd/mm/aaaa HH:MM`).
- ✅ `codigo_postal` leído como `str` y con `zfill(5)`.
- ✅ Tests unitarios con `tmp_path` y test con datos reales.
- ✅ La base del cruce es la lista de la campaña (`campana_verano_clientes.csv`), con una fila
  por cliente, y LEFT JOIN a la maestra y a los pedidos, en pandas y en SQL. Un test cubre un
  cliente de la maestra que no recibió la campaña y otro de la campaña sin ficha.
- ✅ Comentario del test corregido. Hay dos tests con datos reales: por cliente (14.946 →
  2.442 / 1.938 / 10.566) y por contacto, que reproduce las cifras del curso (15.247 filas →
  2.499 / 1.975 / 10.773, 6.782 sin pedidos, 349 desde junio). Se entrega por cliente; queda
  confirmarlo con Jorge (ver retrospectiva).

## Paso 3 · Día 2 tarde: limpieza configurable

- ✅ `Campaign` como `StrEnum` en `campaigns/config.py`.
- ✅ Mappings de columnas por campaña (`CampaignConfig.columnas`).
- ✅ `anonimo_valor`: `None` en verano, `-1` en primavera.
- ✅ `clean.py`: una función pura por problema, tipada y con logging.
- ✅ Fechas parseadas por máscara con `format=` explícito (rango verano 2024-06-17 → 2024-09-14).
- ✅ Precio por regex (`"0,8€"` válido, miles rechazados).
- ✅ Ids como `Int64` (acepta `105049.0`, rechaza `1.5`).
- ✅ Tests con caso feliz y caso límite por función.
- ✅ Primavera limpia con datos reales: 31.204 filas, 78 anónimos.
- ✅ Nombre de la marca de anónimo decidido y documentado en `docs/data_dictionary.md`:
  `cliente_anonimo` en silver y `ventas_anonimas` en gold (el curso usa `es_anonimo`).

## Paso 4 · Día 3: pipeline, validaciones y PR

- ✅ `validate.py`: lo primero es `no_vacio`; si falla, el resto no se ejecuta.
- ✅ Sin paths en el código: `--input` y `--silver-dir` obligatorios por CLI.
- ✅ Campañas con el Enum en todo el flujo.
- ✅ Fechas inválidas con `errors="coerce"` y contadas.
- ✅ `pipeline.py`: si falla una validación no se escribe nada (y no se estropea una partición previa).
- ✅ Silver en Parquet particionado `silver/campaign_ventas/campana=verano/`, escritura atómica.
- ✅ Tests de integración de extremo a extremo con CSV pequeños.
- ✅ Verano con datos reales: **42.733 filas, 6/6 validaciones OK** (el curso pide 5/5; aquí
  hay una más).
- ✅ `validar_fechas_en_rango` con el periodo de cada campaña en `CampaignConfig`. Un test de
  regresión con datos reales demuestra que el parseo del curso (`format="mixed", dayfirst=True`)
  solo lo detecta esta validación.
- ✅ Silver de primavera en `freshmart-lake/silver/` (31.204 filas, 6/6). Silver total 73.937.
- ✅ Restos limpiados: `campaigns/__init__.py` real, `src/segmentation/` eliminado y tests
  `(1)` fusionados.
- ✅ `campaigns/cli.py` con `--campaign` o `--all` (excluyentes), `--input` y `--silver-dir`.
  Con `--all` una campaña fallida no bloquea a las demás y la salida es 1. `pipeline.py` queda
  como librería. `--only-gold` y `--gold-dir` pasan al Paso 6, junto con `gold.py`.
- ✅ PR #2 abierta con descripción (qué, cómo probar, decisiones, contexto) y mergeada a `main`.
- ✅ PR de seguimiento #4: entran en `main` la CLI, el tipado, las rutas/logging y el README.

## Paso 5 · Día 4 mañana: incidente DATA-162

- ✅ `dags/raw_orders_daily.py` con la conexión desde la Airflow Connection
  `freshmart_orders_ro` (`PostgresHook`), pensada para el secrets backend de Secrets Manager.
  Ninguna contraseña en el repo.
- ✅ Query parametrizada (`%(inicio)s`/`%(fin)s` sobre el `data_interval`), sin f-string SQL.
  Escritura idempotente por día y fallo explícito si la extracción sale vacía
  (`src/freshmart/orders/raw_orders.py`, testeable sin Airflow).
- ✅ El DAG compila (`py_compile`) y documenta cómo relanzar los días caídos: Clear y no
  Trigger con `catchup=False`, usando fechas lógicas (el run del 18 procesa el 17).
- ✅ Guarda en `tests/unit/test_dags.py`: falla si un DAG contiene `password="..."`,
  `psycopg2.connect(`, una URL con credenciales o SQL dentro de un f-string.
- ✅ `docs/incidents/DATA-162_postmortem.md`: cronología, diagnóstico (alerta → logs →
  hipótesis → verificación), causa raíz y factores, opciones con trade-offs, fix, comunicación
  y acciones. Incluye que la contraseña del fix temporal quedó en Git y hay que rotarla de nuevo.
- ✅ Ticket DATA-162 descrito (fix definitivo, despliegue y revisión de los demás DAGs) en el
  postmortem. No se ha ejecutado contra Airflow ni AWS reales: el entregable es código y documento.
- ✅ README: `dags/` y `orders/` en la estructura y una sección del DAG `raw_orders_daily`.
- ✅ `docs/` versionable: estaba registrado como submódulo roto (gitlink sin `.gitmodules`
  desde `b1542ef`), así que Git ignoraba todo lo de dentro. Se quita el gitlink y se versionan
  `Bienvenido.md` y el postmortem. El enunciado del curso (`FreshmarketProyect.txt`) queda en
  `.gitignore` por ser material de terceros.

## Paso 6 · Día 4 tarde: capa gold

- ✅ Silver de `productos` y `categorias` (`catalog/silver.py`): ids `Int64` (`"22.0"` → 22),
  booleanos normalizados (`no/false/FALSE/0` y `sí/true/TRUE/1`), validación de ids únicos y
  de categorías existentes. 1.847 productos y 89 categorías.
- ✅ `campaigns/gold.py` → `campaign_performance` (campaña + día) con `assign` +
  `groupby(...).agg(...)` con named aggregation (sin el `lambda df.loc` del curso).
- ✅ `campaign_top_products` (campaña + producto, ranking tipo ROW_NUMBER por revenue neto con
  desempate por id, top 50, con nombre, marca y categoría por LEFT JOIN).
- ✅ Gold escrito en `freshmart-lake/gold/` en Parquet (escritura atómica compartida en
  `lake/parquet.py`).
- ✅ `cli.py`: `--catalog`, `--only-gold` y `--gold-dir`. Gold no se reconstruye si falla una
  campaña.
- ✅ `sql/gold_campaign_performance.sql` y `sql/gold_campaign_top_products.sql` ejecutados con
  DuckDB, y `verificar_gold` exige pandas == SQL (con datos sintéticos y reales).
- ✅ Tests con cifras verificadas: 166 filas (90 + 76); neto 996.555 € / 750.622 €; bruto
  1.048.754 € / 790.729 €; ticket 23,32 € / 24,06 €; top 1 Häagen-Dazs y Protos.
- ✅ ADR de granularidad (`docs/decisions/001-granularidad-gold.md`).
- ✅ Definición de "cliente nuevo" acordada con María (diálogo del curso, jueves 15:18): las dos,
  y la principal es primera compra. `clientes_nuevos_por_campana` → 4.769 / 3.479 (registro:
  667 / 840).
- ✅ `docs/preview_maria.md`: dato, comparación y "so what" (revenue, clientes nuevos, top 5).
- ✅ README actualizado: gold, comandos, cómo añadir una campaña y problemas conocidos.

## Paso 7 · Día 5: dashboard y cierre

- ✅ `sql/dashboard_cards.sql` con las 4 cards (revenue, clientes nuevos, top 10, evolución
  diaria), una query por `-- name:`, ejecutadas con DuckDB por `freshmart/dashboard/cards.py`
  (`python scripts/dashboard.py`). La card 4 añade `dia_de_campana` para poder superponer
  campañas que no coinciden en el calendario.
- ✅ Card de clientes nuevos con primera compra sobre **todo** el historial de pedidos: en SQL da
  4.769 / 3.479, igual que `gold.clientes_nuevos_por_campana`. Un test comprueba que sus
  periodos coinciden con `CampaignConfig`.
- ✅ `docs/playbook_nueva_campana.md` para Víctor: 6 pasos con ejemplo (`otoño`), qué hacer si
  falla cada validación y la nota sobre escalarlo a otros equipos.
- ✅ `docs/data_dictionary.md`: todas las tablas silver y gold, definiciones de métricas y qué
  columnas se pueden sumar entre días.
- ✅ ADRs 002 (Parquet particionado), 003 (Enum de campañas) y 004 (fechas por máscara, con las
  cifras verificadas: 11.126 fechas desplazadas).
- ✅ `docs/retrospectiva_semana1.md`, basada en lo que pasó en el repo (borrador: falta añadir lo
  personal).

## Paso 8 · Bonus

- ✅ `quality/csv_validator.py` (estructura, tipos, nulos críticos, umbral, duplicados), con
  `validar_csv_campana` que saca el esquema de `CampaignConfig` y `scripts/validar_csv.py`
  (salida 1 si hay errores). Las fechas se comprueban con las máscaras de la limpieza.
- ✅ Una sola clase: `quality/result.py` (`ResultadoValidacion` con severidad ERROR/AVISO +
  `InformeCalidad`). La usan el pipeline (`InformeValidacion` hereda de ella), el catálogo y el
  validador. La `ValidationResult` del bonus no se crea.
- ✅ Tests del validador con CSV pequeños y con los reales: verano válido con 2 avisos (3
  formatos 30.157 / 10.646 / 2.088 y 155 duplicados), primavera 10/10.
- ✅ `sql/monitoring_gaps.sql` + `quality/gap_detection.py` con campaña y ventana como
  parámetros (sin `CURRENT_DATE`). Datos reales: 0 huecos internos. Con el periodo configurado
  de verano salen 15/06, 16/06 y 15/09 sin ventas (ver "Para preguntar").
- ✅ `quality/slack_alerts.py` con el webhook en `SLACK_WEBHOOK_URL` y el envío inyectado
  (los tests nunca llaman a Slack). Sin webhook y con gaps, falla en voz alta.
- ✅ Sin gaps no se envía alerta (test).

## Paso 9 · Stretch (semana siguiente)

- ✅ DAG `campaign_pipeline_weekly` (lunes 06:00): validar CSV → silver por campaña + catálogo
  → gold → gaps con alerta a Slack. Gold solo si todo lo anterior va bien. Lógica en
  `freshmart/orchestration/tasks.py`, testeada sin Airflow; rutas desde Variables de Airflow.
- ✅ Fix de DATA-162 en todos los DAGs del repo: los 3 (`raw_orders_daily`,
  `campaign_pipeline_weekly`, `operations_daily`) sin credenciales ni SQL formateado, vigilados
  por `tests/unit/test_dags.py`. No desplegado: no hay Airflow real.
- ✅ Ingesta y limpieza de `inventario_diario.csv` y `lineas_pedido.csv`: raw con su fuente
  (`inventory/`, `orders/`), silver con cuarentena (ADR 005) y gold `inventario_tienda_dia`.
  Datos reales: inventario 17.525 filas + 34 en cuarentena; líneas 142.204 + 172 en cuarentena.
- ✅ Inventario dentro del mismo esquema que las campañas: misma limpieza, el mismo
  `InformeCalidad`, Parquet atómico, CLI y DAG `operations_daily`.
- ❌ Pair programming con Raúl para migrar su pipeline de inventario a este esquema: su código
  no está en este repo.

---

## Cifras de referencia verificadas

Comprobadas con `data/` el 2026-10-19; los tests de `tests/integration/` las fijan:

| Métrica | Valor |
|---|---|
| Verano limpio | 42.733 filas (155 duplicados, 3 cantidad = 0), 2024-06-17 → 2024-09-14, 90 días |
| Primavera limpio | 31.204 filas, 78 anónimos, 2024-03-15 → 2024-05-29, 76 días |
| Gold campaña + día | 166 filas |
| Revenue neto | verano 996.555 € · primavera 750.622 € |
| Revenue bruto | verano 1.048.754 € · primavera 790.729 € |
| Ticket medio | verano 23,32 € · primavera 24,06 € |
| Clientes nuevos (1.ª compra) | verano 4.769 · primavera 3.479 |
| Registros nuevos | verano 667 · primavera 840 |
| Segmentación (15.247 filas campaña) | 2.499 / 1.975 / 10.773 · 6.782 sin pedidos · 349 desde junio |
| Segmentación (14.946 únicos) | 2.442 / 1.938 / 10.566 · 6.661 sin pedidos · 345 desde junio |
