# Generamos un script para explorar los datos que nos han dado

import pandas as pd
from pathlib import Path

# Localizar la raíz del proyecto
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"

# Cargar los archivos CSV
clientes = pd.read_csv(DATA_DIR / "campana_verano_clientes.csv")
ventas = pd.read_csv(DATA_DIR / "campana_verano_ventas.csv")
productos = pd.read_csv(DATA_DIR / "productos_promo_verano.csv")

# Mostramos por pantalla información básica de los datos
print("=" * 60)
print("CLIENTES DE LA CAMPAÑA")
print("=" * 60)
print(f"Filas: {len(clientes):,}")
print(f"Columnas: {list(clientes.columns)}")
print()
print(clientes.info())
print()
print(clientes.head())
print()
print("Nulos por columna:")
print(clientes.isnull().sum())
print()
print(f"IDs únicos: {clientes['cliente_id'].nunique():,}")
print(f"IDs totales: {len(clientes):,}")
print(f"→ Posibles duplicados: {len(clientes) - clientes['cliente_id'].nunique():,}")


# Explorar el CSV de ventas — aquí es donde está el CAOS
print("=" * 60)
print("VENTAS DE LA CAMPAÑA")
print("=" * 60)
print(f"Filas: {len(ventas):,}")
print(f"Columnas: {list(ventas.columns)}")
print()
print(ventas.dtypes)
print()
print("Primeras filas:")
print(ventas.head(10).to_string())
print()
print("Nulos por columna:")
print(ventas.isnull().sum())
print()
# Verificar el formato de fecha_compra
print("Muestras de fecha_compra:")
print(ventas['fecha_compra'].sample(10, random_state=42).values)
print()
# Verificar el formato de precio
print("Muestras de precio:")
print(ventas['precio'].sample(10, random_state=42).values)