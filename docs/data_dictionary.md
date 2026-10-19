# Diccionario de datos — lake de campañas

Tablas del lake local (`freshmart-lake/`). En producción el mismo layout vive en
`s3://freshmart-lake/`. Las cifras de filas son las de los datos del caso (septiembre 2024).

| Capa | Tabla | Granularidad | Filas | Escribe |
|---|---|---|---|---|
| raw | `raw/marketing/<tabla>/2024/09/16/*.csv` | archivo original | — | `lake/raw_upload.py` |
| raw | `raw/orders/orders/AAAA/MM/DD/orders.csv` | pedidos de un día | — | DAG `raw_orders_daily` |
| silver | `campaign_ventas` | una venta | 73.937 | `campaigns/pipeline.py` |
| silver | `productos` | un producto | 1.847 | `catalog/silver.py` |
| silver | `categorias` | una categoría | 89 | `catalog/silver.py` |
| raw | `raw/inventory/inventario_diario/…`, `raw/orders/lineas_pedido/…` | archivo original | — | `lake/raw_upload.py` |
| silver | `inventario_diario` | producto + tienda + día | 17.525 | `inventory/silver.py` |
| silver | `lineas_pedido` | una línea de pedido | 142.204 | `orders/lineas.py` |
| silver | `_cuarentena/<tabla>` | fila apartada + motivo | 34 / 172 | `quality/cuarentena.py` |
| gold | `campaign_performance` | campaña + día | 166 | `campaigns/gold.py` |
| gold | `campaign_top_products` | campaña + producto (top 50) | 100 | `campaigns/gold.py` |
| gold | `inventario_tienda_dia` | tienda + día | 10 | `inventory/gold.py` |

Convenciones:

- Parquet, un `part-0.parquet` por tabla o partición, escrito de forma atómica.
- Ids enteros con nulos permitidos (`Int64` en pandas, `int64` en Parquet).
- Fechas sin zona horaria. Las de compra no traen hora: valen las 00:00.
- Importes en euros, sin redondear (el redondeo es cosa de la visualización).

---

## silver.campaign_ventas

Ventas de las campañas de Marketing, limpias y validadas. Particionada por campaña
(`campana=verano/`, `campana=primavera/`). Origen: `campana_<campaña>_ventas.csv`, con un mapping
de columnas por campaña (`campaigns/config.py`).

| Columna | Tipo | Nulos | Descripción |
|---|---|---|---|
| `venta_id` | int64 | no | Id de la venta. Único (validación `venta_id_unico`). En primavera viene como `id_transaccion`. |
| `cliente_id` | int64 | sí (925) | Cliente. **Nulo = venta anónima** (guest checkout). Verano los trae vacíos; primavera usa `-1`, que se convierte a nulo. Llega como `105049.0`. |
| `producto_id` | int64 | no | Producto. 12 ventas de verano tienen ids que no están en `productos`. |
| `fecha_compra` | timestamp | no | Día de la compra. Verano mezcla ISO, `dd/mm/aaaa` y `Mon d, aaaa`; se parsea por máscara. Dentro del periodo de la campaña (validación `fechas_en_rango`). |
| `cantidad` | int64 | no | Unidades, ≥ 1. Se descartan las filas con 0 (3 en verano: error de la app). |
| `precio` | double | no | Precio unitario en € (> 0). En verano llega como texto `"9,89€"`. |
| `descuento_pct` | double | no | Descuento de la línea, 0–100. |
| `tienda_id` | int64 | no | Almacén que sirve el pedido (`almacen` en primavera). |
| `cliente_anonimo` | bool | no | `true` si `cliente_id` es nulo. Se **marca**, no se elimina: son ventas reales. |
| `campana` | string | no | Partición: `verano` o `primavera`. No está dentro del Parquet; la aporta el directorio. |

> **Nombre de la marca de anónimo.** El curso la llama `es_anonimo`. Aquí se usa
> `cliente_anonimo` en silver y su agregado en gold se llama `ventas_anonimas`. Una sola
> palabra para todo el lake; si se renombra, hay que cambiar silver, gold, SQL y tests a la vez.

## silver.productos

Maestro de productos. Origen: `productos.csv`.

| Columna | Tipo | Nulos | Descripción |
|---|---|---|---|
| `producto_id` | int64 | no | Id único. |
| `nombre` | string | no | Nombre comercial. |
| `marca` | string | no | Marca. |
| `categoria_id` | int64 | sí (23) | Categoría (hoja del árbol). Llega como `"22.0"`. Si no es nula, existe en `categorias`. |
| `precio_base` | double | no | Precio de catálogo en €. **No** es el precio de venta de la campaña. |
| `peso_kg` | double | no | Peso. |
| `es_perecedero` | bool | no | Normalizado desde `no/false/FALSE/0/False` y `sí/true/TRUE/1/True`. |
| `dias_caducidad` | int64 | sí | Vida útil; nulo en los no perecederos. |
| `activo` | bool | no | Producto activo en catálogo. |
| `fecha_alta` | timestamp | no | Alta en el catálogo. |

## silver.categorias

Árbol de categorías (3 niveles). Origen: `categorias.csv`.

| Columna | Tipo | Nulos | Descripción |
|---|---|---|---|
| `categoria_id` | int64 | no | Id único. |
| `nombre` | string | no | Nombre (`Helados`, `Cerveza y vino`…). |
| `padre_id` | int64 | sí (8) | Categoría padre; nulo en las 8 de nivel 1. |
| `nivel` | int64 | no | 1, 2 o 3. |

---

## gold.campaign_performance

Una fila por **campaña y día con ventas** (verano 90, primavera 76). Alimenta las cards 1 y 4.
Por qué esta granularidad: [ADR 001](decisions/001-granularidad-gold.md).

| Columna | Tipo | Definición | ¿Se puede sumar entre días? |
|---|---|---|---|
| `campana` | string | `verano` / `primavera` | — |
| `fecha` | timestamp | Día | — |
| `revenue_bruto` | double | Σ precio × cantidad | Sí |
| `revenue_neto` | double | Σ precio × cantidad × (1 − descuento_pct/100). Después de descuentos, **antes de devoluciones**. | Sí |
| `num_transacciones` | int64 | Número de ventas (líneas de silver), anónimas incluidas | Sí |
| `unidades_vendidas` | int64 | Σ cantidad | Sí |
| `clientes_unicos` | int64 | Clientes distintos del día, **sin anónimos** | **No**: un cliente que compra dos días contaría dos veces |
| `ventas_anonimas` | int64 | Ventas sin cliente | Sí |
| `productos_distintos` | int64 | Productos distintos vendidos ese día | **No** |
| `ticket_medio` | double | revenue_neto / num_transacciones | **No**: el de la campaña es Σ neto / Σ transacciones |
| `revenue_neto_acumulado` | double | Revenue neto acumulado desde el inicio de la campaña | No (ya es acumulado) |
| `transacciones_acumuladas` | int64 | Transacciones acumuladas desde el inicio de la campaña | No |

Totales de referencia: neto 996.555 € (verano) y 750.622 € (primavera); ticket medio 23,32 € y
24,06 €.

## gold.campaign_top_products

Top 50 productos por **revenue neto** en cada campaña (empates: menor `producto_id`). Alimenta la
card 3 (top 10).

| Columna | Tipo | Definición |
|---|---|---|
| `campana` | string | `verano` / `primavera` |
| `ranking` | int64 | 1 = más revenue neto (equivale a `ROW_NUMBER()`) |
| `producto_id` | int64 | Producto |
| `producto_nombre`, `marca`, `categoria` | string | Del catálogo (LEFT JOIN). Nulos si el producto no está en el maestro. |
| `revenue_bruto`, `revenue_neto` | double | Como en `campaign_performance`, para ese producto y campaña |
| `unidades_vendidas` | int64 | Σ cantidad |
| `compradores_unicos` | int64 | Clientes distintos que lo compraron, sin anónimos |
| `num_transacciones` | int64 | Ventas del producto |

---

## silver.inventario_diario

Foto diaria del stock por producto y tienda. Particionada por día (`fecha=AAAA-MM-DD/`). Origen:
`inventario_diario.csv`. Se eliminan 911 duplicados exactos (el mismo batch dos veces) y van a
cuarentena las filas imposibles (34 con stock negativo). Clave única: producto + tienda + fecha.
Que un producto no aparezca en una tienda **no** es un error: es el surtido de esa tienda.

| Columna | Tipo | Descripción |
|---|---|---|
| `producto_id`, `tienda_id` | int64 | Producto (existe en `productos`) y tienda (1–5) |
| `stock_actual` | int64 | Unidades en stock al cierre del día; ≥ 0 |
| `stock_minimo` | int64 | Punto de pedido |
| `stock_seguridad` | int64 | Colchón mínimo; ≤ `stock_minimo` |
| `unidades_vendidas`, `unidades_recibidas` | int64 | Movimientos del día |
| `sin_stock` | bool | `stock_actual = 0` |
| `bajo_seguridad` | bool | `stock_actual < stock_seguridad`: riesgo de rotura |
| `bajo_minimo` | bool | `stock_actual < stock_minimo`: toca reponer |
| `fecha` | string | Partición (día de la foto) |

> El stock de un día **no** cuadra con el del anterior menos lo vendido más lo recibido (solo
> 31 de 8.772 pares). No se valida hasta aclarar con Operaciones cómo se toma la foto.

## silver.lineas_pedido

Una fila por línea de pedido. Origen: `lineas_pedido.csv`. 172 líneas en cuarentena
(precio negativo, cantidad 0 o total que no cuadra).

| Columna | Tipo | Descripción |
|---|---|---|
| `linea_id` | int64 | Id único de la línea |
| `pedido_id` | int64 | Pedido (todos existen en `pedidos.csv`) |
| `producto_id` | int64 | Producto; 47 líneas son de productos que no están en el catálogo |
| `cantidad` | int64 | Unidades, ≥ 1 |
| `precio_unitario` | double | € por unidad, ≥ 0. 375 líneas a 0 €: pendiente de confirmar si son regalos o promociones |
| `descuento_pct` | double | 0–100 |
| `total_linea` | double | cantidad × precio × (1 − descuento/100), redondeado a céntimos (validado ±0,01 €) |

> La suma de `total_linea` **no** cuadra con `pedidos.total_neto` en 48.480 de 48.520 pedidos.
> No se construye nada encima hasta saber cuál es la fuente buena.

## silver._cuarentena/&lt;tabla&gt;

Filas apartadas por imposibles, con las mismas columnas que la tabla de origen más
`motivo_cuarentena` (reglas separadas por `;`, p. ej. `cantidad_no_positiva;total_inconsistente`).
Se reescribe en cada carga. Es una lista de preguntas para negocio, no una papelera
(ver [ADR 005](decisions/005-cuarentena.md)).

## gold.inventario_tienda_dia

Salud del stock por **tienda y día** para Operaciones.

| Columna | Tipo | Definición |
|---|---|---|
| `tienda_id`, `fecha` | int64, timestamp | Tienda y día |
| `productos` | int64 | Productos con foto de stock ese día |
| `sin_stock`, `bajo_seguridad`, `bajo_minimo` | int64 | Productos en cada situación |
| `stock_total` | int64 | Σ unidades en stock |
| `unidades_vendidas`, `unidades_recibidas` | int64 | Σ movimientos del día |
| `pct_bajo_seguridad` | double | bajo_seguridad / productos (3,7 %–4,9 % en los datos del caso) |

---

## Métricas que no están en una tabla

| Métrica | Definición | Dónde |
|---|---|---|
| **Cliente nuevo (primera compra)** | Cliente cuya primera compra de **todo el historial** de `pedidos` (cualquier estado) cae en el periodo de la campaña. Verano 4.769, primavera 3.479. | `gold.clientes_nuevos_por_campana`, card 2 |
| Cliente nuevo (registro) | Cliente (deduplicado) con `fecha_registro` en el periodo. Verano 667, primavera 840. | `gold.clientes_nuevos_por_campana` |
| Segmento (premium / regular / nuevo) | Pedidos no cancelados en los 3 meses anteriores al 16/09/2024: > 6, 2–6, 0–1. | `segmentation/segment.py`, `sql/segmentacion_campana.sql` |

Periodos de campaña: verano 15/06–15/09/2024 y primavera 01/03–31/05/2024
(`CampaignConfig.fecha_min` / `fecha_max`).
