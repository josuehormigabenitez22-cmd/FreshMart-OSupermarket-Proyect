-- Segmentación de los clientes de la campaña de verano (Jorge).
--
-- Requisitos (los prepara src/freshmart/segmentation/segment.py):
--   * vista  campana_raw   -> campana_verano_clientes.csv (todo VARCHAR)
--   * vista  clientes_raw  -> clientes.csv (todo VARCHAR)
--   * vista  pedidos_raw   -> pedidos.csv  (todo VARCHAR)
--   * variable fecha_corte -> SET VARIABLE fecha_corte = DATE '2024-09-16';
--
-- Reglas:
--   * Base: los clientes de la campaña, UNA fila por cliente. La lista trae 15.247 filas
--     porque un cliente aparece una vez por canal de contacto; son 14.946 clientes.
--   * Ventana: [fecha_corte - 3 meses, fecha_corte), pedidos cancelados excluidos.
--   * Segmento: premium >= 7 pedidos, regular 2-6, nuevo 0-1.
--   * "Sin pedidos" no es un segmento: es nuevo con pedidos_3m = 0.

WITH clientes_campana AS (
    -- Base del cruce: quién recibió la campaña (sin repetir por canal).
    SELECT DISTINCT CAST(CAST(cliente_id AS DOUBLE) AS BIGINT) AS cliente_id
    FROM campana_raw
),

clientes_unicos AS (
    -- Trampa 1: la maestra trae ids duplicados. Nos quedamos con una fila por id,
    -- priorizando la que tiene el código postal completo (5 dígitos) y
    -- desempatando por teléfono para que el resultado sea determinista.
    SELECT * EXCLUDE (rn)
    FROM (
        SELECT
            CAST(cliente_id AS BIGINT) AS cliente_id,
            nombre,
            fecha_registro,
            -- Trampa 3: el CSV ya trae CPs sin el cero inicial ('8015').
            lpad(codigo_postal, 5, '0') AS codigo_postal,
            ROW_NUMBER() OVER (
                PARTITION BY cliente_id
                ORDER BY (length(codigo_postal) = 5) DESC, telefono ASC
            ) AS rn
        FROM clientes_raw
    )
    WHERE rn = 1
),

pedidos_3m AS (
    SELECT
        -- cliente_id llega como '108333.0' en pedidos.csv.
        CAST(CAST(cliente_id AS DOUBLE) AS BIGINT) AS cliente_id,
        COUNT(*) AS pedidos_3m
    FROM (
        SELECT
            *,
            -- Trampa 2: dos formatos de fecha. Primero ISO; si falla, dd/mm/aaaa.
            COALESCE(
                try_strptime(fecha_pedido, '%Y-%m-%d %H:%M:%S'),
                try_strptime(fecha_pedido, '%d/%m/%Y %H:%M')
            ) AS fecha_ts
        FROM pedidos_raw
    )
    WHERE cliente_id IS NOT NULL
      AND estado <> 'cancelado'
      AND fecha_ts >= getvariable('fecha_corte') - INTERVAL 3 MONTH
      AND fecha_ts <  getvariable('fecha_corte')
    GROUP BY 1
)

-- Los dos joins son LEFT: un cliente de la campaña sin ficha en la maestra o sin
-- pedidos sigue en el resultado (los que no tienen pedidos son el hallazgo).
SELECT
    cc.cliente_id,
    m.nombre,
    CAST(m.fecha_registro AS DATE)     AS fecha_registro,
    COALESCE(p.pedidos_3m, 0)          AS pedidos_3m,
    CASE
        WHEN COALESCE(p.pedidos_3m, 0) >= 7 THEN 'premium'
        WHEN COALESCE(p.pedidos_3m, 0) >= 2 THEN 'regular'
        ELSE 'nuevo'
    END AS segmento_calculado
FROM clientes_campana AS cc
LEFT JOIN clientes_unicos AS m ON cc.cliente_id = m.cliente_id
LEFT JOIN pedidos_3m      AS p ON cc.cliente_id = p.cliente_id
ORDER BY cc.cliente_id;
