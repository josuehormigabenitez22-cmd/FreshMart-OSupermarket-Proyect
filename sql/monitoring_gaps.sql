-- ================================================================
-- Monitorización: días SIN datos en gold.campaign_performance
--
-- Un pipeline puede terminar en verde y no haber escrito nada (filtro que se lo
-- lleva todo, origen vacío, partición en la carpeta de otro día). Eso no falla,
-- así que no avisa. Esta query sí: si devuelve filas, faltan días.
--
-- Parámetros (los fija freshmart.quality.gap_detection):
--   * campana -> 'verano' / 'primavera'
--   * desde, hasta -> ventana de fechas esperadas (ambas incluidas). El dataset es
--     histórico de 2024: la ventana es un parámetro, nunca CURRENT_DATE.
-- ================================================================

WITH fechas_esperadas AS (
    SELECT CAST(gs AS DATE) AS fecha
    FROM generate_series(
        CAST(getvariable('desde') AS TIMESTAMP),
        CAST(getvariable('hasta') AS TIMESTAMP),
        INTERVAL 1 DAY
    ) AS t (gs)
),

fechas_con_datos AS (
    SELECT DISTINCT CAST(fecha AS DATE) AS fecha
    FROM gold.campaign_performance
    WHERE campana = getvariable('campana')
),

gaps AS (
    SELECT fe.fecha
    FROM fechas_esperadas AS fe
    LEFT JOIN fechas_con_datos AS fd ON fe.fecha = fd.fecha
    WHERE fd.fecha IS NULL
)

SELECT
    fecha,
    -- 1 = gap consecutivo al anterior (un hueco de varios días seguidos)
    fecha - LAG(fecha) OVER (ORDER BY fecha) AS dias_desde_gap_anterior
FROM gaps
ORDER BY fecha;
