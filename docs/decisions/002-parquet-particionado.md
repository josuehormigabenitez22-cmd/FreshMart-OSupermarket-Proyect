# ADR 002 — Silver y gold en Parquet particionado por campaña

- **Estado:** aceptada
- **Fecha:** 2024-09-18

## Contexto

El curso escribe la silver en CSV para poder inspeccionarla. Elena pide Parquet, y el código
del curso no se pone de acuerdo en el nombre del archivo: `run.py` escribe
`ventas_{campaña}.parquet` y `gold.py` lee `campaign_ventas.parquet`. Además, cada campaña se
procesa por separado (verano el miércoles, primavera el jueves) y reprocesar una no debe tocar
la otra.

## Decisión

- **Formato Parquet** (pyarrow) en silver y gold. Es columnar, comprimido (los 2,7 MB del CSV
  de verano quedan en ~0,6 MB) y **conserva los tipos**: fechas, `int64` con nulos y booleanos
  no se pierden como en CSV, que es justo lo que costó limpiar.
- **Partición estilo Hive por campaña** en la tabla de ventas:
  `silver/campaign_ventas/campana=<verano|primavera>/part-0.parquet`. La columna `campana` no
  se guarda dentro del archivo: la aporta el directorio, y pandas, pyarrow, DuckDB y Athena la
  recuperan al leer la tabla.
- **Una tabla = un directorio**, se lee el directorio entero (`pd.read_parquet(dir)`), nunca un
  nombre de archivo concreto. Eso elimina el desajuste de nombres del curso.
- **Escritura atómica** (`lake/parquet.py`): se escribe en un directorio temporal oculto y se
  renombra al final. Una ejecución que falla a mitad no deja una partición rota, y si falla una
  validación la partición anterior queda intacta.

## Alternativas descartadas

- **CSV en silver**: pierde tipos y obliga a repetir el parseo en cada lectura.
- **Un único Parquet con todas las campañas**: reprocesar primavera reescribiría verano.
- **Particionar por fecha**: 166 archivos diminutos para 74k filas. La campaña es la unidad con
  la que se reprocesa.

## Consecuencias

- Añadir una campaña es añadir una partición; las demás no se tocan.
- Los Parquet no se abren en Excel: para inspeccionar se usa pandas o DuckDB, que además
  ejecuta el SQL de gold directamente sobre los archivos.
- Las tablas pequeñas (catálogo, gold) no se particionan.
