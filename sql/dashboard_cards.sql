-- ================================================================
-- Dashboard "Campañas 2024" (Metabase) — 4 cards para la demo con dirección
--
-- Cada bloque "-- name: <card>" es una pregunta SQL independiente en Metabase.
-- En local las ejecuta freshmart.dashboard.cards con DuckDB, que prepara:
--   * gold.campaign_performance, gold.campaign_top_products (Parquet de gold)
--   * pedidos (historial completo de pedidos, con fecha_pedido ya como TIMESTAMP)
-- El SQL es estándar: funciona igual en PostgreSQL/Redshift.
-- ================================================================


-- name: card_1_revenue
-- ¿Qué campaña funcionó mejor? (bar chart: bruto vs neto por campaña)
-- Ticket medio = suma de revenue / suma de transacciones, NO la media de los diarios.
SELECT
    campana,
    SUM(revenue_bruto)                                          AS revenue_bruto_total,
    SUM(revenue_neto)                                           AS revenue_neto_total,
    SUM(num_transacciones)                                      AS transacciones,
    SUM(revenue_neto) / NULLIF(SUM(num_transacciones), 0)      AS ticket_medio
FROM gold.campaign_performance
GROUP BY campana
ORDER BY revenue_neto_total DESC;


-- name: card_2_clientes_nuevos
-- ¿Estamos captando clientes nuevos? (número grande por campaña)
-- Cliente nuevo = su PRIMERA compra de todo el historial cae en el periodo de la campaña.
-- OJO: la primera compra se busca en todo el historial de pedidos, no solo en la campaña;
-- si no, cualquier comprador saldría como "nuevo".
WITH primera_compra AS (
    SELECT
        cliente_id,
        CAST(MIN(fecha_pedido) AS DATE) AS fecha_primera_compra
    FROM pedidos
    WHERE cliente_id IS NOT NULL
    GROUP BY cliente_id
),

periodos (campana, inicio, fin) AS (
    -- Mismos periodos que CampaignConfig (src/freshmart/campaigns/config.py)
    VALUES
        ('verano',    DATE '2024-06-15', DATE '2024-09-15'),
        ('primavera', DATE '2024-03-01', DATE '2024-05-31')
)

SELECT
    p.campana,
    COUNT(pc.cliente_id) AS clientes_nuevos
FROM periodos AS p
LEFT JOIN primera_compra AS pc
    ON pc.fecha_primera_compra BETWEEN p.inicio AND p.fin
GROUP BY p.campana
ORDER BY clientes_nuevos DESC;


-- name: card_3_top_10_productos
-- ¿Qué productos impulsar? (tabla)
SELECT
    campana,
    ranking,
    producto_nombre,
    categoria,
    revenue_neto,
    unidades_vendidas
FROM gold.campaign_top_products
WHERE ranking <= 10
ORDER BY campana, ranking;


-- name: card_4_evolucion_diaria
-- ¿Cómo evolucionó cada campaña? (line chart, ambas campañas superpuestas)
-- Las campañas no coinciden en el calendario: para superponerlas, el eje X es
-- dia_de_campana (1 = primer día con ventas), no la fecha.
SELECT
    campana,
    CAST(fecha AS DATE) - MIN(CAST(fecha AS DATE)) OVER (PARTITION BY campana) + 1
                                AS dia_de_campana,
    CAST(fecha AS DATE)         AS fecha,
    revenue_neto,
    revenue_neto_acumulado
FROM gold.campaign_performance
ORDER BY campana, fecha;
