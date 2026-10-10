# Bienvenido a FreshMart — Data Engineering

## 1. Descripción del proyecto

FreshMart es un supermercado 100 % online fundado en Barcelona en 2019, especializado en la entrega de pedidos en un plazo de dos horas.

La empresa opera en cinco ciudades españolas y gestiona aproximadamente **400.000 pedidos mensuales**, generando un volumen significativo de datos de ventas, clientes e inventario.

El objetivo de este proyecto es desarrollar y mantener una infraestructura de datos fiable, escalable y automatizada que facilite el análisis del negocio y la toma de decisiones.

## 2. Objetivos del proyecto

- Automatizar la ingesta de datos desde distintas fuentes.
- Limpiar, validar y transformar los datos.
- Evitar registros duplicados y garantizar la calidad de la información.
- Construir capas de datos estructuradas para análisis y reporting.
- Orquestar pipelines ETL/ELT y monitorizar sus ejecuciones.
- Facilitar el acceso a datos fiables para los equipos de negocio.

## 3. Stack tecnológico

| Tecnología | Uso |
|---|---|
| Python 3.11 | Ingesta, procesamiento y automatización |
| SQL | Consultas y transformaciones |
| PostgreSQL 15 (AWS RDS) | Bases de datos operacionales |
| AWS S3 | Almacenamiento de datos en el Data Lake |
| Apache Airflow 2.7 | Orquestación de pipelines |
| dbt Core | Modelado y transformación de datos |
| Metabase | Visualización y análisis |
| GitHub | Control de versiones y colaboración |

## 4. Arquitectura de datos

El proyecto utiliza una arquitectura basada en tres componentes principales:

- **Fuentes operacionales:** PostgreSQL, con bases de datos de pedidos (`orders`), usuarios (`users`) e inventario (`inventory`).
- **Data Lake:** AWS S3, organizado en capas `raw`, `silver` y `gold`.
- **Procesamiento y consumo:** Airflow para orquestación, dbt para transformaciones y Metabase para reporting.

Flujo general:

`PostgreSQL → Ingesta ETL/ELT → AWS S3 → Transformaciones → Datos analíticos → Metabase`

## 5. Principales retos técnicos

- Automatizar procesos que actualmente dependen de archivos CSV manuales.
- Garantizar una ingesta idempotente para evitar duplicados.
- Mejorar la calidad, consistencia y validación de los datos.
- Reducir el retraso de actualización de los datos de ventas.
- Documentar tablas, columnas y transformaciones.
- Recuperar y monitorizar pipelines fallidos.
- Mejorar la fiabilidad de los dashboards y modelos analíticos.

## 6. Alcance del rol

Como Junior Data Engineer, las responsabilidades principales son:

- Desarrollar tareas sencillas de ingesta, limpieza y transformación.
- Escribir código Python y consultas SQL mantenibles.
- Validar los resultados con datos reales.
- Documentar los procesos desarrollados.
- Trabajar con GitHub mediante ramas y Pull Requests.
- Colaborar con el equipo para resolver incidencias y mejorar los pipelines existentes.

Las decisiones de arquitectura y los cambios críticos en producción deben coordinarse con la persona responsable de Data Engineering.

## 7. Flujo de trabajo

1. Revisar la tarea y comprender los requisitos.
2. Explorar las fuentes y comprobar la estructura de los datos.
3. Desarrollar la solución en un entorno de trabajo controlado.
4. Validar resultados, calidad y posibles duplicados.
5. Documentar los cambios y crear un Pull Request.
6. Solicitar revisión antes de integrar los cambios.

**Principio fundamental:** priorizar la calidad, la trazabilidad y la fiabilidad de los datos antes que la velocidad de desarrollo.