-- ================================================================
-- GOLD: campaign_performance
-- Granularidad: campaña + día (docs/decisions/001-granularidad-gold.md)
-- Misma lógica que construir_campaign_performance (src/freshmart/campaigns/gold.py).
--
-- Requisitos (los prepara gold.construir_gold_sql):
--   * vista campaign_ventas -> silver/campaign_ventas/*/*.parquet (hive: columna campana)
-- ================================================================

WITH ventas AS (
    SELECT
        campana,
        CAST(fecha_compra AS DATE)                                      AS fecha,
        venta_id,
        cliente_id,
        producto_id,
        cantidad,
        cliente_anonimo,
        precio * cantidad                                               AS revenue_bruto,
        precio * cantidad * (1 - COALESCE(descuento_pct, 0) / 100.0)    AS revenue_neto
    FROM campaign_ventas
    WHERE cantidad > 0  -- ya filtrado en silver; defensa en profundidad
),

diario AS (
    SELECT
        campana,
        fecha,
        SUM(revenue_bruto)                                  AS revenue_bruto,
        SUM(revenue_neto)                                   AS revenue_neto,
        COUNT(*)                                            AS num_transacciones,
        SUM(cantidad)                                       AS unidades_vendidas,
        -- Los anónimos tienen cliente_id NULL: COUNT(DISTINCT) ya los excluye.
        COUNT(DISTINCT cliente_id)                          AS clientes_unicos,
        COUNT(*) FILTER (WHERE cliente_anonimo)             AS ventas_anonimas,
        COUNT(DISTINCT producto_id)                         AS productos_distintos
    FROM ventas
    GROUP BY campana, fecha
)

SELECT
    campana,
    fecha,
    revenue_bruto,
    revenue_neto,
    num_transacciones,
    unidades_vendidas,
    clientes_unicos,
    ventas_anonimas,
    productos_distintos,
    revenue_neto / NULLIF(num_transacciones, 0)   AS ticket_medio,
    SUM(revenue_neto) OVER por_campana            AS revenue_neto_acumulado,
    SUM(num_transacciones) OVER por_campana       AS transacciones_acumuladas
FROM diario
WINDOW por_campana AS (PARTITION BY campana ORDER BY fecha)
ORDER BY campana, fecha;
