-- ================================================================
-- GOLD: campaign_top_products
-- Granularidad: campaña + producto, ranking por revenue neto.
-- Misma lógica que construir_top_products (src/freshmart/campaigns/gold.py).
--
-- Requisitos (los prepara gold.construir_gold_sql):
--   * vistas campaign_ventas, productos, categorias (silver)
--   * variable top_n -> SET VARIABLE top_n = 50;
-- ================================================================

WITH producto_stats AS (
    -- Se agrega por id y se enriquece después: agrupar por nombre/marca
    -- uniría productos distintos que compartan nombre.
    SELECT
        campana,
        producto_id,
        SUM(precio * cantidad)                                          AS revenue_bruto,
        SUM(precio * cantidad * (1 - COALESCE(descuento_pct, 0) / 100.0)) AS revenue_neto,
        SUM(cantidad)                                                   AS unidades_vendidas,
        COUNT(DISTINCT cliente_id)                                      AS compradores_unicos,
        COUNT(*)                                                        AS num_transacciones
    FROM campaign_ventas
    WHERE cantidad > 0
    GROUP BY campana, producto_id
),

enriquecido AS (
    -- LEFT JOIN: un producto que no está en el maestro sigue contando (sin nombre).
    SELECT
        s.*,
        p.nombre    AS producto_nombre,
        p.marca,
        c.nombre    AS categoria
    FROM producto_stats AS s
    LEFT JOIN productos  AS p ON s.producto_id = p.producto_id
    LEFT JOIN categorias AS c ON p.categoria_id = c.categoria_id
),

rankeado AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY campana
            ORDER BY revenue_neto DESC, producto_id
        ) AS ranking
    FROM enriquecido
)

SELECT
    campana,
    ranking,
    producto_id,
    producto_nombre,
    marca,
    categoria,
    revenue_bruto,
    revenue_neto,
    unidades_vendidas,
    compradores_unicos,
    num_transacciones
FROM rankeado
WHERE ranking <= getvariable('top_n')
ORDER BY campana, ranking;
