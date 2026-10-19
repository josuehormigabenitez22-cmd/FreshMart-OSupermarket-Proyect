# Playbook: añadir una campaña de Marketing al pipeline

**Para:** cualquier persona del equipo de datos · **Pedido por:** Víctor Molina (demo del viernes)
**Tiempo estimado:** 1–2 h si el CSV no trae sorpresas.

Con esto, cuando María mande la campaña de otoño (o la de Navidad), cualquiera del equipo puede
pasarla de CSV a dashboard sin depender de quien hizo el pipeline. El ejemplo usa una campaña
`otoño` imaginaria.

## Antes de empezar

- Pide a Marketing el **periodo exacto** de la campaña (fecha de inicio y de fin) y confirma
  qué archivo es el bueno. Si te llega `ventas_otoño_FINAL_v3.csv`, pregunta.
- No abras el CSV en Excel: cambia fechas y quita ceros sin avisar. Míralo con pandas.
- Copia el archivo **tal cual** a `data/` y súbelo a raw: añádelo a `FILES` en
  `src/freshmart/lake/raw_upload.py` y ejecuta `python scripts/subir_a_raw.py`. Raw no se
  toca nunca: si llega una versión corregida, entra con otra fecha de ingesta.

## Los 6 pasos

### 1. Explora el CSV y apunta lo raro

```python
import pandas as pd

df = pd.read_csv("data/campana_otono_ventas.csv", dtype=str)
df.info()
df.head(10)
df.isna().sum()
df.duplicated().sum()
df["<columna_fecha>"].sample(20, random_state=1)  # ¿cuántos formatos de fecha?
df["<columna_precio>"].sample(20, random_state=1)  # ¿número, o texto con € y coma?
```

Lo que tienes que saber antes de seguir:

- Cómo se llaman las 9 columnas del esquema común (venta, cliente, producto, fecha, cantidad,
  precio, descuento, tienda y campaña).
- Cómo marca a los clientes anónimos (vacío como verano, `-1` como primavera u otro valor).
- Qué formatos de fecha trae.

### 2. Añade la campaña al Enum

En `src/freshmart/campaigns/config.py`:

```python
class Campaign(StrEnum):
    VERANO = "verano_2024"
    PRIMAVERA = "primavera_2024"
    OTONO = "otono_2024"  # el valor de la columna campana/promocion del CSV
```

### 3. Declara su configuración

En el mismo archivo, una entrada nueva en `CONFIGS`. Es lo único que cambia entre campañas:
ninguna función de limpieza se toca.

```python
Campaign.OTONO: CampaignConfig(
    archivo="campana_otono_ventas.csv",
    columnas=MappingProxyType({            # nombre en el CSV -> nombre común
        "id_venta": COL_VENTA_ID,
        "cliente": COL_CLIENTE_ID,
        # ... las 9 columnas
    }),
    anonimo_valor=None,                    # None si viene vacío; -1 (u otro) si es un valor
    particion="otono",                     # silver/campaign_ventas/campana=otono/
    fecha_min=date(2024, 9, 16),           # periodo que confirmó Marketing
    fecha_max=date(2024, 11, 30),
),
```

Si trae un formato de fecha que no sea ISO, `dd/mm/aaaa` o `Mon d, aaaa`, la limpieza falla con
ejemplos del valor. Añade su máscara en `campaigns/clean.py` (regex + `format=` explícito).
**Nunca** uses `format="mixed", dayfirst=True`: lee las fechas ISO como año-día-mes.

### 4. Ejecuta el pipeline de esa campaña

```powershell
python scripts/ejecutar_pipeline.py --campaign otono --input data --silver-dir freshmart-lake/silver
```

Tienen que salir **6/6 validaciones OK**. Si alguna falla, no se escribe nada en silver. Mira la
tabla de abajo antes de tocar código.

### 5. Reconstruye gold y revisa el dashboard

```powershell
python scripts/ejecutar_pipeline.py --only-gold --silver-dir freshmart-lake/silver --gold-dir freshmart-lake/gold
python scripts/dashboard.py --gold-dir freshmart-lake/gold --input data
```

Añade el periodo de la campaña a la CTE `periodos` de la card 2 en
`sql/dashboard_cards.sql` (los clientes nuevos dependen de él). Comprueba que los totales tienen
sentido: filas por día, revenue de un orden razonable, top de productos coherente con la
temporada.

### 6. Tests, PR y aviso

- Añade una prueba con un CSV pequeño de la campaña (mismo patrón que
  `tests/integration/test_pipeline_e2e.py`) y fija las cifras reales que has comprobado.
- `pytest`, `ruff check .` y `mypy` en verde.
- PR con qué, cómo probar, decisiones y contexto. Lo raro que hayas encontrado va en la PR como
  pregunta.
- Avisa a Marketing con el dato, la comparación y qué significa, no solo "ya está cargado".

## Si una validación falla

| Validación | Qué suele significar | Qué hacer |
|---|---|---|
| `no_vacio` | CSV vacío o todo filtrado (p. ej. cantidades a 0) | Pedir el archivo de nuevo a Marketing |
| `columnas_esperadas` | El mapping no cubre alguna columna | Revisar nombres en el paso 3 |
| `venta_id_unico` | Ids repetidos que no son duplicados exactos | Preguntar a Marketing: ¿dos exportaciones mezcladas? |
| `fechas_validas` | Fechas vacías o imposibles | Ver los ejemplos del log; preguntar si faltan datos |
| `fechas_en_rango` | Formato de fecha mal leído o periodo mal configurado | Revisar máscaras y `fecha_min`/`fecha_max` |
| `valores_validos` | Precio ≤ 0, cantidad < 1 o descuento fuera de 0–100 | **No borrar**: preguntar si son promos legítimas o un error del origen |

Regla del equipo: **un dato raro se consulta, no se elimina**.

## Sobre escalarlo a otros equipos (Ops, Finance…)

El patrón (configuración por fuente + limpieza común + validaciones + capas raw/silver/gold) es
reutilizable, pero cada equipo tiene sus propios formatos y definiciones: qué es "revenue", qué
es un "cliente". Antes de comprometer fechas, hay que sentarse con Elena y con cada equipo para
acordar esas definiciones. No es copiar y pegar este pipeline.
