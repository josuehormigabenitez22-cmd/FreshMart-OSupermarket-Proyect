# Retrospectiva — Semana 1 en FreshMart

> Borrador basado en lo que pasó de verdad en este repositorio (commits, PRs, bugs y decisiones).
> Para leer en el 1:1 con Elena. Revísalo y añade lo personal: cómo te sentiste, qué te costó
> preguntar.

## Lo que entregué

| Día | Entrega | Estado |
|---|---|---|
| Lun | Exploración + raw inmutable e idempotente (manifest con sha256) | ✅ |
| Mar | Segmentación para Jorge (SQL con 3 CTEs = pandas, verificado con DuckDB) | ✅ |
| Mar | Limpieza configurable para verano y primavera (Enum + `CampaignConfig`) | ✅ |
| Mié | Pipeline raw → silver con 6 validaciones; verano 42.733 filas, primavera 31.204 | ✅ |
| Jue | Diagnóstico de DATA-162, DAG sin credenciales y postmortem | ✅ (sin desplegar) |
| Jue | Gold (166 filas) en pandas y SQL + preview para María | ✅ |
| Vie | 4 cards del dashboard, playbook para Víctor, diccionario de datos, ADRs | ✅ |

## Lo que fue bien

- **No me fié del código del curso con datos reales.** El parseo `format="mixed", dayfirst=True`
  movía 11.126 fechas de verano y la campaña salía de enero a diciembre. Lo detecté, parseo por
  máscara y añadí `fechas_en_rango`, la única validación que lo habría pillado (ADR 004).
- **Cada cifra que fijé en un test la comprobé antes contra `data/`**: 42.733 filas, 166 de
  gold, 996.555 € / 750.622 €, 4.769 / 3.479 clientes nuevos. Todas cuadran con el curso, y
  donde no cuadraban busqué por qué en vez de ajustar el test.
- **Cada cálculo importante existe dos veces y se comparan** (segmentación, gold, card 2): pandas
  contra SQL en DuckDB. Si alguien cambia una definición en un sitio, un test lo avisa.
- **En el incidente, diagnostiqué antes de tocar nada**: el error decía "authentication failed",
  no timeout, así que no era RDS saturado. Presenté opciones con trade-offs y decidió Elena.
- **Comuniqué hallazgos, no solo archivos**: los 6.782 clientes sin pedidos, las 12 ventas de
  productos que no están en el maestro, y los datos raros los dejé como preguntas en las PRs.
- **El repo quedó mejor que como lo encontré**: paquete instalable, mypy strict, pre-commit y
  más de 130 tests.

## Qué mejorar

- **Las PRs se mergearon incompletas dos veces.** La #2 sin sus 2 últimos commits (`main` dejó de
  pasar mypy) y la #5 solo con el commit del DAG, sin la documentación. Desde entonces: push
  primero, revisar la pestaña *Commits* de la PR y mergear después.
- **`docs/` estuvo fuera de Git desde su primer commit sin que nadie lo notara**: un submódulo roto (gitlink sin
  `.gitmodules`) hacía que Git ignorase todo lo de dentro. `git status` no lo mostraba como
  cambio. Lección: revisar en GitHub que lo que creo subido está subido.
- **Restos de copiar y pegar**: archivos `(1)`, un paquete `src/segmentation/` duplicado y un
  `__init__ (1).py` que dejaba `campaigns` funcionando por casualidad. Mejor `git status` antes
  de cada commit que limpieza a posteriori.
- **Interpreté las cifras de segmentación sin preguntar.** Las del curso (2.499 premium…) cuentan
  las 15.247 filas de la campaña; deduplicando salen 2.442. Entregué una versión sin confirmar
  con Jorge cuál quería. Sigue pendiente.
- **Commits demasiado grandes al principio** (un commit con los Pasos 1–4 y mensaje no
  convencional). Después: un commit por cambio lógico.

## Aprendizajes clave

1. **Raw no se toca nunca.** Todo lo demás se puede regenerar desde ahí.
2. **Los datos de negocio vienen sucios, y el código de ejemplo también.** "Funciona con 5 filas"
   no es "funciona".
3. **Un error que no falla es el peor error.** Fechas mal leídas, particiones vacías en verde,
   PRs a medias: hay que diseñar para que fallen en voz alta.
4. **Definir antes de calcular.** "Cliente nuevo", "revenue", "descuento medio": cada uno tenía
   al menos dos lecturas posibles.
5. **Fix rápido + ticket definitivo**, y el fix rápido también tiene coste: la contraseña del
   parche quedó en Git y hay que rotarla otra vez.
6. **Airflow piensa en fechas lógicas**: el run que se ejecuta el día 18 procesa el 17. Para
   recargar días caídos con `catchup=False` se usa Clear, no Trigger.

## Pendiente para la semana que viene

- Confirmar con Jorge qué cifras de segmentación quiere (por fila de campaña o por cliente).
- Preguntar a Marketing por las 12 ventas de productos `90xx` que no están en el catálogo.
- Desplegar DATA-162 y pedir a Infra que rote `data_readonly` de nuevo.
- Automatizar el pipeline de campañas con Airflow (lo pidió Laura en la demo).
- Validador de CSV de entrada y detección de gaps con alerta a Slack (bonus).
