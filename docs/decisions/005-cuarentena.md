# ADR 005 — Cuarentena para las filas imposibles

- **Estado:** aceptada
- **Fecha:** 2024-09-23 (semana 2: inventario y líneas de pedido)

## Contexto

Hasta ahora la regla era una: si una validación falla, no se escribe nada en silver. Con las
campañas no hubo conflicto, porque sus problemas (duplicados, cantidad 0) tenían una limpieza
clara. Los archivos de operaciones traen otro tipo de problema:

- `inventario_diario.csv`: 34 filas con stock negativo, imposible físicamente. 5 de ellas son
  una segunda versión de una clave que ya llega con un stock positivo.
- `lineas_pedido.csv`: 12 precios negativos, 8 cantidades a 0 y 160 líneas cuyo `total_linea`
  no cuadra con cantidad × precio × (1 − descuento), con diferencias de hasta 42 €.

Bloquear 142.376 líneas por 172 dejaría a Operaciones sin datos. Borrarlas iría contra la regla
del equipo: un dato raro se consulta, no se elimina. Corregirlas exigiría saber cuál de los dos
valores es el bueno, y eso no lo sabemos.

## Decisión

Se distinguen dos niveles:

| Nivel | Ejemplos | Qué pasa |
|---|---|---|
| **Tabla** | vacía, clave repetida, producto inexistente en inventario | Validación ERROR: no se escribe nada |
| **Fila** | stock negativo, precio negativo, total que no cuadra | La fila va a `silver/_cuarentena/<tabla>/` con `motivo_cuarentena`; el resto se procesa |

- `quality/cuarentena.py` (`separar_cuarentena`) aplica reglas declaradas como máscaras con
  nombre. Cada regla genera un AVISO con su número de filas en el informe de calidad.
- La cuarentena se reescribe en cada carga, como cualquier tabla silver, y con escritura
  atómica.
- Las validaciones de tabla se ejecutan **después** de apartar la cuarentena. Así, en el
  inventario, las 5 claves con dos versiones quedan únicas al apartar la negativa, sin resolver
  conflictos a mano.
- Lo dudoso pero posible **no** va a cuarentena: precios a 0 (¿regalos?) y productos que no
  están en el catálogo se quedan en silver con un AVISO.

## Consecuencias

- Las tablas silver de operaciones nunca contienen filas imposibles, y nada se pierde: silver +
  cuarentena = filas de entrada (sin contar duplicados exactos).
- La cuarentena es una lista de preguntas para negocio: alguien tiene que revisarla y decidir.
  No es un cajón de sastre: una regla nueva necesita un motivo con nombre y un test.
- Las campañas siguen con la regla anterior: no tenían filas imposibles. Si aparecen, se puede
  aplicar el mismo mecanismo.
