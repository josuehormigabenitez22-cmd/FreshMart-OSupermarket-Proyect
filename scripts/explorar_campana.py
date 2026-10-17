# Generamos un script para explorar los datos que nos han dado

import json
from pathlib import Path

import pandas as pd

# Directorios del proyecto
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
REPORT_DIR = ROOT_DIR / "reports"
REPORT_PATH = REPORT_DIR / "exploracion_campana.json"


def analizar_csv(
    nombre_archivo: str,
    columnas_muestra: list[str] | None = None,
    columna_id: str | None = None,
    filas_muestra: int = 10,
) -> dict:
    """Analiza un CSV y devuelve un informe serializable a JSON"""

    ruta = DATA_DIR / nombre_archivo
    df = pd.read_csv(ruta)

    # Sustituir valores ausentes por None para generar JSON válido.
    muestra = (
        df.head(filas_muestra)
        .astype(object)
        .where(df.head(filas_muestra).notna(), None)
        .to_dict(orient="records")
    )

    informe = {
        "archivo": nombre_archivo,
        "filas": len(df),
        "numero_columnas": len(df.columns),
        "columnas": list(df.columns),
        "tipos_datos": {columna: str(tipo) for columna, tipo in df.dtypes.items()},
        "valores_nulos": {
            columna: int(cantidad) for columna, cantidad in df.isnull().sum().items()
        },
        "filas_muestra": muestra,
    }

    # Analizar posibles duplicados por identificador.
    if columna_id and columna_id in df.columns:
        ids_unicos = int(df[columna_id].nunique())

        informe["identificadores"] = {
            "columna": columna_id,
            "ids_unicos": ids_unicos,
            "ids_totales": len(df),
            "posibles_duplicados": int(len(df) - ids_unicos),
        }

    # Inspeccionar muestras de columnas concretas.
    if columnas_muestra:
        informe["muestras_columnas"] = {}

        for columna in columnas_muestra:
            if columna in df.columns:
                valores = df[columna].dropna().head(filas_muestra).tolist()

                # Convertir tipos NumPy y otros valores a tipos JSON.
                informe["muestras_columnas"][columna] = [
                    valor.item() if hasattr(valor, "item") else valor
                    for valor in valores
                ]

    return informe


def main() -> None:
    """Genera el informe de exploración de los datos de la campaña."""

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    informes = {
        "clientes": analizar_csv(
            "campana_verano_clientes.csv",
            columna_id="cliente_id",
        ),
        "ventas": analizar_csv(
            "campana_verano_ventas.csv",
            columnas_muestra=["fecha_compra", "precio"],
        ),
        "productos": analizar_csv(
            "productos_promo_verano.csv",
        ),
    }

    informe_final = {
        "proyecto": "FreshMart",
        "tipo_informe": "exploracion_inicial",
        "datasets": informes,
    }

    with REPORT_PATH.open("w", encoding="utf-8") as archivo:
        json.dump(
            informe_final,
            archivo,
            indent=4,
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        )

    print(f"Informe generado correctamente: {REPORT_PATH}")


if __name__ == "__main__":
    main()
