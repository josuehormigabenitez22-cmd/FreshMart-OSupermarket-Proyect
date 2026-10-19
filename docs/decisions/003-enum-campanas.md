# ADR 003: Campañas como Enum con su configuración declarada

- **Estado:** aceptada
- **Fecha:** 2024-09-18 (comentario 4 del code review de Elena)

## Contexto

La primera versión usaba strings como claves: `COLUMN_MAPPINGS['verano']`. Si alguien escribe
`'Verano'`, `.get()` devuelve el valor por defecto sin avisar y el pipeline procesa la campaña
sin mapping. Además, primavera llegó con otros nombres de columna y otra forma de marcar a los
anónimos (`-1` en vez de vacío), y vendrán más campañas.

## Decisión

- `Campaign(StrEnum)` en `campaigns/config.py`. Sus valores son los de la columna
  `campana`/`promocion` de los CSV (`verano_2024`, `primavera_2024`). Un nombre mal escrito da
  un error claro en vez de un resultado vacío.
- Toda la diferencia entre campañas vive en **un** `CampaignConfig` congelado por campaña:
  archivo, mapping de columnas, `anonimo_valor` (el valor que marca al anónimo, no un sí/no:
  `None` en verano, `-1` en primavera), nombre de partición y periodo (`fecha_min`, `fecha_max`).
- Las funciones de limpieza no tienen `if campaña == ...`: reciben lo que necesitan de la
  configuración.
- La CLI acepta tanto el valor (`verano_2024`) como el nombre corto (`verano`) y rechaza
  cualquier otro con la lista de válidas.

## Consecuencias

- Añadir una campaña = un valor en el Enum y una entrada en `CONFIGS` (ver
  `docs/playbook_nueva_campana.md`). Un test comprueba que cada mapping cubre el esquema común.
- `MappingProxyType` y `frozen=True` impiden modificar la configuración en tiempo de ejecución.
- El periodo de campaña está en la configuración y no en el SQL de gold, salvo en la card 2 del
  dashboard, que lo repite porque Metabase no lee Python. Un test comprueba que ambos coinciden.
