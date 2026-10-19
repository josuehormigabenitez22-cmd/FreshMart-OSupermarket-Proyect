# ADR 001: Granularidad de la capa gold de campañas

- **Estado:** aceptada
- **Fecha:** 2024-09-19
- **Contexto de negocio:** María (Marketing) presenta verano vs primavera a dirección el viernes.

## Contexto

María necesita: revenue bruto y neto por campaña, clientes únicos, clientes nuevos, ticket
medio, top 10 productos por campaña y la evolución diaria del revenue para un gráfico de
líneas. Silver tiene una fila por transacción (73.937 filas). Antes de escribir SQL hay que
decidir qué representa cada fila de gold.

## Opciones

| Granularidad | Filas | Valoración |
|---|---|---|
| Campaña | 2 | Demasiado agregada: no permite ver la evolución diaria ni el pico. |
| **Campaña + día** | **166** (90 + 76) | Responde a todo salvo el top de productos. Es el nivel al que se mira un dashboard. |
| Campaña + día + producto | miles | Demasiado detalle para un dashboard. Si hace falta, se consulta silver. |
| Transacción | 73.937 | Eso ya es silver. |

## Decisión

1. **`gold/campaign_performance`**: una fila por **campaña y día**, con revenue bruto y neto,
   transacciones, unidades, clientes únicos, ventas anónimas, productos distintos, ticket
   medio y acumulados (revenue neto y transacciones) para los gráficos de evolución.
2. **`gold/campaign_top_products`**: tabla auxiliar a granularidad **campaña + producto** con
   el **top 50** por campaña (María pide 10: el margen evita reconstruir si pide más).
3. El ranking es por **revenue neto**, desempatando por `producto_id` para que sea
   determinista (equivale a `ROW_NUMBER()`). El SQL del curso ordena por bruto: en los datos
   reales el top 5 es el mismo, pero el neto es la cifra que se presenta a negocio.
4. Se agrega por `producto_id` y se enriquece con nombre, marca y categoría **después**, con
   LEFT JOIN. Así un producto vendido que no está en el maestro no desaparece del total (hay
   12 ventas así en verano) y dos productos con el mismo nombre no se mezclan.

## Consecuencias

- Agregar de día a campaña es trivial (`SUM`), pero **no se pueden sumar `clientes_unicos`
  de varios días**: un cliente que compra dos días contaría dos veces. Los clientes únicos por
  campaña se calculan sobre silver, no sumando gold.
- Lo mismo para `ticket_medio`: el de la campaña es `SUM(revenue_neto) / SUM(num_transacciones)`,
  no la media de los tickets diarios.
- "Clientes nuevos" no cabe en esta granularidad: se calcula sobre el historial completo de
  pedidos (`gold.clientes_nuevos_por_campana` y la card 2 del dashboard).
- La lógica existe en pandas (`campaigns/gold.py`) y en SQL (`sql/gold_*.sql`). Un test exige
  que den lo mismo, así que cualquier cambio de definición se hace en los dos sitios.
