
# Simular la estructura del data lake en local

import shutil
from pathlib import Path
from datetime import date

# Directorios del proyecto
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
LAKE_ROOT = ROOT_DIR / "freshmart-lake"

# Configuración de la ingesta
FUENTE = "marketing"
FECHA = date(2024, 9, 16)  # Fecha de ingesta del ticket

# Archivos de marketing
archivos = [
    "campana_verano_clientes.csv",
    "campana_verano_ventas.csv",
    "productos_promo_verano.csv",
]

for archivo in archivos:
    origen = DATA_DIR / archivo

    # Comprobar que el archivo de origen existe
    if not origen.is_file():
        print(f"⚠️ No se encuentra el archivo: {origen}")
        continue

    # Nombre de la tabla: nombre del archivo sin extensión
    tabla = Path(archivo).stem

    # Estructura: raw/{fuente}/{tabla}/{año}/{mes}/{día}/
    destino = (
        LAKE_ROOT
        / "raw"
        / FUENTE
        / tabla
        / str(FECHA.year)
        / f"{FECHA.month:02d}"
        / f"{FECHA.day:02d}"
    )

    destino.mkdir(parents=True, exist_ok=True)

    # Copiar el archivo original sin modificarlo
    shutil.copy2(origen, destino / archivo)

    print(f"✓ {archivo} → {destino.relative_to(ROOT_DIR)}")


print("\nTodos los archivos subidos a raw (sin modificar)")