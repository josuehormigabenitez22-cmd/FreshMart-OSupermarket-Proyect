# ADR 004: Fechas parseadas por máscara, nunca con `format="mixed", dayfirst=True`

- **Estado:** aceptada
- **Fecha:** 2024-09-17

## Contexto

`fecha_compra` de verano mezcla tres formatos: ISO `2024-07-15` (30.157 filas), `15/07/2024`
(10.646) y `Jul 15, 2024` (2.088). El código del curso usa
`pd.to_datetime(..., format="mixed", dayfirst=True)`. Con `dayfirst=True`, pandas lee las ISO
como año-**día**-mes: **11.126 ventas** cambian de fecha y la campaña de verano pasa a ir del
2024-01-07 al 2024-12-09. El curso avisa de este mismo error en `pedidos.csv` y luego lo repite en ventas.

Lo grave no es el error en sí, sino que **no falla**: las fechas mal leídas siguen siendo
fechas válidas.

## Decisión

1. Cada formato se identifica con una **regex** y se parsea con su `format=` explícito
   (`campaigns/clean.py`). Los meses en texto se traducen con una tabla propia, no con `%b`, que
   depende del idioma del sistema.
2. Un valor que no encaja en ninguna máscara hace **fallar la limpieza** con ejemplos, en vez
   de convertirse en NaT en silencio.
3. Se añade la validación **`fechas_en_rango`**: todas las fechas deben caer en el periodo de la
   campaña. Es la única de las 6 que detecta el error del curso. Un test de regresión aplica el
   parseo del curso a los datos reales y comprueba que falla justo esa validación.
4. `pedidos.csv` (ISO con hora y `dd/mm/aaaa HH:MM`) sigue la misma regla: dos pasadas con
   formatos explícitos, en pandas (`segmentation/segment.py`) y en SQL (`try_strptime`).

## Consecuencias

- Un formato nuevo exige añadir su máscara (una línea y un test), y lo sabrás porque el pipeline
  falla con ejemplos. Es preferible a que lo "adivine" mal.
- Resultado: verano queda entre 2024-06-17 y 2024-09-14, el rango esperado.
