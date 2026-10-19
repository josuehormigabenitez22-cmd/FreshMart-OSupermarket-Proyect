# Postmortem DATA-162 — `raw_orders_daily` sin datos durante ~33 h

| | |
|---|---|
| **Estado** | Mitigado (fix temporal) · fix definitivo en revisión |
| **Severidad** | Media: sin pérdida de datos, dashboards de pedidos desactualizados |
| **Fecha** | 2024-09-18 03:00 UTC → 2024-09-19 ~11:35 |
| **Detectado por** | Alerta de Airflow en `#data-alerts`, revisada en el standup del jueves |
| **Autor** | Josué (diagnóstico) · revisión: Elena Torres |
| **Formato** | Blameless: se analizan procesos y sistemas, no personas |

## Resumen

El DAG `raw_orders_daily`, que copia cada noche los pedidos del día anterior de PostgreSQL
(RDS) a `s3://freshmart-lake/raw/`, falló dos noches seguidas con
`password authentication failed`. Infra había rotado el martes por la noche las credenciales
del usuario `data_readonly`, dentro de su protocolo trimestral, y el DAG tenía la contraseña
antigua escrita en el código. Se aplicó un fix temporal (contraseña nueva en el código), se
relanzaron los dos días caídos y se abrió DATA-162 para leer la conexión de Airflow
Connections / Secrets Manager.

## Impacto

- **Datos**: los pedidos del martes 17 y del miércoles 18 no llegaron a raw hasta el jueves.
  No se perdió ningún dato: el origen (RDS) estaba intacto y se recargaron con Clear.
- **Negocio**: entre el miércoles a las 03:00 y el jueves a las 12:00 los dashboards de
  pedidos de Metabase mostraban datos del lunes. Jorge preguntó si sus cifras del día anterior
  eran correctas: no lo eran hasta la recarga.
- **Duración**: unas 33 h sin datos frescos. El primer fallo (miércoles) pasó desapercibido
  más de un día.

## Cronología

Horas de Airflow en UTC; el resto, hora local.

| Cuándo | Qué |
|---|---|
| Lun 16 | Infra avisa por email al canal de engineering de la rotación trimestral. El equipo de datos no lo recibe o no lo lee. |
| Mar 17, 03:00 UTC | Último run correcto (pedidos del lunes 16). |
| Mar 17, noche | Infra rota las credenciales de los usuarios de solo lectura de RDS. La nueva va a Secrets Manager (`freshmart/prod/rds/data_readonly`). |
| Mié 18, 03:00–03:10 UTC | `extract_orders` falla: `password authentication failed for user "data_readonly"`. Tres reintentos cada 5 min, run FAILED. Nadie actúa. |
| Jue 19, 03:00–03:10 UTC | Mismo fallo (pedidos del miércoles 18). |
| Jue 19, 09:15 | Se ve la alerta en `#data-alerts`. |
| Jue 19, 09:36 | Standup. El dueño del DAG está con otro proyecto y apunta a una posible saturación de RDS. Elena pide **diagnóstico, no fix**. |
| 09:37–10:00 | Lectura del código del DAG y de los logs de los dos runs fallidos. |
| 10:05 | Hipótesis: credenciales cambiadas entre el martes y el miércoles. |
| 10:15 | Pregunta en `#infra`. 10:22: Infra confirma la rotación del martes y dónde está el secreto. |
| 11:22 | Informe a Elena: causa raíz y dos opciones con trade-offs. |
| 11:25 | Elena decide: fix rápido ahora, fix definitivo en un ticket. |
| ~11:30 | Fix temporal mergeado. Clear de los runs fallidos; en ~3 min, ambos en verde. |
| 12:05 | Comunicación en `#data-team`: qué pasó, causa, fix, impacto y siguientes pasos. |

## Diagnóstico

Se siguió la secuencia alerta → entender el sistema → logs → hipótesis → verificación →
opciones, sin tocar nada hasta tener la causa.

1. **Entender el DAG.** Conecta a RDS con `psycopg2.connect(...)` y la contraseña **literal
   en el código**, extrae los pedidos con una query formada con f-string y escribe un CSV en S3.
2. **Logs.** Los dos runs fallan en la conexión, no en la query ni en S3. El error es
   `password authentication failed`, no un timeout ni `connection refused`.
3. **Hipótesis.** Si el servidor responde que la contraseña es incorrecta, el servidor está
   vivo: no es red ni saturación de RDS (la hipótesis inicial). El último run bueno fue el
   martes, así que algo cambió entre el martes y el miércoles en las credenciales.
4. **Verificación.** Infra confirma la rotación del martes por la noche. Hipótesis
   confirmada antes de tocar código.

## Causa raíz y factores contribuyentes

**Causa raíz**: la credencial de RDS estaba escrita en el código del DAG, así que una rotación
rutinaria y anunciada lo rompió.

Factores que lo empeoraron:

- **Aviso que no llegó**: Infra avisó el lunes en un canal que el equipo de datos no sigue.
- **Primer fallo sin respuesta**: la alerta del miércoles existió, pero nadie la atendió hasta
  el jueves. No hay guardia ni responsable de `#data-alerts`.
- **Reintentos inútiles**: un error de autenticación no es transitorio. Los 3 reintentos solo
  retrasaron 10 minutos el fallo definitivo.
- **Sin control de frescura**: nada avisa de que una partición de raw o de gold no tiene datos
  (ver Paso 8, detección de gaps).
- **Deuda conocida**: el dueño del DAG sabía que las credenciales estaban en el código y lo
  tenía en su lista de pendientes.

## Opciones evaluadas

| Opción | Tiempo | A favor | En contra |
|---|---|---|---|
| **1. Fix rápido**: contraseña nueva en el código | 5 min | Restaura el servicio ya | Se repite en la próxima rotación (3 meses). La contraseña nueva queda también en el historial de Git |
| **2. Fix definitivo**: Airflow Connection leída de Secrets Manager | 2–3 h | No vuelve a romperse por rotación. Sin secretos en el repo | Tarda más, con el servicio caído; requiere configurar el secrets backend |

**Decisión (Elena)**: opción 1 ya, porque llevábamos más de un día sin pedidos, y opción 2 en
DATA-162 la semana siguiente.

## Fix aplicado

- **Temporal**: credencial actualizada en el código. PR aprobada por urgencia y mergeada.
- **Recarga**: con `catchup=False`, *Trigger DAG* habría creado un run con la fecha de hoy y
  los dos días seguirían vacíos. Se hizo **Clear** de los dos runs fallidos para relanzarlos
  con su fecha. Por CLI, con fechas lógicas (el run del 18 procesa el día 17):
  `airflow tasks clear raw_orders_daily -s 2024-09-17 -e 2024-09-18 --yes`.
- **Comprobación**: ambos runs en verde y las particiones del 17 y el 18 presentes en raw.

## Fix definitivo (DATA-162)

Implementado en este repo:

- [`dags/raw_orders_daily.py`](../../dags/raw_orders_daily.py): la conexión sale de la Airflow
  Connection `freshmart_orders_ro` (`PostgresHook`). Con el secrets backend de AWS Secrets
  Manager, Airflow la lee del secreto en cada ejecución y una rotación no requiere tocar nada.
- [`src/freshmart/orders/raw_orders.py`](../../src/freshmart/orders/raw_orders.py): la query
  es **parametrizada** (`%(inicio)s`, `%(fin)s`), sin f-string, y usa un intervalo semiabierto
  del `data_interval` del run. Si la extracción sale vacía, el run falla en vez de escribir una
  partición vacía en verde. La escritura reemplaza la partición del día, así que relanzar es
  idempotente.
- [`tests/unit/test_dags.py`](../../tests/unit/test_dags.py): guarda que hace fallar los tests
  si algún DAG de `dags/` contiene `password="..."`, `psycopg2.connect(`, una URL de Postgres
  con usuario y contraseña, o SQL dentro de un f-string.

Pasos de despliegue (fuera de este repo, sin acceso a AWS ni Airflow reales):

1. Configurar el secrets backend `SecretsManagerBackend` en Airflow, o crear la Connection
   `freshmart_orders_ro` a mano como paso intermedio.
2. Desplegar el DAG y el paquete `freshmart-osupermarket` en la imagen de Airflow.
3. Clear de un día ya cargado y comparar con la partición existente.
4. **Pedir a Infra que rote otra vez la contraseña de `data_readonly`**: la del fix temporal
   está en el historial de Git y debe considerarse expuesta.
5. Quitar la credencial del fix temporal del código. Purgar el historial no basta para
   protegerla: por eso hace falta el paso 4.

## Acciones

| Acción | Responsable | Estado |
|---|---|---|
| Migrar `raw_orders_daily` a Connection + Secrets Manager | Josué / Raúl | En revisión (este repo) |
| Rotar de nuevo `data_readonly` tras el despliegue | Infra (Carlos) | Pendiente |
| Revisar los otros 11 DAGs en busca de credenciales; llevarlos a `dags/` para que la guarda de `test_dags.py` los cubra (no hay CI todavía: corre con `pytest` y pre-commit) | Equipo de datos | Pendiente |
| Suscribir al equipo de datos a los avisos de Infra (canal o lista de email) | Elena | Pendiente |
| Responsable rotativo de `#data-alerts` cada mañana | Elena | Pendiente |
| Detección de gaps de datos con alerta a Slack (Paso 8) | Josué | Pendiente |

## Comunicación

Mensaje enviado a `#data-team` a las 12:05, con `cc` a Elena y al dueño del DAG:

> **Qué pasó:** el DAG `raw_orders_daily` falló el miércoles 18 y el jueves 19. Los pedidos no
> se actualizaron durante ~33 horas.
> **Causa raíz:** Infra rotó las credenciales del usuario `data_readonly` de RDS el martes por
> la noche (protocolo trimestral). El DAG tenía la contraseña escrita en el código y seguía
> usando la antigua.
> **Fix aplicado:** credencial actualizada y relanzadas las dos ejecuciones caídas. Los pedidos
> del martes y del miércoles ya están en el lake.
> **Impacto:** entre el miércoles a las 3:00 y hoy a las 12:00, los dashboards de pedidos
> enseñaban datos del lunes. Ya están al día.
> **Próximos pasos:** DATA-162 para migrar la conexión a Airflow Connections / Secrets
> Manager, y revisar si hay más DAGs con credenciales en el código.

## Qué aprendimos

- Un error de autenticación con el servidor respondiendo descarta red y carga: leer bien el
  mensaje de error ahorra horas.
- Diagnosticar antes de actuar: la hipótesis inicial ("RDS saturado") era incorrecta.
- Presentar opciones con trade-offs y dejar decidir al lead.
- Resolver no es suficiente: si no se comunica, otros toman decisiones con datos viejos.
- Un fix temporal que mete un secreto en Git crea otro incidente: hay que planificar su
  retirada (nueva rotación) en el mismo momento en que se aplica.
