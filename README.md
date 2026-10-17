# FreshMart — Online Supermarket Data Engineering Project

**Estado:** En desarrollo 🚧

## 📌 Descripción

**FreshMart** es un proyecto personal de Data Engineering basado en el escenario de un supermercado online ficticio. El objetivo es desarrollar progresivamente un flujo de trabajo de datos que permita explorar, organizar, ingerir y transformar información relacionada con clientes, productos, pedidos, ventas, inventario y campañas de marketing.

El proyecto sirve como entorno práctico para aplicar conceptos de ingeniería de datos, automatización de procesos y diseño de arquitecturas de datos, construyendo una solución modular y reproducible.

> Este proyecto tiene fines educativos y de portfolio. FreshMart es un escenario ficticio y los datos utilizados se emplean como material de práctica.

## 🎯 Objetivos

- Explorar y comprender datasets en formato CSV.
- Identificar problemas de calidad de datos, valores nulos y posibles duplicados.
- Diseñar una estructura de almacenamiento inspirada en un Data Lake.
- Implementar procesos de ingesta de datos mediante Python.
- Generar informes de exploración en formato JSON.
- Preparar una base para futuras transformaciones, validaciones y análisis.
- Documentar la evolución del proyecto siguiendo buenas prácticas de desarrollo.

## 🛠️ Tecnologías

- **Python:** desarrollo de scripts y automatización.
- **Pandas:** exploración y análisis inicial de datasets.
- **JSON:** almacenamiento de informes estructurados.
- **CSV:** formato de los datos de entrada.
- **Git y GitHub:** control de versiones y seguimiento del desarrollo.

## 📂 Estructura del proyecto

```text
FreshMart-OSupermarket-Proyect/
├── data/                       # Datasets locales de entrada
├── docs/                       # Documentación del proyecto
├── reports/                    # Informes generados
├── scripts/
│   ├── explorar_campana.py      # Exploración de datos y generación de JSON
│   └── subir_a_raw.py           # Simulación de ingesta en el Data Lake
├── src/                        # Código fuente del proyecto
├── .gitignore
└── README.md
```

La estructura puede cambiar a medida que se incorporen nuevos componentes.

## 📊 Datos disponibles

Los datasets iniciales cubren distintas áreas del negocio:

- **Clientes:** información relacionada con los clientes.
- **Productos:** catálogo de productos y productos promocionales.
- **Pedidos y ventas:** operaciones comerciales y líneas de pedido.
- **Inventario:** seguimiento diario de existencias.
- **Marketing:** datos de campañas comerciales y segmentación de clientes.

Los archivos de entrada se mantienen en `data/` durante el desarrollo local. Según la configuración de Git, estos datasets pueden estar excluidos del repositorio.

## ⚙️ Funcionalidades actuales

### 1. Exploración de datos

El script `scripts/explorar_campana.py` permite realizar una primera inspección de los datasets de una campaña de verano.

El informe recoge información como:

- Número de filas y columnas.
- Nombres y tipos de datos.
- Cantidad de valores nulos por columna.
- Muestras de registros.
- Posibles duplicados en identificadores seleccionados.

El resultado se guarda en:

```text
reports/exploracion_campana.json
```

### 2. Ingesta de datos en bruto

El script `scripts/subir_a_raw.py` simula la carga de archivos de marketing en una estructura local de Data Lake, organizándolos por fuente, tabla y fecha de ingesta.

La estructura de destino sigue este patrón:

```text
freshmart-lake/
└── raw/
    └── marketing/
        └── nombre_tabla/
            └── año/
                └── mes/
                    └── día/
                        └── archivo.csv
```

Esta primera capa conserva los archivos originales sin aplicar transformaciones.

## 🚀 Instalación y ejecución

### Requisitos previos

- Python instalado.
- Git.
- Las dependencias necesarias para los scripts.

### 1. Clonar el repositorio

```bash
git clone <URL_DEL_REPOSITORIO>
cd FreshMart-OSupermarket-Proyect
```

### 2. Instalar dependencias

Si todavía no existe un archivo `requirements.txt`, instala las dependencias utilizadas actualmente:

```bash
python -m pip install pandas
```

### 3. Ejecutar la exploración de datos

Desde la raíz del proyecto:

```bash
python scripts/explorar_campana.py
```

El informe JSON se generará en el directorio `reports/`.

### 4. Ejecutar la ingesta en bruto

```bash
python scripts/subir_a_raw.py
```

Los archivos seleccionados se copiarán a la estructura local de `freshmart-lake/raw/`.

## Activar el entorno virtual

```bash
.\.venv\Scripts\Activate.ps1
```

## 🗺️ Roadmap

- [x] Crear la estructura inicial del proyecto.
- [x] Preparar scripts de exploración e ingesta.
- [x] Generar un informe de exploración en JSON.
- [ ] Mejorar las validaciones de calidad de datos.
- [ ] Separar la lógica de ingesta y transformación en módulos reutilizables.
- [ ] Diseñar un modelo de datos para el negocio.
- [ ] Incorporar una capa de datos procesados.
- [ ] Automatizar la ejecución de los procesos.
- [ ] Añadir pruebas y documentación técnica.
- [ ] Evaluar la integración de tecnologías de almacenamiento y procesamiento adicionales.

## 📚 Aprendizajes

Este proyecto busca consolidar conocimientos prácticos en:

- Programación Python aplicada a datos.
- Organización y gestión de datasets.
- Diseño inicial de pipelines de datos.
- Estructuras de almacenamiento tipo Data Lake.
- Exploración y calidad de datos.
- Generación de informes estructurados.
- Control de versiones y documentación técnica.

## 👤 Autor

Proyecto personal desarrollado como parte de mi portfolio de Data Engineering y mi proceso de aprendizaje en arquitectura y procesamiento de datos.

## License

This project is proprietary and all rights are reserved.
Viewing the repository for portfolio evaluation does not
grant permission to reuse, modify, or distribute its contents.

See [LICENSE](LICENSE) for details.
